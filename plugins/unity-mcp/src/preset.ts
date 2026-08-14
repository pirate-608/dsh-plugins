/** Managed Unity agent-preset generation and lifecycle operations. */

import { createHash, randomUUID } from 'node:crypto'
import {
  chmod,
  cp,
  lstat,
  mkdir,
  readFile,
  readdir,
  readlink,
  rename,
  rm,
  writeFile,
} from 'node:fs/promises'
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import {
  MCP_SERVER_VERSION,
  PACKAGE_NAME,
  PRESET_STATE_FORMAT_VERSION,
} from './constants.js'

const STATE_FILE = '.dsh-unity-mcp.json'
const COMPOSITION_FILE = 'agent.cordis.yml'
const PRESET_METADATA_FILE = 'preset.yml'
const PRESET_ID_PATTERN = /^[a-z0-9][a-z0-9-]*$/
const SERVER_NAME_PATTERN = /^[A-Za-z0-9_-]{1,32}$/
const DEFAULT_TIMEOUT_MS = 300_000

/** User-configurable fields emitted into the Unity preset. */
export interface PresetConfig {
  id: string
  serverName: string
  uvxCommand: string
  toolCallTimeoutMs: number
}

/** Resolved installation locations and host versions for one operation. */
export interface PresetOperationContext {
  dshHome: string
  profileName: string
  profileDir: string
  standardPresetDir: string
  packageRoot: string
  mcpClientPlugin: string
  skillFilesystemPlugin: string
  packageVersion: string
  dshVersion: string
}

/** Result of inspecting one managed preset. */
export interface PresetStatus {
  kind: 'absent' | 'clean' | 'outdated' | 'modified' | 'invalid'
  presetDir: string
  message: string
}

/** Result of an install or update. */
export interface PresetWriteResult {
  presetDir: string
  backupDir?: string
}

interface ManagedState {
  formatVersion: number
  packageName: string
  packageVersion: string
  profileName: string
  dshVersion: string
  sourceStandardHash: string
  config: PresetConfig
  files: Record<string, string>
}

interface InspectedPreset {
  status: PresetStatus
  state?: ManagedState
}

/** Defaults used by the public CLI. */
export const DEFAULT_PRESET_CONFIG: Readonly<PresetConfig> = Object.freeze({
  id: 'unity',
  serverName: 'unity',
  uvxCommand: 'uvx',
  toolCallTimeoutMs: DEFAULT_TIMEOUT_MS,
})

/** Install a managed Unity preset without overwriting an existing id. */
export async function installPreset(
  context: PresetOperationContext,
  config: PresetConfig = { ...DEFAULT_PRESET_CONFIG },
): Promise<PresetWriteResult> {
  validateInputs(context, config)
  const target = presetDir(context, config.id)
  if (await pathExists(target)) {
    throw new Error(`Unity preset "${config.id}" already exists at ${target}; choose another id or run preset update`)
  }
  await mkdir(userPresetRoot(context), { recursive: true })
  const temp = await generatePreset(context, config)
  try {
    await rename(temp, target)
  } catch (error) {
    await rm(temp, { recursive: true, force: true })
    throw error
  }
  return { presetDir: target }
}

/** Rebuild a managed Unity preset from the currently installed standard preset. */
export async function updatePreset(
  context: PresetOperationContext,
  config: PresetConfig = { ...DEFAULT_PRESET_CONFIG },
  force = false,
): Promise<PresetWriteResult> {
  validateInputs(context, config)
  const inspected = await inspectPreset(context, config)
  if (inspected.status.kind === 'absent') {
    throw new Error(`${inspected.status.message}; run preset install first`)
  }
  if (inspected.status.kind === 'invalid') {
    throw new Error(`${inspected.status.message}; refusing to treat an unowned directory as managed`)
  }
  if (inspected.status.kind === 'modified' && !force) {
    throw new Error(`${inspected.status.message}; re-run with --force to preserve it as a backup before updating`)
  }

  const target = presetDir(context, config.id)
  const temp = await generatePreset(context, config)
  const displaced = inspected.status.kind === 'modified'
    ? await nextBackupPath(target)
    : `${target}.replace-${process.pid}-${randomUUID()}`
  try {
    await rename(target, displaced)
    try {
      await rename(temp, target)
    } catch (error) {
      await rename(displaced, target)
      throw error
    }
    if (inspected.status.kind !== 'modified') {
      await rm(displaced, { recursive: true, force: true })
      return { presetDir: target }
    }
    return { presetDir: target, backupDir: displaced }
  } catch (error) {
    await rm(temp, { recursive: true, force: true })
    throw error
  }
}

/** Remove an unchanged managed preset, or preserve a modified one as a backup with force. */
export async function removePreset(
  context: PresetOperationContext,
  config: PresetConfig = { ...DEFAULT_PRESET_CONFIG },
  force = false,
): Promise<{ removed: boolean, backupDir?: string }> {
  validateInputs(context, config)
  const inspected = await inspectPreset(context, config)
  if (inspected.status.kind === 'absent') return { removed: false }
  if (inspected.status.kind === 'invalid') {
    throw new Error(`${inspected.status.message}; refusing to remove an unowned directory`)
  }
  const target = presetDir(context, config.id)
  if (inspected.status.kind === 'modified') {
    if (!force) {
      throw new Error(`${inspected.status.message}; re-run with --force to move it to a backup instead of deleting it`)
    }
    const backupDir = await nextBackupPath(target)
    await rename(target, backupDir)
    return { removed: true, backupDir }
  }
  await rm(target, { recursive: true })
  return { removed: true }
}

/** Inspect ownership, local modifications, and host/package drift. */
export async function presetStatus(
  context: PresetOperationContext,
  config: PresetConfig = { ...DEFAULT_PRESET_CONFIG },
): Promise<PresetStatus> {
  validateInputs(context, config)
  return (await inspectPreset(context, config)).status
}

async function inspectPreset(context: PresetOperationContext, config: PresetConfig): Promise<InspectedPreset> {
  const target = presetDir(context, config.id)
  if (!await pathExists(target)) {
    return { status: { kind: 'absent', presetDir: target, message: `Unity preset "${config.id}" is not installed` } }
  }

  let state: ManagedState
  try {
    state = parseManagedState(await readFile(join(target, STATE_FILE), 'utf8'))
  } catch (error) {
    return {
      status: {
        kind: 'invalid',
        presetDir: target,
        message: `Unity preset "${config.id}" has no valid ${STATE_FILE}: ${errorMessage(error)}`,
      },
    }
  }

  const currentFiles = await hashTree(target, new Set([STATE_FILE]))
  if (!sameRecord(currentFiles, state.files)) {
    return {
      state,
      status: {
        kind: 'modified',
        presetDir: target,
        message: `Unity preset "${config.id}" contains changes made after its last managed generation`,
      },
    }
  }

  const currentStandardHash = await hashRecord(await hashTree(context.standardPresetDir))
  const outdated = state.packageVersion !== context.packageVersion
    || state.dshVersion !== context.dshVersion
    || state.profileName !== context.profileName
    || state.sourceStandardHash !== currentStandardHash
    || !sameConfig(state.config, config)
  return {
    state,
    status: outdated
      ? { kind: 'outdated', presetDir: target, message: `Unity preset "${config.id}" is managed but needs regeneration` }
      : { kind: 'clean', presetDir: target, message: `Unity preset "${config.id}" is installed and current` },
  }
}

async function generatePreset(context: PresetOperationContext, config: PresetConfig): Promise<string> {
  const root = userPresetRoot(context)
  const temp = join(root, `.${config.id}.tmp-${process.pid}-${randomUUID()}`)
  await cp(context.standardPresetDir, temp, { recursive: true, dereference: true, errorOnExist: true })
  try {
    const compositionPath = join(temp, COMPOSITION_FILE)
    const composition = await readFile(compositionPath, 'utf8')
    assertRowsAvailable(composition)
    const nextComposition = `${composition.trimEnd()}\n\n${renderUnityRows(context, config)}`
    await writeFile(compositionPath, nextComposition, 'utf8')
    await writeFile(
      join(temp, PRESET_METADATA_FILE),
      'name: Unity MCP\ndescription: Text-first Unity Editor automation through MCP for Unity 10.1.2.\n',
      'utf8',
    )
    await tightenTree(temp)
    const files = await hashTree(temp, new Set([STATE_FILE]))
    const sourceStandardHash = await hashRecord(await hashTree(context.standardPresetDir))
    const state: ManagedState = {
      formatVersion: PRESET_STATE_FORMAT_VERSION,
      packageName: PACKAGE_NAME,
      packageVersion: context.packageVersion,
      profileName: context.profileName,
      dshVersion: context.dshVersion,
      sourceStandardHash,
      config,
      files,
    }
    await writeFile(join(temp, STATE_FILE), `${JSON.stringify(state, undefined, 2)}\n`, { encoding: 'utf8', mode: 0o600 })
    return temp
  } catch (error) {
    await rm(temp, { recursive: true, force: true })
    throw error
  }
}

function renderUnityRows(context: PresetOperationContext, config: PresetConfig): string {
  const logicalSkillsDir = join(context.packageRoot, 'skills').replaceAll('\\', '/')
  const mcpClientPlugin = context.mcpClientPlugin.replaceAll('\\', '/')
  const skillFilesystemPlugin = context.skillFilesystemPlugin.replaceAll('\\', '/')
  const q = (value: string): string => JSON.stringify(value)
  return `# Unity MCP is preset-scoped: standard and sibling presets do not see these registrations.
- id: unity-mcp
  name: ${q(mcpClientPlugin)}
  config:
    transport: stdio
    serverName: ${q(config.serverName)}
    command: ${q(config.uvxCommand)}
    args:
      - --from
      - ${q(`mcpforunityserver==${MCP_SERVER_VERSION}`)}
      - mcp-for-unity
      - --transport
      - stdio
      - --project-scoped-tools
    env: {}
    cwd: ''
    toolCallTimeoutMs: ${config.toolCallTimeoutMs}
    failOnStartupError: true

- id: unity-skills
  name: ${q(skillFilesystemPlugin)}
  config:
    includeDefaultRoots: false
    customSkillDirs:
      - ${q(logicalSkillsDir)}
`
}

function assertRowsAvailable(composition: string): void {
  for (const id of ['unity-mcp', 'unity-skills']) {
    const pattern = new RegExp(`^\\s*-\\s+id:\\s*['\"]?${id}['\"]?\\s*$`, 'mu')
    if (pattern.test(composition)) {
      throw new Error(`The standard preset already contains row id "${id}"; refusing to generate an ambiguous composition`)
    }
  }
}

function validateInputs(context: PresetOperationContext, config: PresetConfig): void {
  if (!PRESET_ID_PATTERN.test(config.id)) {
    throw new Error(`Preset id must match ${PRESET_ID_PATTERN.source}`)
  }
  if (!SERVER_NAME_PATTERN.test(config.serverName)) {
    throw new Error(`MCP server name must match ${SERVER_NAME_PATTERN.source}`)
  }
  if (config.uvxCommand.trim() === '') throw new Error('uvx command must not be blank')
  if (!Number.isSafeInteger(config.toolCallTimeoutMs) || config.toolCallTimeoutMs <= 0) {
    throw new Error('tool call timeout must be a positive integer')
  }
  for (const [name, path] of Object.entries({
    dshHome: context.dshHome,
    profileDir: context.profileDir,
    standardPresetDir: context.standardPresetDir,
    packageRoot: context.packageRoot,
    mcpClientPlugin: context.mcpClientPlugin,
    skillFilesystemPlugin: context.skillFilesystemPlugin,
  })) {
    if (!isAbsolute(path)) throw new Error(`${name} must be an absolute path`)
  }
  const target = presetDir(context, config.id)
  assertDirectChild(userPresetRoot(context), target)
}

function userPresetRoot(context: PresetOperationContext): string {
  return resolve(context.dshHome, '.agent-presets')
}

function presetDir(context: PresetOperationContext, id: string): string {
  return resolve(userPresetRoot(context), id)
}

function assertDirectChild(parent: string, child: string): void {
  const rel = relative(resolve(parent), resolve(child))
  if (rel === '' || rel.startsWith(`..${sep}`) || rel === '..' || rel.includes(sep)) {
    throw new Error(`Preset target must be one direct child of ${parent}`)
  }
}

async function nextBackupPath(target: string): Promise<string> {
  const stamp = new Date().toISOString().replaceAll(':', '').replaceAll('.', '')
  for (let index = 0; ; index += 1) {
    const suffix = index === 0 ? '' : `-${index}`
    const candidate = `${target}.backup-${stamp}${suffix}`
    if (!await pathExists(candidate)) return candidate
  }
}

async function pathExists(path: string): Promise<boolean> {
  try {
    await lstat(path)
    return true
  } catch (error) {
    if (isNodeError(error, 'ENOENT')) return false
    throw error
  }
}

async function hashTree(root: string, excluded = new Set<string>()): Promise<Record<string, string>> {
  const output: Record<string, string> = {}
  await walk(root, '')
  return Object.fromEntries(Object.entries(output).sort(([left], [right]) => left.localeCompare(right)))

  async function walk(absolute: string, relativePath: string): Promise<void> {
    const entries = await readdir(absolute, { withFileTypes: true })
    entries.sort((left, right) => left.name.localeCompare(right.name))
    for (const entry of entries) {
      const nextRelative = relativePath === '' ? entry.name : `${relativePath}/${entry.name}`
      if (relativePath === '' && excluded.has(entry.name)) continue
      const nextAbsolute = join(absolute, entry.name)
      if (entry.isDirectory()) {
        await walk(nextAbsolute, nextRelative)
      } else if (entry.isSymbolicLink()) {
        output[nextRelative] = digest(`symlink\0${await readlink(nextAbsolute)}`)
      } else if (entry.isFile()) {
        output[nextRelative] = digest(await readFile(nextAbsolute))
      } else {
        output[nextRelative] = digest(`unsupported\0${entry.name}`)
      }
    }
  }
}

async function hashRecord(record: Record<string, string>): Promise<string> {
  return digest(JSON.stringify(record))
}

function digest(value: string | Buffer): string {
  return createHash('sha256').update(value).digest('hex')
}

function sameRecord(left: Record<string, string>, right: Record<string, string>): boolean {
  const leftEntries = Object.entries(left)
  const rightEntries = Object.entries(right)
  return leftEntries.length === rightEntries.length
    && leftEntries.every(([key, value]) => right[key] === value)
}

function sameConfig(left: PresetConfig, right: PresetConfig): boolean {
  return left.id === right.id
    && left.serverName === right.serverName
    && left.uvxCommand === right.uvxCommand
    && left.toolCallTimeoutMs === right.toolCallTimeoutMs
}

function parseManagedState(raw: string): ManagedState {
  const value: unknown = JSON.parse(raw)
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error('state must contain an object')
  }
  const state = value as Partial<ManagedState>
  if (state.formatVersion !== PRESET_STATE_FORMAT_VERSION || state.packageName !== PACKAGE_NAME) {
    throw new Error('state owner or format version is not recognized')
  }
  if (typeof state.packageVersion !== 'string' || typeof state.profileName !== 'string'
    || typeof state.dshVersion !== 'string' || typeof state.sourceStandardHash !== 'string') {
    throw new Error('state metadata is incomplete')
  }
  if (!isPresetConfig(state.config) || !isStringRecord(state.files)) {
    throw new Error('state config or file hashes are invalid')
  }
  return state as ManagedState
}

function isPresetConfig(value: unknown): value is PresetConfig {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const config = value as Partial<PresetConfig>
  return typeof config.id === 'string'
    && typeof config.serverName === 'string'
    && typeof config.uvxCommand === 'string'
    && typeof config.toolCallTimeoutMs === 'number'
}

function isStringRecord(value: unknown): value is Record<string, string> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    && Object.values(value).every(entry => typeof entry === 'string')
}

async function tightenTree(root: string): Promise<void> {
  await chmod(root, 0o700)
  const entries = await readdir(root, { withFileTypes: true })
  for (const entry of entries) {
    const path = join(root, entry.name)
    if (entry.isDirectory()) {
      await tightenTree(path)
    } else if (entry.isFile()) {
      await chmod(path, 0o600)
    }
  }
}

function isNodeError(error: unknown, code: string): error is NodeJS.ErrnoException {
  return error instanceof Error && (error as NodeJS.ErrnoException).code === code
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
