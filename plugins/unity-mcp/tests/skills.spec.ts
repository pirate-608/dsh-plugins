import { readFile, readdir } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const PACKAGE_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const SKILLS_ROOT = join(PACKAGE_ROOT, 'skills')

async function markdownFiles(root: string): Promise<string[]> {
  const output: string[] = []
  await walk(root)
  return output

  async function walk(dir: string): Promise<void> {
    const entries = await readdir(dir, { withFileTypes: true })
    for (const entry of entries) {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) await walk(path)
      else if (entry.isFile() && entry.name.endsWith('.md')) output.push(path)
    }
  }
}

describe('DSH Unity skills', () => {
  it('ships ten direct skill bundles and no Codex agent metadata', async () => {
    const entries = await readdir(SKILLS_ROOT, { withFileTypes: true })
    const skillDirs = entries.filter(entry => entry.isDirectory()).map(entry => entry.name).sort()
    expect(skillDirs).toHaveLength(10)
    for (const name of skillDirs) {
      const files = await readdir(join(SKILLS_ROOT, name))
      expect(files).toContain('SKILL.md')
      expect(files).not.toContain('agents')
      const skill = await readFile(join(SKILLS_ROOT, name, 'SKILL.md'), 'utf8')
      expect(skill).toMatch(/^---\nname: [a-z0-9-]+\ndescription: .+\n---\n/u)
    }
  })

  it('contains no executable resource or inline-image guidance', async () => {
    const files = await markdownFiles(SKILLS_ROOT)
    const corpus = (await Promise.all(files.map(file => readFile(file, 'utf8')))).join('\n')
    expect(corpus).not.toContain('mcpforunity://')
    expect(corpus).not.toMatch(/include_image\s*=\s*(?:true|True)/u)
    expect(corpus).toContain('Visual verification pending')
    expect(corpus).toContain('A path proves that an artifact was created, not that its contents are correct.')
  })

  it('qualifies direct Unity MCP call examples with the DSH server namespace', async () => {
    const files = await markdownFiles(SKILLS_ROOT)
    const corpus = (await Promise.all(files.map(file => readFile(file, 'utf8')))).join('\n')
    const unqualifiedCall = /(?<!mcp__unity__)\b(?:manage_[a-z_]+|read_console|run_tests|get_test_job|refresh_unity|set_active_instance|unity_reflect|unity_docs|execute_code|render_ui|batch_execute)\s*\(/gu
    expect([...corpus.matchAll(unqualifiedCall)].map(match => match[0])).toEqual([])
    expect(corpus).toContain('"tool": "find_gameobjects"')
  })
})
