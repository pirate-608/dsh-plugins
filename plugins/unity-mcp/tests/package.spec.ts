import { readFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')

describe('package metadata', () => {
  it('declares an inert DSH bundle and public preset CLI', async () => {
    const manifest = JSON.parse(await readFile(join(ROOT, 'package.json'), 'utf8')) as {
      name: string
      bin: Record<string, string>
      dsh: { bundle: { patch: string } }
      dependencies?: Record<string, string>
      peerDependencies: Record<string, string>
    }
    expect(manifest.name).toBe('@pirate-608/dsh-unity-mcp')
    expect(manifest.bin).toEqual({ 'dsh-unity-mcp': 'lib/cli.js' })
    expect(manifest.dsh.bundle.patch).toBe('./cordis.patch.yml')
    expect(manifest.dependencies).toEqual({ '@pirate-608/dsh-plugin-kit': 'workspace:^' })
    expect(manifest.peerDependencies['@deepseek-ai/dsh']).toBe('>=0.0.1-rc.5 <0.2.0')
    await expect(readFile(join(ROOT, 'cordis.patch.yml'), 'utf8')).resolves.toBe('[]\n')
  })
})
