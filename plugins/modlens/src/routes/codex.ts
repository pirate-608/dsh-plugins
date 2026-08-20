/** Ephemeral, read-only Codex CLI vision route. */

import { spawn } from 'node:child_process'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { parseVisionResult, visionPrompt } from '../schema.js'
import type { CodexRouteConfig, RouteContext, VisionResult } from '../types.js'

export async function runCodex(config: CodexRouteConfig, context: RouteContext): Promise<{ result: VisionResult, model: string | null }> {
  if (config.consent !== true) throw new Error('Codex reuse requires explicit consent')
  const workdir = await mkdtemp(join(tmpdir(), 'dsh-modlens-codex-'))
  const image = join(workdir, `input.${extension(context.image.mediaType)}`)
  await writeFile(image, context.image.data, { mode: 0o600 })
  try {
    const args = ['exec', '--skip-git-repo-check', '--ephemeral', '-s', 'read-only', '--json', '-i', image]
    if (config.model !== undefined) args.push('-m', config.model)
    args.push('--', context.prompt)
    const stdout = await run(config.command ?? 'codex', args, workdir, context.signal, context.timeoutMs)
    return { result: parseVisionResult(extractFinalMessage(stdout)), model: config.model ?? null }
  } finally {
    await rm(workdir, { recursive: true, force: true, maxRetries: 1 })
  }
}

function run(command: string, args: string[], cwd: string, signal: AbortSignal, timeoutMs: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, windowsHide: true, detached: process.platform !== 'win32', stdio: ['ignore', 'pipe', 'pipe'] })
    let stdout = ''
    let stderr = ''
    let settled = false
    const finish = (error?: Error): void => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      signal.removeEventListener('abort', abort)
      if (error !== undefined) reject(error)
      else resolve(stdout)
    }
    const abort = (): void => { terminate(child); finish(new Error('Codex route aborted')) }
    const timer = setTimeout(() => { terminate(child); finish(new Error(`Codex route timed out after ${timeoutMs} ms`)) }, timeoutMs)
    signal.addEventListener('abort', abort, { once: true })
    child.stdout.setEncoding('utf8').on('data', chunk => { stdout += String(chunk) })
    child.stderr.setEncoding('utf8').on('data', chunk => { stderr += String(chunk) })
    child.on('error', error => finish(error))
    child.on('close', code => finish(code === 0 ? undefined : new Error(`Codex route failed with code ${code}: ${redact(stderr).slice(0, 500)}`)))
  })
}

function terminate(child: ReturnType<typeof spawn>): void {
  if (child.pid === undefined) return
  if (process.platform === 'win32') {
    const killer = spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' })
    killer.unref()
  } else {
    try { process.kill(-child.pid, 'SIGTERM') } catch { child.kill('SIGTERM') }
  }
}

export function extractFinalMessage(stdout: string): string {
  let final = ''
  for (const line of stdout.split(/\r?\n/u)) {
    if (line.trim() === '') continue
    let value: unknown
    try { value = JSON.parse(line) } catch { continue }
    const found = findText(value)
    if (found !== undefined) final = found
  }
  if (final === '') throw new Error('Codex route returned no final message')
  return final
}

function findText(value: unknown): string | undefined {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return undefined
  const record = value as Record<string, unknown>
  if (record.type === 'item.completed' && typeof record.item === 'object' && record.item !== null) {
    const item = record.item as Record<string, unknown>
    if (item.type === 'agent_message' && typeof item.text === 'string') return item.text
  }
  if (typeof record.output_text === 'string') return record.output_text
  if (typeof record.message === 'string' && /completed|final/iu.test(String(record.type ?? ''))) return record.message
  return undefined
}

function extension(mediaType: string): string {
  return mediaType === 'image/png' ? 'png' : mediaType === 'image/jpeg' ? 'jpg' : mediaType === 'image/gif' ? 'gif' : 'webp'
}

function redact(text: string): string {
  return text.replace(/(?:sk|key|token)[-_A-Za-z0-9]{12,}/giu, '[redacted]')
}

export function codexPrompt(extra?: string): string {
  return visionPrompt(extra)
}
