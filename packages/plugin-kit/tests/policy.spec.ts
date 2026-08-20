import { describe, expect, it } from 'vitest'
import apply from '../src/policy.js'

describe('MCP approval policy', () => {
  it('allows explicit reads, asks for writes and unknowns, and denies forbidden tools', async () => {
    let listener!: (exec: { name: string }, next: () => Promise<{ kind: string }>) => Promise<{ kind: string, reason?: string }>
    apply({ on: (_name, value) => { listener = value } }, {
      serverNames: ['fixture'],
      readOnly: ['mcp__fixture__read'],
      ask: ['mcp__fixture__write'],
      deny: ['mcp__fixture__erase'],
    })
    const next = async (): Promise<{ kind: string }> => ({ kind: 'allow' })
    await expect(listener({ name: 'mcp__fixture__read' }, next)).resolves.toEqual({ kind: 'allow' })
    await expect(listener({ name: 'mcp__fixture__write' }, next)).resolves.toMatchObject({ kind: 'ask' })
    await expect(listener({ name: 'mcp__fixture__new' }, next)).resolves.toMatchObject({ kind: 'ask' })
    await expect(listener({ name: 'mcp__fixture__erase' }, next)).resolves.toMatchObject({ kind: 'deny' })
    await expect(listener({ name: 'bash' }, next)).resolves.toEqual({ kind: 'allow' })
  })
})
