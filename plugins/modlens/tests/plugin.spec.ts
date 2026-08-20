import { createServer, type Server } from 'node:http'
import { once } from 'node:events'
import { afterEach, describe, expect, it } from 'vitest'
import apply from '../src/index.js'
import type { VisionResult } from '../src/types.js'

const servers: Server[] = []
afterEach(async () => {
  await Promise.all(servers.splice(0).map(server => new Promise<void>(resolve => server.close(() => resolve()))))
})

describe('DSH tool plugin', () => {
  it('reads an authorized attachment and returns a text-safe evidence envelope', async () => {
    const evidence: VisionResult = {
      summary: 'one pixel', ocr: { full_text: '', lines: [] }, layout: { regions: [] },
      semantics: {}, visual: { color: 'black' }, uncertainty: [],
    }
    const server = createServer((_request, response) => {
      response.setHeader('content-type', 'application/json')
      response.end(JSON.stringify({ message: { content: JSON.stringify(evidence) }, model: 'fixture' }))
    })
    servers.push(server)
    server.listen(0, '127.0.0.1')
    await once(server, 'listening')
    const address = server.address()
    if (address === null || typeof address === 'string') throw new Error('missing port')

    let tool: { name: string, execute(args: unknown, exec: unknown): Promise<unknown> } | undefined
    const attachment = { attachmentId: 'fixture-id', mediaType: 'image/png' }
    const ctx = {
      tools: { register(value: unknown) { tool = value as typeof tool } },
      fs: { resolve: () => Promise.reject(new Error('unused')), readBytes: () => Promise.reject(new Error('unused')) },
      attachments: { readImage: async () => ({ ref: attachment, data: Uint8Array.of(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a) }) },
    }
    apply(ctx as never, { routes: { ollama: { type: 'ollama', baseUrl: `http://127.0.0.1:${address.port}`, model: 'fixture' } }, failover: ['ollama'] })
    if (tool === undefined) throw new Error('tool was not registered')
    expect(tool.name).toBe('modlens_read_image')
    const output = await tool.execute({ attachmentId: 'fixture-id' }, {
      signal: new AbortController().signal,
      agent: { session: { events: [{ data: { content: [{ type: 'image', attachment }] } }] } },
    })
    expect(output).toMatchObject({ provider: 'ollama', result: evidence })
    expect(JSON.stringify(output)).not.toContain('iVBOR')
  })
})
