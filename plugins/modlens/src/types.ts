/** Supported route ids in their default failover order. */
export type RouteId = 'codex' | 'openai' | 'ollama'

export interface CodexRouteConfig {
  type: 'codex-cli'
  consent: boolean
  command?: string
  model?: string
}

export interface OpenAiRouteConfig {
  type: 'openai-compatible'
  baseUrl: string
  model: string
  credentialRef?: string
  structuredOutput?: boolean
}

export interface OllamaRouteConfig {
  type: 'ollama'
  baseUrl?: string
  model: string
}

/** DSH plugin configuration. */
export interface Config {
  routes?: {
    codex?: CodexRouteConfig
    openai?: OpenAiRouteConfig
    ollama?: OllamaRouteConfig
  }
  failover?: readonly RouteId[]
  timeoutMs?: number
  maxImageBytes?: number
  pasteToPath?: boolean
}

export interface VisionResult {
  summary: string
  ocr: { full_text: string, lines: unknown[] }
  layout: { regions: unknown[] }
  semantics: Record<string, unknown>
  visual: Record<string, unknown>
  uncertainty: unknown[]
}

export interface ImagePayload {
  data: Uint8Array
  mediaType: string
  source: string
  sha256: string
}

export interface Attempt {
  route: RouteId
  durationMs: number
  error?: string
}

export interface EvidenceEnvelope {
  image: { source: string, mediaType: string, bytes: number, sha256: string }
  provider: RouteId
  result: VisionResult
  meta: { model: string | null, attempts: Attempt[], warnings: string[] }
}

export interface RouteContext {
  signal: AbortSignal
  timeoutMs: number
  prompt: string
  image: ImagePayload
  credentials?: { resolve(ref: string): Promise<{ value: string } | undefined> }
}
