import { Context } from '@deepseek-ai/cordis'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import { describe, expect, it } from 'vitest'
import * as ModLens from '../src/index.js'

describe('assembled DSH registration', () => {
  it('registers a valid model-facing tool definition', async () => {
    const app = new Context()
    app.provide('fs', {})
    app.provide('attachments', {})
    await app.plugin(SystemPrompt, { persona: '' })
    await app.plugin(ToolRuntime)
    await app.plugin(ModLens as never, { routes: { ollama: { type: 'ollama', model: 'fixture' } } } as never)
    try {
      expect(app.tools.schemas().map(tool => tool.name)).toContain('modlens_read_image')
    } finally {
      await app.fiber.dispose()
    }
  })
})
