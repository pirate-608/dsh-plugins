/** Bounded image admission for DSH files, attachments, pastes, and remote URLs. */

import { createHash, randomUUID } from 'node:crypto'
import { chmod, mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises'
import { lookup } from 'node:dns/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { isIP } from 'node:net'
import type { ImagePayload } from './types.js'

const PASTE_ROOT = join(tmpdir(), 'dsh-modlens-paste')
const pastes = new Map<string, { path: string, createdAt: number }>()
const MAX_REDIRECTS = 5

interface ContextLike {
  fs: {
    resolve(path: string, options?: { cwd?: string, signal?: AbortSignal }): Promise<unknown>
    readBytes(target: unknown, signal: AbortSignal | undefined, maxBytes: number): Promise<Uint8Array>
  }
  attachments: { readImage(ref: unknown, signal?: AbortSignal): Promise<{ ref: { mediaType: string }, data: Uint8Array }> }
}

interface ExecLike {
  signal: AbortSignal
  agent?: { session?: { events?: readonly unknown[], cwd?: string, meta?: { cwd?: string } } }
}

export async function loadImage(
  ctx: ContextLike,
  args: { path?: string, url?: string, attachmentId?: string },
  exec: ExecLike,
  maxBytes: number,
): Promise<ImagePayload> {
  const choices = [args.path, args.url, args.attachmentId].filter(value => typeof value === 'string' && value.length > 0)
  if (choices.length !== 1) throw new Error('provide exactly one of path, url, or attachmentId')
  if (args.attachmentId !== undefined) {
    const ref = findAttachment(exec.agent?.session?.events ?? [], args.attachmentId)
    if (ref === undefined) throw new Error('attachmentId is not referenced by this session')
    const stored = await ctx.attachments.readImage(ref, exec.signal)
    if (stored.data.byteLength > maxBytes) throw new Error(`image exceeds ${maxBytes} bytes`)
    return admitted(stored.data, stored.ref.mediaType, `attachment:${args.attachmentId}`)
  }
  if (args.url !== undefined) {
    const remote = await fetchImage(args.url, exec.signal, maxBytes)
    return admitted(remote.data, remote.mediaType, args.url)
  }
  const path = args.path!
  if (path.startsWith('modlens-paste:')) {
    const record = pastes.get(path.slice('modlens-paste:'.length))
    if (record === undefined) throw new Error('paste reference is missing or expired')
    const data = new Uint8Array(await readFile(record.path))
    return admitted(data, sniff(data), path)
  }
  const cwd = exec.agent?.session?.cwd ?? exec.agent?.session?.meta?.cwd
  const target = await ctx.fs.resolve(path, { ...(cwd === undefined ? {} : { cwd }), signal: exec.signal })
  const data = await ctx.fs.readBytes(target, exec.signal, maxBytes)
  return admitted(data, sniff(data), path)
}

export async function savePaste(data: Uint8Array, maxBytes: number): Promise<string> {
  if (data.byteLength > maxBytes) throw new Error(`image exceeds ${maxBytes} bytes`)
  const mediaType = sniff(data)
  await mkdir(PASTE_ROOT, { recursive: true, mode: 0o700 })
  await chmod(PASTE_ROOT, 0o700)
  const id = randomUUID()
  const path = join(PASTE_ROOT, `${id}.${extension(mediaType)}`)
  await writeFile(path, data, { mode: 0o600 })
  pastes.set(id, { path, createdAt: Date.now() })
  void sweepPastes()
  return `modlens-paste:${id}`
}

async function sweepPastes(): Promise<void> {
  const cutoff = Date.now() - 60 * 60 * 1000
  for (const [id, record] of pastes) {
    if (record.createdAt >= cutoff) continue
    pastes.delete(id)
    await rm(record.path, { force: true }).catch(() => undefined)
  }
  let entries: string[]
  try { entries = await readdir(PASTE_ROOT) } catch { return }
  await Promise.all(entries.map(async entry => {
    const path = join(PASTE_ROOT, entry)
    try { if ((await stat(path)).mtimeMs < cutoff) await rm(path, { force: true }) } catch { /* best-effort private temp cleanup */ }
  }))
}

async function fetchImage(urlText: string, signal: AbortSignal, maxBytes: number): Promise<{ data: Uint8Array, mediaType: string }> {
  let current = new URL(urlText)
  for (let redirects = 0; redirects <= MAX_REDIRECTS; redirects += 1) {
    if (!['http:', 'https:'].includes(current.protocol)) throw new Error('only http(s) image URLs are supported')
    await assertPublicHost(current.hostname)
    const response = await fetch(current, { signal, redirect: 'manual' })
    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get('location')
      if (location === null) throw new Error('image redirect has no location')
      current = new URL(location, current)
      continue
    }
    if (!response.ok) throw new Error(`image download failed with HTTP ${response.status}`)
    const declared = Number(response.headers.get('content-length') ?? '0')
    if (declared > maxBytes) throw new Error(`image exceeds ${maxBytes} bytes`)
    if (response.body === null) throw new Error('image response has no body')
    const reader = response.body.getReader()
    const chunks: Uint8Array[] = []
    let total = 0
    for (;;) {
      const next = await reader.read()
      if (next.done) break
      total += next.value.byteLength
      if (total > maxBytes) {
        await reader.cancel()
        throw new Error(`image exceeds ${maxBytes} bytes`)
      }
      chunks.push(next.value)
    }
    const data = new Uint8Array(total)
    let offset = 0
    for (const chunk of chunks) { data.set(chunk, offset); offset += chunk.byteLength }
    return { data, mediaType: sniff(data) }
  }
  throw new Error('image URL exceeded redirect limit')
}

async function assertPublicHost(hostname: string): Promise<void> {
  const addresses = isIP(hostname) === 0 ? (await lookup(hostname, { all: true })).map(item => item.address) : [hostname]
  if (addresses.length === 0 || addresses.some(privateAddress)) throw new Error('image URL resolves to a private or local address')
}

function privateAddress(address: string): boolean {
  const lower = address.toLowerCase()
  if (lower === '::1' || lower.startsWith('fe80:') || lower.startsWith('fc') || lower.startsWith('fd')) return true
  const mapped = /^::ffff:(\d+\.\d+\.\d+\.\d+)$/u.exec(lower)?.[1]
  const ip = mapped ?? lower
  const parts = ip.split('.').map(Number)
  if (parts.length !== 4 || parts.some(Number.isNaN)) return false
  const [a = 0, b = 0] = parts
  return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)
}

function admitted(data: Uint8Array, mediaType: string, source: string): ImagePayload {
  return { data, mediaType, source, sha256: createHash('sha256').update(data).digest('hex') }
}

export function sniff(data: Uint8Array): string {
  const b = Buffer.from(data)
  if (b.length >= 8 && b.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return 'image/png'
  if (b.length >= 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return 'image/jpeg'
  if (b.length >= 6 && ['GIF87a', 'GIF89a'].includes(b.toString('ascii', 0, 6))) return 'image/gif'
  if (b.length >= 12 && b.toString('ascii', 0, 4) === 'RIFF' && b.toString('ascii', 8, 12) === 'WEBP') return 'image/webp'
  throw new Error('input is not a recognized PNG, JPEG, GIF, or WebP image')
}

function extension(mediaType: string): string {
  return ({ 'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif', 'image/webp': 'webp' })[mediaType] ?? 'bin'
}

function findAttachment(events: readonly unknown[], id: string): unknown | undefined {
  const visit = (value: unknown): unknown | undefined => {
    if (typeof value !== 'object' || value === null) return undefined
    if (Array.isArray(value)) {
      for (const item of value) { const found = visit(item); if (found !== undefined) return found }
      return undefined
    }
    const record = value as Record<string, unknown>
    const attachment = record.attachment
    if (typeof attachment === 'object' && attachment !== null
      && String((attachment as Record<string, unknown>).attachmentId) === id) return attachment
    for (const child of Object.values(record)) { const found = visit(child); if (found !== undefined) return found }
    return undefined
  }
  return visit(events)
}
