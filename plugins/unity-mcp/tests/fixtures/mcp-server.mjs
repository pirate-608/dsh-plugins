import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import { z } from 'zod'

const server = new McpServer(
  { name: 'dsh-unity-fixture', version: '1.0.0' },
  { capabilities: { tools: {} } },
)

server.registerTool('scene_summary', {
  description: 'Returns text-only structural scene evidence.',
  inputSchema: {},
}, async () => ({
  content: [{ type: 'text', text: 'Scene: Fixture; roots: 2; consoleErrors: 0' }],
}))

server.registerTool('screenshot', {
  description: 'Returns a path plus an image block to test the text-first fallback.',
  inputSchema: { include_image: z.boolean().optional() },
}, async () => ({
  content: [
    { type: 'text', text: 'Saved screenshot: Assets/Screenshots/fixture.png' },
    { type: 'image', data: 'iVBORw0KGgo=', mimeType: 'image/png' },
  ],
}))

await server.connect(new StdioServerTransport())
