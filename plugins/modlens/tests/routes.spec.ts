import { createServer, type Server } from 'node:http'
import { once } from 'node:events'
import { afterEach, describe, expect, it } from 'vitest'
import { analyze } from '../src/analyzer.js'
import { extractFinalMessage } from '../src/routes/codex.js'
import { parseVisionResult } from '../src/schema.js'
import type { ImagePayload, VisionResult } from '../src/types.js'

const servers: Server[] = []
const result: VisionResult = {
  summary: 'fixture',
  ocr: { full_text: 'hello', lines: [] },
  layout: { regions: [] },
  semantics: {},
  visual: {},
  uncertainty: [],
}
const image: ImagePayload = {
  data: Uint8Array.of(1, 2, 3),
  mediaType: 'image/png',
  source: 'fixture.png',
  sha256: 'fixture-hash',
}

afterEach(async () => {
  await Promise.all(servers.splice(0).map(server => new Promise<void>(resolve => server.close(() => resolve()))))
})

describe('vision routes', () => {
  it('parses Codex NDJSON final messages', () => {
    const text = JSON.stringify(result)
    expect(extractFinalMessage([
      JSON.stringify({ type: 'thread.started', thread_id: 't' }),
      JSON.stringify({ type: 'item.completed', item: { type: 'agent_message', text } }),
    ].join('\n'))).toBe(text)
    expect(parseVisionResult(text)).toEqual(result)
  })

  it('uses the exact codex-openai-ollama failover order', async () => {
    const server = createServer((request, response) => {
      if (request.url !== '/api/chat') { response.writeHead(404).end(); return }
      response.setHeader('content-type', 'application/json')
      response.end(JSON.stringify({ model: 'fixture-vision', message: { content: JSON.stringify(result) } }))
    })
    servers.push(server)
    server.listen(0, '127.0.0.1')
    await once(server, 'listening')
    const address = server.address()
    if (address === null || typeof address === 'string') throw new Error('missing server port')
    const output = await analyze({
      routes: {
        codex: { type: 'codex-cli', consent: false },
        openai: { type: 'openai-compatible', baseUrl: 'http://127.0.0.1:1', model: 'missing' },
        ollama: { type: 'ollama', baseUrl: `http://127.0.0.1:${address.port}`, model: 'fixture-vision' },
      },
      failover: ['codex', 'openai', 'ollama'],
      timeoutMs: 2_000,
    }, image, { signal: new AbortController().signal })
    expect(output.provider).toBe('ollama')
    expect(output.meta.attempts.map(attempt => attempt.route)).toEqual(['codex', 'openai', 'ollama'])
    expect(output.result).toEqual(result)
  })

  it('pins one OpenAI-compatible route without fallback', async () => {
    const server = createServer((request, response) => {
      if (request.url !== '/v1/chat/completions') { response.writeHead(404).end(); return }
      response.setHeader('content-type', 'application/json')
      response.end(JSON.stringify({ choices: [{ message: { content: JSON.stringify(result) } }] }))
    })
    servers.push(server)
    server.listen(0, '127.0.0.1')
    await once(server, 'listening')
    const address = server.address()
    if (address === null || typeof address === 'string') throw new Error('missing server port')
    const output = await analyze({ routes: {
      openai: { type: 'openai-compatible', baseUrl: `http://127.0.0.1:${address.port}/v1`, model: 'fixture' },
    } }, { ...image, sha256: 'openai-hash' }, {
      route: 'openai', signal: new AbortController().signal,
    })
    expect(output.provider).toBe('openai')
    expect(output.meta.attempts).toHaveLength(1)
  })
})
