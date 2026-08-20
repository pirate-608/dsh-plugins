import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { installPreset, presetStatus, removePreset, updatePreset } from '../src/preset.js'
import type { PresetContext, PresetSpec } from '../src/types.js'

const roots: string[] = []

afterEach(async () => {
  await Promise.all(roots.splice(0).map(root => rm(root, { recursive: true, force: true })))
})

async function fixture(): Promise<{ spec: PresetSpec, context: PresetContext }> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-plugin-kit-'))
  roots.push(root)
  const standardPresetDir = join(root, 'dsh', 'standard')
  const packageRoot = join(root, 'package')
  await mkdir(join(packageRoot, 'skills'), { recursive: true })
  await mkdir(standardPresetDir, { recursive: true })
  await writeFile(join(standardPresetDir, 'agent.cordis.yml'), '- id: base\n  name: noop\n')
  const spec: PresetSpec = {
    packageName: '@pirate-608/example',
    packageVersion: '1.0.0',
    id: 'example',
    name: 'Example',
    description: 'Example preset.',
    providerName: 'example-skills',
    mcpServers: [{ id: 'example-mcp', serverName: 'example', command: 'node', args: ['server.js'] }],
    policy: {
      serverNames: ['example'],
      readOnly: ['mcp__example__read'],
      ask: ['mcp__example__write'],
      deny: ['mcp__example__erase'],
    },
  }
  const context: PresetContext = {
    dshHome: join(root, 'home'),
    profileName: 'web',
    profileDir: join(root, 'home', 'profiles', 'web'),
    standardPresetDir,
    packageRoot,
    mcpClientPlugin: join(root, 'plugins', 'mcp.js'),
    skillFilesystemPlugin: join(root, 'plugins', 'skills.js'),
    policyPlugin: join(root, 'plugins', 'policy.js'),
    dshVersion: '0.1.0-rc.8',
  }
  return { spec, context }
}

describe('managed preset kit', () => {
  it('installs a scoped composition and detects drift', async () => {
    const { spec, context } = await fixture()
    const installed = await installPreset(spec, context)
    const composition = await readFile(join(installed.presetDir, 'agent.cordis.yml'), 'utf8')
    expect(composition).toContain('providerName: "example-skills"')
    expect(composition).toContain('serverName: "example"')
    expect(composition).toContain('mcp__example__read')
    await expect(presetStatus(spec, context)).resolves.toMatchObject({ kind: 'clean' })
    await expect(presetStatus({ ...spec, packageVersion: '2.0.0' }, context)).resolves.toMatchObject({ kind: 'outdated' })
  })

  it('protects local changes during update and removal', async () => {
    const { spec, context } = await fixture()
    const installed = await installPreset(spec, context)
    await writeFile(join(installed.presetDir, 'mine.txt'), 'mine')
    await expect(updatePreset(spec, context)).rejects.toThrow(/--force/)
    const updated = await updatePreset(spec, context, true)
    expect(updated.backupDir).toBeDefined()
    await writeFile(join(updated.presetDir, 'mine-again.txt'), 'mine')
    await expect(removePreset(spec, context)).rejects.toThrow(/--force/)
    const removed = await removePreset(spec, context, true)
    expect(removed.backupDir).toBeDefined()
  })
})
