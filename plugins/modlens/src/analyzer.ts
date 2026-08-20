/** Three-route failover and evidence caching. */

import { parseVisionResult, visionPrompt } from './schema.js'
import { runCodex } from './routes/codex.js'
import { runOllama } from './routes/ollama.js'
import { runOpenAi } from './routes/openai.js'
import type { Attempt, Config, EvidenceEnvelope, ImagePayload, RouteContext, RouteId } from './types.js'

const DEFAULT_FAILOVER: readonly RouteId[] = ['codex', 'openai', 'ollama']
const cache = new Map<string, Promise<EvidenceEnvelope>>()
const routeTails = new Map<RouteId, Promise<void>>()

export async function analyze(
  config: Config,
  image: ImagePayload,
  options: { prompt?: string, route?: RouteId, signal: AbortSignal, credentials?: RouteContext['credentials'] },
): Promise<EvidenceEnvelope> {
  const routes = options.route === undefined ? validateFailover(config.failover ?? DEFAULT_FAILOVER) : [options.route]
  const key = JSON.stringify({ hash: image.sha256, prompt: options.prompt ?? '', routes, config: config.routes })
  let pending = cache.get(key)
  if (pending === undefined) {
    pending = run(config, image, routes, options)
    cache.set(key, pending)
    void pending.catch(() => { if (cache.get(key) === pending) cache.delete(key) })
    if (cache.size > 64) cache.delete(cache.keys().next().value!)
  }
  return pending
}

async function run(
  config: Config,
  image: ImagePayload,
  routes: readonly RouteId[],
  options: { prompt?: string, signal: AbortSignal, credentials?: RouteContext['credentials'] },
): Promise<EvidenceEnvelope> {
  const attempts: Attempt[] = []
  const context: RouteContext = {
    image,
    prompt: visionPrompt(options.prompt),
    signal: options.signal,
    timeoutMs: config.timeoutMs ?? 180_000,
    ...(options.credentials === undefined ? {} : { credentials: options.credentials }),
  }
  for (const route of routes) {
    const started = Date.now()
    try {
      const configured = config.routes?.[route]
      if (configured === undefined) throw new Error(`${route} route is not configured`)
      const output = await inRouteLane(route, context.signal, async () => route === 'codex'
        ? runCodex(configured as never, context)
        : route === 'openai'
          ? runOpenAi(configured as never, context)
          : runOllama(configured as never, context))
      attempts.push({ route, durationMs: Date.now() - started })
      return {
        image: { source: safeSource(image.source), mediaType: image.mediaType, bytes: image.data.byteLength, sha256: image.sha256 },
        provider: route,
        result: parseVisionResult(output.result),
        meta: { model: output.model, attempts, warnings: route === 'codex' ? ['This read reused the local Codex CLI login and may spend remote account quota.'] : [] },
      }
    } catch (error) {
      attempts.push({ route, durationMs: Date.now() - started, error: safeError(error) })
    }
  }
  throw new Error(`No vision route succeeded: ${attempts.map(item => `${item.route}: ${item.error}`).join('; ')}`)
}

async function inRouteLane<T>(route: RouteId, signal: AbortSignal, operation: () => Promise<T>): Promise<T> {
  if (route === 'openai') return operation()
  const previous = routeTails.get(route) ?? Promise.resolve()
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const tail = previous.catch(() => undefined).then(() => gate)
  routeTails.set(route, tail)
  try {
    await waitFor(previous, signal)
    return await operation()
  } finally {
    release()
    if (routeTails.get(route) === tail) routeTails.delete(route)
  }
}

function waitFor(promise: Promise<void>, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(signal.reason)
  return new Promise((resolve, reject) => {
    const abort = (): void => { cleanup(); reject(signal.reason) }
    const cleanup = (): void => signal.removeEventListener('abort', abort)
    signal.addEventListener('abort', abort, { once: true })
    void promise.then(() => { cleanup(); resolve() }, error => { cleanup(); reject(error) })
  })
}

function validateFailover(value: readonly RouteId[]): readonly RouteId[] {
  if (value.length === 0 || new Set(value).size !== value.length || value.some(route => !DEFAULT_FAILOVER.includes(route))) {
    throw new Error('failover must contain unique codex/openai/ollama route ids')
  }
  return value
}

function safeError(error: unknown): string {
  return (error instanceof Error ? error.message : String(error))
    .replace(/https?:\/\/[^\s"']+/giu, '[endpoint]')
    .replace(/Bearer\s+\S+/giu, 'Bearer [redacted]')
    .replace(/(?:sk|key|token)[-_A-Za-z0-9]{12,}/giu, '[redacted]')
    .slice(0, 500)
}

function safeSource(source: string): string {
  if (!/^https?:\/\//iu.test(source)) return source
  try { return `remote:${new URL(source).hostname}` } catch { return 'remote:[invalid]' }
}
