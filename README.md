# pirate-608 DSH Plugins

English | [简体中文](README.zh-CN.md)

Personal plugins and agent-preset extensions for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness).

## Plugins

| Package | Purpose |
| --- | --- |
| `@pirate-608/dsh-unity-mcp` | Preset-scoped Unity Editor automation through MCP for Unity 10.1.2, with text-first verification |

Each plugin is an independently versioned npm package under `plugins/`. Installing one affects only the selected DSH profile. Consult its README before enabling external processes or write-capable tools.

## Development

Requires Node.js 22.19+ or 24+ and pnpm 10.

```sh
pnpm install
pnpm run check
```

No package is published by the test or build commands.
