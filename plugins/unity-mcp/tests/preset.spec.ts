import { mkdtemp, mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  DEFAULT_PRESET_CONFIG,
  installPreset,
  presetStatus,
  removePreset,
  updatePreset,
  type PresetOperationContext,
} from '../src/preset.js'

let root: string
let context: PresetOperationContext

beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), 'dsh-unity-mcp-'))
  const dshHome = join(root, 'home')
  const profileDir = join(dshHome, 'profiles', 'web')
  const standardPresetDir = join(root, 'dsh', 'config', 'agent-presets', 'standard')
  const packageRoot = join(profileDir, 'node_modules', '@pirate-608', 'dsh-unity-mcp')
  await mkdir(profileDir, { recursive: true })
  await mkdir(standardPresetDir, { recursive: true })
  await mkdir(join(packageRoot, 'skills'), { recursive: true })
  await writeFile(join(standardPresetDir, 'agent.cordis.yml'), [
    '# fixture standard',
    '- id: persona',
    "  name: '@deepseek-ai/dsh-persona'",
    '- id: conditional',
    "  name: '@deepseek-ai/dsh-tool-pwsh'",
    "  disabled: !!js process.platform !== 'win32'",
    '',
  ].join('\n'))
  await writeFile(join(standardPresetDir, 'preset.yml'), 'name: Standard\n')
  context = {
    dshHome,
    profileName: 'web',
    profileDir,
    standardPresetDir,
    packageRoot,
    mcpClientPlugin: join(root, 'plugins', 'dsh-mcp-client.js'),
    skillFilesystemPlugin: join(root, 'plugins', 'dsh-skill-filesystem.js'),
    packageVersion: '0.1.0',
    dshVersion: '0.1.0-rc.6',
  }
})

afterEach(async () => {
  const { rm } = await import('node:fs/promises')
  await rm(root, { recursive: true, force: true })
})

describe('managed Unity preset lifecycle', () => {
  it('derives standard and appends scoped MCP and skill rows', async () => {
    const result = await installPreset(context)
    const composition = await readFile(join(result.presetDir, 'agent.cordis.yml'), 'utf8')

    expect(composition).toContain('# fixture standard')
    expect(composition).toContain('- id: unity-mcp')
    expect(composition).toContain('name: "')
    expect(composition).toContain('/plugins/dsh-mcp-client.js"')
    expect(composition).toContain('serverName: "unity"')
    expect(composition).toContain('mcpforunityserver==10.1.2')
    expect(composition).toContain('--project-scoped-tools')
    expect(composition).toContain('failOnStartupError: true')
    expect(composition).toContain('- id: unity-skills')
    expect(composition).toContain('/plugins/dsh-skill-filesystem.js"')
    expect(composition).toContain('includeDefaultRoots: false')
    await expect(presetStatus(context)).resolves.toMatchObject({ kind: 'clean' })
  })

  it('never overwrites an existing preset during install', async () => {
    await installPreset(context)
    await expect(installPreset(context)).rejects.toThrow(/already exists/)
  })

  it('detects package, DSH, config, and standard-preset drift', async () => {
    await installPreset(context)
    await expect(presetStatus({ ...context, packageVersion: '0.2.0' })).resolves.toMatchObject({ kind: 'outdated' })
    await expect(presetStatus({ ...context, dshVersion: '0.1.0-rc.7' })).resolves.toMatchObject({ kind: 'outdated' })
    await expect(presetStatus(context, { ...DEFAULT_PRESET_CONFIG, toolCallTimeoutMs: 42 }))
      .resolves.toMatchObject({ kind: 'outdated' })
    await writeFile(join(context.standardPresetDir, 'new-file.txt'), 'new standard generation')
    await expect(presetStatus(context)).resolves.toMatchObject({ kind: 'outdated' })
  })

  it('refuses modified content and backs it up before a forced update', async () => {
    const installed = await installPreset(context)
    await writeFile(join(installed.presetDir, 'local-note.md'), 'keep me')
    await expect(presetStatus(context)).resolves.toMatchObject({ kind: 'modified' })
    await expect(updatePreset(context)).rejects.toThrow(/--force/)

    const updated = await updatePreset(context, { ...DEFAULT_PRESET_CONFIG }, true)
    expect(updated.backupDir).toBeDefined()
    await expect(readFile(join(updated.backupDir!, 'local-note.md'), 'utf8')).resolves.toBe('keep me')
    await expect(presetStatus(context)).resolves.toMatchObject({ kind: 'clean' })
  })

  it('updates an unchanged preset without leaving replacement directories', async () => {
    await installPreset(context)
    await writeFile(join(context.standardPresetDir, 'generation.txt'), 'next')
    const updated = await updatePreset(context)

    expect(updated.backupDir).toBeUndefined()
    await expect(readFile(join(updated.presetDir, 'generation.txt'), 'utf8')).resolves.toBe('next')
    const siblings = await readdir(join(context.dshHome, '.agent-presets'))
    expect(siblings).toEqual(['unity'])
  })

  it('removes clean content and preserves modified content on force', async () => {
    await installPreset(context)
    await expect(removePreset(context)).resolves.toEqual({ removed: true })
    await expect(presetStatus(context)).resolves.toMatchObject({ kind: 'absent' })

    const installed = await installPreset(context)
    await writeFile(join(installed.presetDir, 'mine.txt'), 'mine')
    await expect(removePreset(context)).rejects.toThrow(/--force/)
    const removed = await removePreset(context, { ...DEFAULT_PRESET_CONFIG }, true)
    expect(removed.backupDir).toBeDefined()
    await expect(readFile(join(removed.backupDir!, 'mine.txt'), 'utf8')).resolves.toBe('mine')
    await expect(presetStatus(context)).resolves.toMatchObject({ kind: 'absent' })
  })

  it('rejects unowned, escaping, and conflicting targets', async () => {
    const target = join(context.dshHome, '.agent-presets', 'unity')
    await mkdir(target, { recursive: true })
    await writeFile(join(target, 'agent.cordis.yml'), '[]\n')
    await expect(updatePreset(context, { ...DEFAULT_PRESET_CONFIG }, true)).rejects.toThrow(/unowned/)
    await expect(removePreset(context, { ...DEFAULT_PRESET_CONFIG }, true)).rejects.toThrow(/unowned/)
    await expect(installPreset(context, { ...DEFAULT_PRESET_CONFIG, id: '../escape' })).rejects.toThrow(/Preset id/)

    context = { ...context, dshHome: join(root, 'other-home') }
    await mkdir(context.standardPresetDir, { recursive: true })
    await writeFile(join(context.standardPresetDir, 'agent.cordis.yml'), '- id: unity-mcp\n  name: noop\n')
    await expect(installPreset(context)).rejects.toThrow(/already contains row id/)
  })
})
