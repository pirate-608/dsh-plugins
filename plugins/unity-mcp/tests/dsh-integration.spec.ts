import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { Context } from '@deepseek-ai/cordis'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import Include from '@deepseek-ai/cordis-plugin-include'
import LlmRuntime, { CallId } from '@deepseek-ai/dsh-llm'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import AgentRegistry, { type Agent } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import AgentPresets from '@deepseek-ai/dsh-agent-presets'
import SkillRuntime from '@deepseek-ai/dsh-skill'
import { scopeOf } from '@deepseek-ai/dsh-scope'
import { afterEach, describe, expect, it } from 'vitest'
import { installPreset, type PresetOperationContext } from '../src/preset.js'

const PACKAGE_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const requireHere = createRequire(import.meta.url)
const FIXTURE_SERVER = join(PACKAGE_ROOT, 'tests', 'fixtures', 'mcp-server.mjs')
const roots: string[] = []

afterEach(async () => {
  await Promise.all(roots.splice(0).map(root => rm(root, { recursive: true, force: true })))
})

describe('assembled DSH preset', () => {
  it('keeps Unity tools and skills scoped and renders MCP images as text placeholders', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-unity-integration-'))
    roots.push(root)
    const standardPresetDir = join(root, 'standard')
    const dshHome = join(root, 'home')
    await mkdir(standardPresetDir, { recursive: true })
    await writeFile(join(standardPresetDir, 'noop.mjs'), 'export default () => {}\n')
    await writeFile(join(standardPresetDir, 'agent.cordis.yml'), '- id: noop\n  name: ./noop.mjs\n')
    const context: PresetOperationContext = {
      dshHome,
      profileName: 'web',
      profileDir: join(dshHome, 'profiles', 'web'),
      standardPresetDir,
      packageRoot: PACKAGE_ROOT,
      mcpClientPlugin: requireHere.resolve('@deepseek-ai/dsh-mcp-client'),
      skillFilesystemPlugin: requireHere.resolve('@deepseek-ai/dsh-skill-filesystem'),
      packageVersion: '0.1.0',
      dshVersion: '0.1.0-rc.6',
    }
    const installed = await installPreset(context)
    const compositionPath = join(installed.presetDir, 'agent.cordis.yml')
    const generated = await readFile(compositionPath, 'utf8')
    const fixtureTransport = [
      `    command: ${JSON.stringify(process.execPath)}`,
      '    args:',
      `      - ${JSON.stringify(FIXTURE_SERVER.replaceAll('\\', '/'))}`,
      '',
    ].join('\n')
    const withFixture = generated.replace(
      /    command: .*\n    args:\n(?:      - .*\n)+/u,
      fixtureTransport,
    )
    expect(withFixture).not.toBe(generated)
    await writeFile(compositionPath, withFixture)

    const plainDir = join(dshHome, '.agent-presets', 'plain')
    await mkdir(plainDir, { recursive: true })
    await writeFile(join(plainDir, 'noop.mjs'), 'export default () => {}\n')
    await writeFile(join(plainDir, 'agent.cordis.yml'), '- id: noop\n  name: ./noop.mjs\n')

    const app = new Context()
    app.baseUrl = pathToFileURL(PACKAGE_ROOT).href + '/'
    await app.plugin(Loader)
    app.loader.builtins.include = Include
    await app.plugin(LlmRuntime)
    await app.plugin(SessionStore)
    await app.plugin(SystemPrompt, { persona: '' })
    await app.plugin(ToolRuntime)
    await app.plugin(SkillRuntime)
    await app.plugin(AgentRegistry)
    await app.plugin(AgentLoop, { agents: [] })
    await app.plugin(AgentPresets, {
      default: 'plain',
      roots: [{ path: join(dshHome, '.agent-presets'), trust: 'user' }],
      includeUserRoot: false,
    })

    try {
      const plain = await agentOn(app, 'plain-agent', 'plain')
      expect(app.tools.schemas(plain).map(tool => tool.name)).not.toContain('mcp__unity__scene_summary')
      expect(await app.skills.list({ scope: scopeOf(plain.ctx) })).toEqual([])

      const unity = await agentOn(app, 'unity-agent', 'unity')
      expect(app.tools.schemas(unity).map(tool => tool.name).sort()).toEqual([
        'mcp__unity__scene_summary',
        'mcp__unity__screenshot',
      ])
      const skillNames = (await app.skills.list({ scope: scopeOf(unity.ctx) })).map(skill => skill.name)
      expect(skillNames).toHaveLength(10)
      expect(skillNames).toContain('unity-mcp-orchestrator')

      const screenshot = await app.tools.execute({
        signal: new AbortController().signal,
        callId: CallId('image-fallback'),
        name: 'mcp__unity__screenshot',
        arguments: {},
        agent: unity,
      })
      expect(screenshot.isError).toBe(false)
      expect(screenshot.content).toEqual([{
        type: 'text',
        text: 'Saved screenshot: Assets/Screenshots/fixture.png\n[image: image/png, content discarded]',
      }])
    } finally {
      await app.fiber.dispose()
    }
  }, 30_000)
})

async function agentOn(ctx: Context, session: string, preset: string): Promise<Agent> {
  const handle = await ctx.agents.create({
    sessionId: SessionId(session),
    setup: async (agentCtx: Context) => void await ctx.agentPresets.mount(agentCtx, preset),
  })
  return handle.agent
}
