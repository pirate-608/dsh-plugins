/** Native Ollama vision and structured-output route. */

import { parseVisionResult, VISION_SCHEMA } from '../schema.js'
import type { OllamaRouteConfig, RouteContext, VisionResult } from '../types.js'

export async function runOllama(config: OllamaRouteConfig, context: RouteContext): Promise<{ result: VisionResult, model: string }> {
  const baseUrl = loopbackUrl(config.baseUrl ?? 'http://127.0.0.1:11434')
  const response = await fetch(`${baseUrl}/api/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      model: config.model,
      stream: false,
      format: VISION_SCHEMA,
      messages: [{ role: 'user', content: context.prompt, images: [Buffer.from(context.image.data).toString('base64')] }],
    }),
    signal: AbortSignal.any([context.signal, AbortSignal.timeout(context.timeoutMs)]),
  })
  if (!response.ok) throw new Error(`Ollama route failed with HTTP ${response.status}: ${(await response.text()).slice(0, 500)}`)
  const payload = await response.json() as { message?: { content?: string }, model?: string }
  if (typeof payload.message?.content !== 'string') throw new Error('Ollama route returned no message content')
  return { result: parseVisionResult(payload.message.content), model: payload.model ?? config.model }
}

function loopbackUrl(value: string): string {
  const url = new URL(value)
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '::1', '[::1]'].includes(url.hostname)) {
    throw new Error('Ollama baseUrl must be loopback HTTP')
  }
  return url.href.replace(/\/$/u, '')
}
