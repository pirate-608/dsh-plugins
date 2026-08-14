#!/usr/bin/env node

/** Command-line entry for managed Unity agent presets. */

import { createRequire } from 'node:module'
import { homedir } from 'node:os'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readFile } from 'node:fs/promises'
import {
  DEFAULT_PRESET_CONFIG,
  installPreset,
  presetStatus,
  removePreset,
  updatePreset,
  type PresetConfig,
  type PresetOperationContext,
} from './preset.js'
import { PACKAGE_VERSION } from './constants.js'

interface CliOptions extends PresetConfig {
  profile?: string
  force: boolean
}

const HELP = `Usage:
  dsh-unity-mcp preset install [options]
  dsh-unity-mcp preset update [options]
  dsh-unity-mcp preset status [options]
  dsh-unity-mcp preset remove [options]

Options:
  --profile <name>          DSH profile (default: infer from current directory)
  --id <id>                 Agent preset id (default: unity)
  --server-name <name>      MCP tool namespace (default: unity)
  --uvx-command <path>      uvx executable or absolute path (default: uvx)
  --tool-timeout-ms <ms>    MCP tool-call timeout (default: 300000)
  --force                   Back up local changes before update/remove
  -h, --help                Show this help
`

async function main(argv: readonly string[]): Promise<number> {
  if (argv.includes('--help') || argv.includes('-h')) {
    process.stdout.write(HELP)
    return 0
  }
  if (argv[0] !== 'preset' || !['install', 'update', 'status', 'remove'].includes(argv[1] ?? '')) {
    process.stderr.write(HELP)
    return 2
  }
  const action = argv[1] as 'install' | 'update' | 'status' | 'remove'
  const options = parseOptions(argv.slice(2))
  const context = await resolveContext(options.profile)
  const config: PresetConfig = {
    id: options.id,
    serverName: options.serverName,
    uvxCommand: options.uvxCommand,
    toolCallTimeoutMs: options.toolCallTimeoutMs,
  }

  switch (action) {
    case 'install': {
      const result = await installPreset(context, config)
      process.stdout.write(`Installed Unity MCP preset at ${result.presetDir}\n`)
      return 0
    }
    case 'update': {
      const result = await updatePreset(context, config, options.force)
      process.stdout.write(`Updated Unity MCP preset at ${result.presetDir}\n`)
      if (result.backupDir !== undefined) process.stdout.write(`Preserved local changes at ${result.backupDir}\n`)
      return 0
    }
    case 'status': {
      const status = await presetStatus(context, config)
      process.stdout.write(`${status.kind}: ${status.message}\n${status.presetDir}\n`)
      return status.kind === 'clean' ? 0 : 1
    }
    case 'remove': {
      const result = await removePreset(context, config, options.force)
      if (!result.removed) {
        process.stdout.write(`Unity MCP preset "${config.id}" is not installed\n`)
      } else if (result.backupDir !== undefined) {
        process.stdout.write(`Removed Unity MCP preset and preserved local changes at ${result.backupDir}\n`)
      } else {
        process.stdout.write(`Removed Unity MCP preset "${config.id}"\n`)
      }
      return 0
    }
  }
}

function parseOptions(argv: readonly string[]): CliOptions {
  const options: CliOptions = { ...DEFAULT_PRESET_CONFIG, force: false }
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    switch (arg) {
      case '--force':
        options.force = true
        break
      case '--profile':
        options.profile = requireValue(argv, ++index, arg)
        break
      case '--id':
        options.id = requireValue(argv, ++index, arg)
        break
      case '--server-name':
        options.serverName = requireValue(argv, ++index, arg)
        break
      case '--uvx-command':
        options.uvxCommand = requireValue(argv, ++index, arg)
        break
      case '--tool-timeout-ms': {
        const raw = requireValue(argv, ++index, arg)
        options.toolCallTimeoutMs = Number(raw)
        break
      }
      default:
        throw new Error(`Unknown option: ${arg}`)
    }
  }
  return options
}

function requireValue(argv: readonly string[], index: number, option: string): string {
  const value = argv[index]
  if (value === undefined || value.startsWith('-')) throw new Error(`${option} requires a value`)
  return value
}

async function resolveContext(profileOption: string | undefined): Promise<PresetOperationContext> {
  const dshHome = resolve(process.env.DSH_HOME ?? join(homedir(), '.dsh'))
  const profileDir = profileOption === undefined
    ? resolve(process.cwd())
    : resolve(dshHome, 'profiles', profileOption)
  const profileManifest = JSON.parse(await readFile(join(profileDir, 'package.json'), 'utf8')) as {
    name?: string
    dsh?: { profile?: unknown }
  }
  if (profileManifest.dsh?.profile === undefined) {
    throw new Error(`${profileDir} is not a DSH profile; run this command through "dsh plugin --profile <name> exec" or pass --profile`)
  }
  const profileName = profileOption ?? profileManifest.name?.replace(/^dsh-profile-/, '') ?? basename(profileDir)
  const requireFromProfile = createRequire(join(profileDir, 'package.json'))
  const dshManifestPath = requireFromProfile.resolve('@deepseek-ai/dsh/package.json')
  const dshManifest = JSON.parse(await readFile(dshManifestPath, 'utf8')) as { version?: string }
  if (typeof dshManifest.version !== 'string') throw new Error(`Invalid DSH package manifest at ${dshManifestPath}`)
  const requireFromDsh = createRequire(dshManifestPath)
  const packageRoot = fileURLToPath(new URL('../', import.meta.url))
  return {
    dshHome,
    profileName,
    profileDir,
    standardPresetDir: join(dirname(dshManifestPath), 'config', 'agent-presets', 'standard'),
    packageRoot,
    mcpClientPlugin: requireFromDsh.resolve('@deepseek-ai/dsh-mcp-client'),
    skillFilesystemPlugin: requireFromDsh.resolve('@deepseek-ai/dsh-skill-filesystem'),
    packageVersion: PACKAGE_VERSION,
    dshVersion: dshManifest.version,
  }
}

main(process.argv.slice(2)).then(
  code => { process.exitCode = code },
  error => {
    process.stderr.write(`dsh-unity-mcp: ${error instanceof Error ? error.message : String(error)}\n`)
    process.exitCode = 1
  },
)
