/** Preset-scoped, fail-closed MCP tool approval classifier. */

import type { McpPolicySpec } from './types.js'

interface ToolExecution {
  name: string
}

interface ContextLike {
  on(
    name: 'tools/pre-execute',
    listener: (
      execution: ToolExecution,
      next: () => Promise<{ kind: string }>,
    ) => Promise<{ kind: string, reason?: string }>,
    options?: { prepend?: boolean },
  ): unknown
}

/** Cordis dependency declaration for the tool event vocabulary. */
export const inject = ['tools']

/** Register a scoped MCP policy whose unknown tools always require approval. */
export function apply(ctx: ContextLike, config: McpPolicySpec): void {
  const prefixes = config.serverNames.map(name => `mcp__${name}__`)
  const readOnly = new Set(config.readOnly ?? [])
  const ask = new Set(config.ask ?? [])
  const deny = new Set(config.deny ?? [])
  ctx.on('tools/pre-execute', async (execution, next) => {
    if (!prefixes.some(prefix => execution.name.startsWith(prefix))) return next()
    if (deny.has(execution.name)) {
      return { kind: 'deny', reason: `MCP policy denies tool "${execution.name}"` }
    }
    if (readOnly.has(execution.name)) return next()
    const classified = ask.has(execution.name) ? 'write-classified' : 'unknown'
    return {
      kind: 'ask',
      reason: `${classified} MCP tool "${execution.name}" requires one-shot approval`,
    }
  }, { prepend: true })
}

export default apply
