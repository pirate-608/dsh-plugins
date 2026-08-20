/** OpenAI-compatible chat-completions vision route. */

import { parseVisionResult, VISION_SCHEMA } from '../schema.js'
import type { OpenAiRouteConfig, RouteContext, VisionResult } from '../types.js'

export async function runOpenAi(config: OpenAiRouteConfig, context: RouteContext): Promise<{ result: VisionResult, model: string }> {
  const baseUrl = requiredUrl(config.baseUrl)
  if (config.credentialRef !== undefined && !/^[A-Za-z_][A-Za-z0-9_]*$/u.test(config.credentialRef)) {
    throw new Error('OpenAI credentialRef must be an environment-style identifier')
  }
  const credential = config.credentialRef === undefined
    ? undefined
    : await context.credentials?.resolve(config.credentialRef)
  if (config.credentialRef !== undefined && credential === undefined) {
    throw new Error(`OpenAI credential reference "${config.credentialRef}" is not configured`)
  }
  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(credential === undefined ? {} : { authorization: `Bearer ${credential.value}` }),
    },
    body: JSON.stringify({
      model: config.model,
      ...(config.structuredOutput === true ? { response_format: { type: 'json_schema', json_schema: { name: 'vision_evidence', strict: true, schema: VISION_SCHEMA } } } : {}),
      messages: [{ role: 'user', content: [
        { type: 'image_url', image_url: { url: `data:${context.image.mediaType};base64,${Buffer.from(context.image.data).toString('base64')}` } },
        { type: 'text', text: context.prompt },
      ] }],
      stream: false,
    }),
    signal: AbortSignal.any([context.signal, AbortSignal.timeout(context.timeoutMs)]),
  })
  if (!response.ok) throw new Error(`OpenAI-compatible route failed with HTTP ${response.status}: ${redact(await response.text(), baseUrl)}`)
  const payload = await response.json() as { choices?: Array<{ message?: { content?: string } }> }
  const content = payload.choices?.[0]?.message?.content
  if (typeof content !== 'string') throw new Error('OpenAI-compatible route returned no message content')
  return { result: parseVisionResult(content), model: config.model }
}

function requiredUrl(value: string): string {
  const url = new URL(value)
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('OpenAI baseUrl must use http(s)')
  return url.href.replace(/\/$/u, '')
}

function redact(value: string, baseUrl: string): string {
  return value.replaceAll(baseUrl, '[endpoint]').replace(/(?:sk|key|token)[-_A-Za-z0-9]{12,}/giu, '[redacted]').slice(0, 500)
}
