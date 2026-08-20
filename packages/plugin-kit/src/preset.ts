/** Managed standard-derived preset lifecycle. */

import { createHash, randomUUID } from 'node:crypto'
import { chmod, cp, lstat, mkdir, readFile, readdir, readlink, rename, rm, writeFile } from 'node:fs/promises'
import { isAbsolute, join, relative, resolve, sep } from 'node:path'
import type { PresetContext, PresetSpec, PresetStatus, PresetWriteResult } from './types.js'

const STATE_FILE = '.dsh-plugin-kit.json'
const COMPOSITION_FILE = 'agent.cordis.yml'
const PRESET_METADATA_FILE = 'preset.yml'
const ID_PATTERN = /^[a-z0-9][a-z0-9-]*$/
const SERVER_PATTERN = /^[A-Za-z0-9_-]{1,32}$/

interface ManagedState {
  formatVersion: 1
  packageName: string
  packageVersion: string
  profileName: string
  dshVersion: string
  sourceStandardHash: string
  specHash: string
  files: Record<string, string>
}

/** Install a managed preset without overwriting an existing directory. */
export async function installPreset(spec: PresetSpec, context: PresetContext): Promise<PresetWriteResult> {
  validate(spec, context)
  const target = presetDir(context, spec.id)
  if (await pathExists(target)) throw new Error(`Preset "${spec.id}" already exists at ${target}`)
  await mkdir(userPresetRoot(context), { recursive: true })
  const temp = await generatePreset(spec, context)
  try {
    await rename(temp, target)
  } catch (error) {
    await rm(temp, { recursive: true, force: true })
    throw error
  }
  return { presetDir: target }
}

/** Rebuild a managed preset from the active DSH standard preset. */
export async function updatePreset(
  spec: PresetSpec,
  context: PresetContext,
  force = false,
): Promise<PresetWriteResult> {
  validate(spec, context)
  const status = await presetStatus(spec, context)
  if (status.kind === 'absent') throw new Error(`${status.message}; run preset install first`)
  if (status.kind === 'invalid') throw new Error(`${status.message}; refusing to replace an unowned directory`)
  if (status.kind === 'modified' && !force) {
    throw new Error(`${status.message}; re-run with --force to preserve a backup`)
  }
  const target = presetDir(context, spec.id)
  const temp = await generatePreset(spec, context)
  const displaced = status.kind === 'modified'
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
    if (status.kind !== 'modified') {
      await rm(displaced, { recursive: true, force: true })
      return { presetDir: target }
    }
    return { presetDir: target, backupDir: displaced }
  } catch (error) {
    await rm(temp, { recursive: true, force: true })
    throw error
  }
}

/** Remove a clean preset or preserve a modified one when force is explicit. */
export async function removePreset(
  spec: PresetSpec,
  context: PresetContext,
  force = false,
): Promise<{ removed: boolean, backupDir?: string }> {
  validate(spec, context)
  const status = await presetStatus(spec, context)
  if (status.kind === 'absent') return { removed: false }
  if (status.kind === 'invalid') throw new Error(`${status.message}; refusing to remove an unowned directory`)
  const target = presetDir(context, spec.id)
  if (status.kind === 'modified') {
    if (!force) throw new Error(`${status.message}; re-run with --force to preserve a backup`)
    const backupDir = await nextBackupPath(target)
    await rename(target, backupDir)
    return { removed: true, backupDir }
  }
  await rm(target, { recursive: true })
  return { removed: true }
}

/** Inspect ownership, local changes, host drift, and specification drift. */
export async function presetStatus(spec: PresetSpec, context: PresetContext): Promise<PresetStatus> {
  validate(spec, context)
  const target = presetDir(context, spec.id)
  if (!await pathExists(target)) {
    return { kind: 'absent', presetDir: target, message: `Preset "${spec.id}" is not installed` }
  }
  let state: ManagedState
  try {
    state = parseState(await readFile(join(target, STATE_FILE), 'utf8'), spec.packageName)
  } catch (error) {
    return { kind: 'invalid', presetDir: target, message: `Preset "${spec.id}" has no valid owner state: ${message(error)}` }
  }
  const currentFiles = await hashTree(target, new Set([STATE_FILE]))
  if (!sameRecord(currentFiles, state.files)) {
    return { kind: 'modified', presetDir: target, message: `Preset "${spec.id}" contains local changes` }
  }
  const standardHash = digest(JSON.stringify(await hashTree(context.standardPresetDir)))
  const outdated = state.packageVersion !== spec.packageVersion
    || state.dshVersion !== context.dshVersion
    || state.profileName !== context.profileName
    || state.sourceStandardHash !== standardHash
    || state.specHash !== specHash(spec)
  return outdated
    ? { kind: 'outdated', presetDir: target, message: `Preset "${spec.id}" needs regeneration` }
    : { kind: 'clean', presetDir: target, message: `Preset "${spec.id}" is installed and current` }
}

async function generatePreset(spec: PresetSpec, context: PresetContext): Promise<string> {
  const root = userPresetRoot(context)
  const temp = join(root, `.${spec.id}.tmp-${process.pid}-${randomUUID()}`)
  await cp(context.standardPresetDir, temp, { recursive: true, dereference: true, errorOnExist: true })
  try {
    const compositionPath = join(temp, COMPOSITION_FILE)
    const composition = await readFile(compositionPath, 'utf8')
    const rowIds = generatedRowIds(spec)
    assertRowsAvailable(composition, rowIds)
    await writeFile(compositionPath, `${composition.trimEnd()}\n\n${renderRows(spec, context)}`, 'utf8')
    await writeFile(
      join(temp, PRESET_METADATA_FILE),
      `name: ${yaml(spec.name)}\ndescription: ${yaml(spec.description)}\n`,
      'utf8',
    )
    await tightenTree(temp)
    const files = await hashTree(temp, new Set([STATE_FILE]))
    const state: ManagedState = {
      formatVersion: 1,
      packageName: spec.packageName,
      packageVersion: spec.packageVersion,
      profileName: context.profileName,
      dshVersion: context.dshVersion,
      sourceStandardHash: digest(JSON.stringify(await hashTree(context.standardPresetDir))),
      specHash: specHash(spec),
      files,
    }
    await writeFile(join(temp, STATE_FILE), `${JSON.stringify(state, undefined, 2)}\n`, { encoding: 'utf8', mode: 0o600 })
    return temp
  } catch (error) {
    await rm(temp, { recursive: true, force: true })
    throw error
  }
}

/** Render plugin rows appended to the standard preset. */
export function renderRows(spec: PresetSpec, context: PresetContext): string {
  const rows: string[] = []
  const skillsDir = resolve(context.packageRoot, spec.skillsDir ?? 'skills').replaceAll('\\', '/')
  rows.push(`- id: ${spec.id}-skills\n  name: ${yaml(context.skillFilesystemPlugin.replaceAll('\\', '/'))}\n  config:\n    providerName: ${yaml(spec.providerName)}\n    includeDefaultRoots: false\n    customSkillDirs:\n      - ${yaml(skillsDir)}\n`)
  for (const server of spec.mcpServers ?? []) {
    rows.push(`- id: ${server.id}\n  name: ${yaml(context.mcpClientPlugin.replaceAll('\\', '/'))}\n  config:\n    transport: stdio\n    serverName: ${yaml(server.serverName)}\n    command: ${yaml(server.command)}\n    args:${yamlList(server.args ?? [])}\n    env:${yamlRecord(server.env ?? {})}\n    cwd: ${yaml(resolveRuntimePath(context.packageRoot, server.cwd ?? ''))}\n    toolCallTimeoutMs: ${server.toolCallTimeoutMs ?? 300_000}\n    failOnStartupError: ${server.failOnStartupError ?? true}\n`)
  }
  if (spec.policy !== undefined) {
    rows.push(`- id: ${spec.id}-mcp-policy\n  name: ${yaml(context.policyPlugin.replaceAll('\\', '/'))}\n  config:\n    serverNames:${yamlList(spec.policy.serverNames)}\n    readOnly:${yamlList(spec.policy.readOnly ?? [])}\n    ask:${yamlList(spec.policy.ask ?? [])}\n    deny:${yamlList(spec.policy.deny ?? [])}\n`)
  }
  return `${rows.join('\n')}\n`
}

function resolveRuntimePath(packageRoot: string, value: string): string {
  if (value === '') return ''
  return isAbsolute(value) ? value : resolve(packageRoot, value)
}

function yaml(value: string): string {
  return JSON.stringify(value)
}

function yamlList(values: readonly string[]): string {
  return values.length === 0 ? ' []' : `\n${values.map(value => `      - ${yaml(value)}`).join('\n')}`
}

function yamlRecord(values: Readonly<Record<string, string>>): string {
  const entries = Object.entries(values)
  return entries.length === 0 ? ' {}' : `\n${entries.map(([key, value]) => `      ${key}: ${yaml(value)}`).join('\n')}`
}

function generatedRowIds(spec: PresetSpec): string[] {
  return [`${spec.id}-skills`, ...(spec.mcpServers ?? []).map(server => server.id), ...(spec.policy === undefined ? [] : [`${spec.id}-mcp-policy`])]
}

function assertRowsAvailable(composition: string, ids: readonly string[]): void {
  for (const id of ids) {
    if (new RegExp(`^\\s*-\\s+id:\\s*['\"]?${id}['\"]?\\s*$`, 'mu').test(composition)) {
      throw new Error(`Standard preset already contains row id "${id}"`)
    }
  }
}

function validate(spec: PresetSpec, context: PresetContext): void {
  if (!ID_PATTERN.test(spec.id)) throw new Error(`Preset id must match ${ID_PATTERN.source}`)
  if (!ID_PATTERN.test(spec.providerName)) throw new Error(`Provider name must match ${ID_PATTERN.source}`)
  if (spec.platform !== undefined && spec.platform !== process.platform) {
    throw new Error(`Preset "${spec.id}" requires ${spec.platform}; current platform is ${process.platform}`)
  }
  for (const server of spec.mcpServers ?? []) {
    if (!ID_PATTERN.test(server.id)) throw new Error(`MCP row id must match ${ID_PATTERN.source}`)
    if (!SERVER_PATTERN.test(server.serverName)) throw new Error(`Invalid MCP server name "${server.serverName}"`)
    if (server.command.trim() === '') throw new Error(`MCP server "${server.id}" command must not be blank`)
  }
  for (const [name, value] of Object.entries(context)) {
    if (name === 'profileName' || name === 'dshVersion') continue
    if (!isAbsolute(value)) throw new Error(`${name} must be an absolute path`)
  }
  assertDirectChild(userPresetRoot(context), presetDir(context, spec.id))
}

function userPresetRoot(context: PresetContext): string {
  return resolve(context.dshHome, '.agent-presets')
}

function presetDir(context: PresetContext, id: string): string {
  return resolve(userPresetRoot(context), id)
}

function assertDirectChild(parent: string, child: string): void {
  const rel = relative(resolve(parent), resolve(child))
  if (rel === '' || rel === '..' || rel.startsWith(`..${sep}`) || rel.includes(sep)) {
    throw new Error(`Preset target must be one direct child of ${parent}`)
  }
}

function specHash(spec: PresetSpec): string {
  return digest(JSON.stringify(spec))
}

function parseState(raw: string, packageName: string): ManagedState {
  const value: unknown = JSON.parse(raw)
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new Error('state must be an object')
  const state = value as Partial<ManagedState>
  if (state.formatVersion !== 1 || state.packageName !== packageName || typeof state.packageVersion !== 'string'
    || typeof state.profileName !== 'string' || typeof state.dshVersion !== 'string'
    || typeof state.sourceStandardHash !== 'string' || typeof state.specHash !== 'string'
    || !isStringRecord(state.files)) throw new Error('state owner or fields are invalid')
  return state as ManagedState
}

async function nextBackupPath(target: string): Promise<string> {
  const stamp = new Date().toISOString().replaceAll(':', '').replaceAll('.', '')
  for (let index = 0; ; index += 1) {
    const candidate = `${target}.backup-${stamp}${index === 0 ? '' : `-${index}`}`
    if (!await pathExists(candidate)) return candidate
  }
}

async function pathExists(path: string): Promise<boolean> {
  try {
    await lstat(path)
    return true
  } catch (error) {
    if (error instanceof Error && (error as NodeJS.ErrnoException).code === 'ENOENT') return false
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
      if (entry.isDirectory()) await walk(nextAbsolute, nextRelative)
      else if (entry.isSymbolicLink()) output[nextRelative] = digest(`symlink\0${await readlink(nextAbsolute)}`)
      else if (entry.isFile()) output[nextRelative] = digest(await readFile(nextAbsolute))
      else output[nextRelative] = digest(`unsupported\0${entry.name}`)
    }
  }
}

function digest(value: string | Buffer): string {
  return createHash('sha256').update(value).digest('hex')
}

function sameRecord(left: Record<string, string>, right: Record<string, string>): boolean {
  const entries = Object.entries(left)
  return entries.length === Object.keys(right).length && entries.every(([key, value]) => right[key] === value)
}

async function tightenTree(root: string): Promise<void> {
  await chmod(root, 0o700)
  for (const entry of await readdir(root, { withFileTypes: true })) {
    const path = join(root, entry.name)
    if (entry.isDirectory()) await tightenTree(path)
    else if (entry.isFile()) await chmod(path, 0o600)
  }
}

function isStringRecord(value: unknown): value is Record<string, string> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    && Object.values(value).every(entry => typeof entry === 'string')
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
