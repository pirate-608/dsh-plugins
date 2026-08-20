/** Native DSH text-first vision bridge. */

import { analyze } from './analyzer.js'
import { loadImage, savePaste } from './input.js'
import { VISION_SCHEMA } from './schema.js'
import type { Config, RouteId } from './types.js'

export type { Config, EvidenceEnvelope, RouteId, VisionResult } from './types.js'
export { analyze } from './analyzer.js'

interface ContextLike {
  tools: { register(definition: unknown): unknown }
  fs: Parameters<typeof loadImage>[0]['fs']
  attachments: Parameters<typeof loadImage>[0]['attachments']
  credentials?: { resolve(ref: string): Promise<{ value: string } | undefined> }
  llm?: {
    listProviders(): readonly { id?: string }[]
    listModels(provider: string): Promise<readonly { id?: string, name?: string, inputModalities?: readonly string[] }[]>
  }
  inject?(services: readonly string[], callback: (scope: ContextLike & { webServer: WebServerLike }) => void): unknown
}

interface WebServerLike {
  register(route: { name: string, kind: string, path: string, handler(req: AsyncIterable<Buffer> & { method?: string, url?: string, destroy(): void }, res: ResponseLike): Promise<void> }): unknown
}

interface ResponseLike {
  writeHead(status: number, headers?: Record<string, string>): ResponseLike
  end(body?: string): void
}

interface ExecLike {
  signal: AbortSignal
  agent?: Parameters<typeof loadImage>[2]['agent']
}

/** Required host services for the tool path. */
export const inject = ['tools', 'fs', 'attachments']

/** Register the logged vision tool and the conservative Web paste bridge. */
export function apply(ctx: ContextLike, config: Config = {}): void {
  validateConfig(config)
  const maxBytes = config.maxImageBytes ?? 25 * 1024 * 1024
  ctx.tools.register({
    name: 'modlens_read_image',
    description: 'Read one image through a text-first vision bridge. Use for a local path, an authorized session attachment, a private modlens paste reference, or an http(s) URL. Returns structured OCR, layout, semantics, visual evidence, uncertainty, provider provenance, and failover attempts.',
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'DSH-readable image path or modlens-paste reference' },
        url: { type: 'string', description: 'Public http(s) image URL' },
        attachmentId: { type: 'string', description: 'Attachment id already referenced by this session' },
        prompt: { type: 'string', description: 'Optional extra analysis focus' },
        route: { type: 'string', enum: ['codex', 'openai', 'ollama'], description: 'Pin one route with no fallback' },
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        required: ['image', 'provider', 'result', 'meta'],
        properties: {
          image: { type: 'object', additionalProperties: true },
          provider: { type: 'string', enum: ['codex', 'openai', 'ollama'] },
          result: VISION_SCHEMA,
          meta: { type: 'object', additionalProperties: true },
        },
      },
      render: (_args: unknown, value: unknown) => [{ type: 'text', text: JSON.stringify(value, undefined, 2) }],
    },
    timeoutMs: (config.timeoutMs ?? 180_000) + 20_000,
    isConcurrencySafe: () => true,
    presentCall: (args: { path?: string, url?: string, attachmentId?: string }) => ({
      card: 'generic', title: 'Read image with ModLens', kind: 'read', rawInput: args,
      ...(args.path !== undefined && !args.path.startsWith('modlens-paste:') ? { locations: [{ path: args.path }] } : {}),
    }),
    execute: async (args: { path?: string, url?: string, attachmentId?: string, prompt?: string, route?: RouteId }, exec: ExecLike) => {
      const image = await loadImage(
        ctx,
        args,
        exec.agent === undefined ? { signal: exec.signal } : { signal: exec.signal, agent: exec.agent },
        maxBytes,
      )
      return analyze(config, image, {
        ...(args.prompt === undefined ? {} : { prompt: args.prompt }),
        ...(args.route === undefined ? {} : { route: args.route }),
        signal: exec.signal,
        ...(ctx.credentials === undefined ? {} : { credentials: ctx.credentials }),
      })
    },
  })

  if (config.pasteToPath !== false && typeof ctx.inject === 'function') {
    ctx.inject(['webServer'], scope => registerPasteRoute(scope, ctx, maxBytes))
  }
}

function validateConfig(config: Config): void {
  if (config.timeoutMs !== undefined && (!Number.isSafeInteger(config.timeoutMs) || config.timeoutMs <= 0)) {
    throw new Error('timeoutMs must be a positive integer')
  }
  if (config.maxImageBytes !== undefined && (!Number.isSafeInteger(config.maxImageBytes) || config.maxImageBytes <= 0)) {
    throw new Error('maxImageBytes must be a positive integer')
  }
  const valid = new Set<RouteId>(['codex', 'openai', 'ollama'])
  if (config.failover !== undefined
    && (config.failover.length === 0 || new Set(config.failover).size !== config.failover.length
      || config.failover.some(route => !valid.has(route)))) {
    throw new Error('failover must contain unique codex/openai/ollama route ids')
  }
  if (config.routes?.codex !== undefined && config.routes.codex.type !== 'codex-cli') throw new Error('routes.codex.type must be codex-cli')
  if (config.routes?.openai !== undefined && config.routes.openai.type !== 'openai-compatible') throw new Error('routes.openai.type must be openai-compatible')
  if (config.routes?.ollama !== undefined && config.routes.ollama.type !== 'ollama') throw new Error('routes.ollama.type must be ollama')
}

function registerPasteRoute(scope: ContextLike & { webServer: WebServerLike }, host: ContextLike, maxBytes: number): void {
  scope.webServer.register({
    name: 'pirate-modlens-paste', kind: 'exact', path: '/modlens/paste',
    handler: async (req, res) => {
      if (req.method === 'GET') {
        const label = new URL(req.url ?? '/', 'http://localhost').searchParams.get('model') ?? ''
        res.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify({ takeover: await textOnlyLabel(host, label) }))
        return
      }
      if (req.method !== 'POST') { res.writeHead(405).end(); return }
      try {
        const chunks: Buffer[] = []
        let total = 0
        for await (const chunk of req) {
          total += chunk.length
          if (total > maxBytes) { res.writeHead(413).end(JSON.stringify({ error: `image exceeds ${maxBytes} bytes` })); req.destroy(); return }
          chunks.push(Buffer.from(chunk))
        }
        const path = await savePaste(new Uint8Array(Buffer.concat(chunks)), maxBytes)
        res.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify({ path }))
      } catch (error) {
        res.writeHead(400, { 'content-type': 'application/json' }).end(JSON.stringify({ error: error instanceof Error ? error.message : String(error) }))
      }
    },
  })
}

async function textOnlyLabel(ctx: ContextLike, label: string): Promise<boolean> {
  if (label.trim() === '' || ctx.llm === undefined) return false
  const lowered = label.toLowerCase()
  let matched = false
  for (const provider of ctx.llm.listProviders()) {
    if (provider.id === undefined) continue
    let models
    try { models = await ctx.llm.listModels(provider.id) } catch { return false }
    for (const model of models) {
      if (![model.id, model.name].some(value => typeof value === 'string' && value.length >= 3 && lowered.includes(value.toLowerCase()))) continue
      if (!Array.isArray(model.inputModalities)) return false
      if (model.inputModalities.includes('image')) return false
      matched = model.inputModalities.includes('text')
    }
  }
  return matched
}

export default apply
