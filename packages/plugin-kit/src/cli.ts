/** Shared CLI and DSH profile resolution for managed plugin presets. */

import { spawnSync } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { homedir } from 'node:os'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { installPreset, presetStatus, removePreset, updatePreset } from './preset.js'
import type { PresetContext, PresetSpec } from './types.js'

/** Resolve active DSH and companion plugin paths for a package CLI. */
export async function resolvePresetContext(
  profileOption: string | undefined,
  packageRoot: string,
): Promise<PresetContext> {
  const dshHome = resolve(process.env.DSH_HOME ?? join(homedir(), '.dsh'))
  const profileDir = profileOption === undefined ? resolve(process.cwd()) : resolve(dshHome, 'profiles', profileOption)
  const manifest = JSON.parse(await readFile(join(profileDir, 'package.json'), 'utf8')) as {
    name?: string
    dsh?: { profile?: unknown }
  }
  if (manifest.dsh?.profile === undefined) throw new Error(`${profileDir} is not a DSH profile`)
  const profileName = profileOption ?? manifest.name?.replace(/^dsh-profile-/, '') ?? basename(profileDir)
  const requireFromProfile = createRequire(join(profileDir, 'package.json'))
  const dshManifestPath = requireFromProfile.resolve('@deepseek-ai/dsh/package.json')
  const dshManifest = JSON.parse(await readFile(dshManifestPath, 'utf8')) as { version?: string }
  if (typeof dshManifest.version !== 'string') throw new Error(`Invalid DSH manifest at ${dshManifestPath}`)
  const requireFromDsh = createRequire(dshManifestPath)
  return {
    dshHome,
    profileName,
    profileDir,
    standardPresetDir: join(dirname(dshManifestPath), 'config', 'agent-presets', 'standard'),
    packageRoot: resolve(packageRoot),
    mcpClientPlugin: requireFromDsh.resolve('@deepseek-ai/dsh-mcp-client'),
    skillFilesystemPlugin: requireFromDsh.resolve('@deepseek-ai/dsh-skill-filesystem'),
    policyPlugin: fileURLToPath(new URL('./policy.js', import.meta.url)),
    dshVersion: dshManifest.version,
  }
}

/** Run the standard preset lifecycle and doctor commands for one plugin. */
export async function runPluginCli(
  input: PresetSpec | readonly PresetSpec[],
  argv: readonly string[],
  packageRoot: string,
): Promise<number> {
  const specs = Array.isArray(input) ? input : [input]
  const displaySpec = specs[0]
  if (displaySpec === undefined) throw new Error('Plugin must declare at least one preset')
  if (argv.includes('--help') || argv.includes('-h') || argv.length === 0) {
    process.stdout.write(help(specs))
    return 0
  }
  const parsed = parse(argv)
  if (parsed.command === 'doctor') return doctor(specs)
  if (parsed.command === 'runtime') return runtime(specs, parsed.action, packageRoot)
  const spec = parsed.presetId === undefined
    ? displaySpec
    : specs.find(candidate => candidate.id === parsed.presetId)
  if (spec === undefined) throw new Error(`Unknown preset "${parsed.presetId}"`)
  const context = await resolvePresetContext(parsed.profile, packageRoot)
  switch (parsed.action) {
    case 'install': {
      const result = await installPreset(spec, context)
      process.stdout.write(`Installed ${spec.name} preset at ${result.presetDir}\n`)
      return 0
    }
    case 'update': {
      const result = await updatePreset(spec, context, parsed.force)
      process.stdout.write(`Updated ${spec.name} preset at ${result.presetDir}\n`)
      if (result.backupDir !== undefined) process.stdout.write(`Preserved local changes at ${result.backupDir}\n`)
      return 0
    }
    case 'status': {
      const result = await presetStatus(spec, context)
      process.stdout.write(`${result.kind}: ${result.message}\n${result.presetDir}\n`)
      return result.kind === 'clean' ? 0 : 1
    }
    case 'remove': {
      const result = await removePreset(spec, context, parsed.force)
      process.stdout.write(result.backupDir === undefined
        ? `${result.removed ? 'Removed' : 'Not installed'}: ${spec.id}\n`
        : `Removed ${spec.id}; preserved local changes at ${result.backupDir}\n`)
      return 0
    }
  }
  throw new Error('Unsupported preset action')
}

type PresetAction = 'install' | 'update' | 'status' | 'remove'
type Parsed =
  | { command: 'doctor', force: false }
  | { command: 'runtime', action: 'install' | 'status' | 'remove', force: false }
  | { command: 'preset', action: PresetAction, profile?: string, presetId?: string, force: boolean }

function parse(argv: readonly string[]): Parsed {
  if (argv[0] === 'doctor') return { command: 'doctor', force: false }
  if (argv[0] === 'runtime' && ['install', 'status', 'remove'].includes(argv[1] ?? '')) {
    return { command: 'runtime', action: argv[1] as 'install' | 'status' | 'remove', force: false }
  }
  if (argv[0] !== 'preset' || !['install', 'update', 'status', 'remove'].includes(argv[1] ?? '')) {
    throw new Error('Expected "preset install|update|status|remove" or "doctor"')
  }
  const parsed: Extract<Parsed, { command: 'preset' }> = {
    command: 'preset',
    action: argv[1] as PresetAction,
    force: false,
  }
  for (let index = 2; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--force') parsed.force = true
    else if (arg === '--profile') parsed.profile = requireValue(argv, ++index, arg)
    else if (arg === '--preset') parsed.presetId = requireValue(argv, ++index, arg)
    else throw new Error(`Unknown option: ${arg}`)
  }
  return parsed
}

function requireValue(argv: readonly string[], index: number, option: string): string {
  const value = argv[index]
  if (value === undefined || value.startsWith('-')) throw new Error(`${option} requires a value`)
  return value
}

function doctor(specs: readonly PresetSpec[]): number {
  const requiredPlatform = specs.find(spec => spec.platform !== undefined)?.platform
  if (requiredPlatform !== undefined && requiredPlatform !== process.platform) {
    process.stderr.write(`FAIL platform: requires ${requiredPlatform}, found ${process.platform}\n`)
    return 1
  }
  let failed = false
  const probes = new Map(specs.flatMap(spec => spec.doctor ?? []).map(probe => [probe.label, probe]))
  for (const probe of probes.values()) {
    const result = spawnSync(probe.command, [...(probe.args ?? ['--version'])], {
      encoding: 'utf8',
      windowsHide: true,
      timeout: 15_000,
    })
    const ok = result.status === 0 && result.error === undefined
    process.stdout.write(`${ok ? 'OK' : probe.optional === true ? 'OPTIONAL' : 'FAIL'} ${probe.label}\n`)
    if (!ok && probe.optional !== true) failed = true
  }
  return failed ? 1 : 0
}

function runtime(specs: readonly PresetSpec[], action: 'install' | 'status' | 'remove', packageRoot: string): number {
  const command = specs.map(spec => spec.runtime?.[action]).find(value => value !== undefined)
  if (command === undefined) throw new Error(`runtime ${action} is not provided by this package`)
  const result = spawnSync(command.command, [...(command.args ?? [])], {
    cwd: resolve(packageRoot, command.cwd ?? ''),
    stdio: 'inherit',
    windowsHide: true,
  })
  if (result.error !== undefined) throw result.error
  return result.status ?? 1
}

function help(specs: readonly PresetSpec[]): string {
  const first = specs[0]
  if (first === undefined) return ''
  const choices = specs.map(spec => spec.id).join('|')
  const command = first.commandName ?? `dsh-${first.id}`
  return `Usage:\n  ${command} preset <install|update|status|remove> [--profile <name>] [--preset <${choices}>] [--force]\n  ${command} doctor\n  ${command} runtime <install|status|remove>\n`
}

/** Resolve a package root from a CLI module URL. */
export function packageRootFrom(importMetaUrl: string): string {
  return fileURLToPath(new URL('../', importMetaUrl))
}
