/** Managed Unity preset definition. */

import type { PresetSpec } from '@pirate-608/dsh-plugin-kit'
import { MCP_SERVER_VERSION, PACKAGE_NAME, PACKAGE_VERSION } from './constants.js'

export const UNITY_PRESET: PresetSpec = {
  packageName: PACKAGE_NAME,
  packageVersion: PACKAGE_VERSION,
  commandName: 'dsh-unity-mcp',
  id: 'unity',
  name: 'Unity MCP',
  description: 'Text-first Unity Editor automation through MCP for Unity 10.1.2.',
  providerName: 'unity-skills',
  mcpServers: [{
    id: 'unity-mcp',
    serverName: 'unity',
    command: 'uvx',
    args: ['--from', `mcpforunityserver==${MCP_SERVER_VERSION}`, 'mcp-for-unity', '--transport', 'stdio', '--project-scoped-tools'],
    env: {},
    cwd: '',
    toolCallTimeoutMs: 300_000,
    failOnStartupError: true,
  }],
  policy: {
    serverNames: ['unity'],
    readOnly: ['mcp__unity__unity_reflect', 'mcp__unity__unity_docs', 'mcp__unity__read_console', 'mcp__unity__screenshot'],
    ask: [],
    deny: [],
  },
  doctor: [{ label: 'uvx', command: 'uvx', args: ['--version'] }],
}
