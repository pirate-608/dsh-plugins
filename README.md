# pirate-608 DSH Plugins

English | [简体中文](README.zh-CN.md)

Personal plugins and agent-preset extensions for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness).

## Plugins

| Package | Purpose |
| --- | --- |
| `@pirate-608/dsh-unity-mcp` | Preset-scoped Unity Editor automation through MCP for Unity 10.1.2, with text-first verification |
| `@pirate-608/dsh-modlens` | Text-first vision through Codex CLI, OpenAI-compatible endpoints, and local Ollama |
| `@pirate-608/dsh-everything-search` | Windows file discovery through Everything |
| `@pirate-608/dsh-latex-workflows` | LaTeX build and PDF validation workflows |
| `@pirate-608/dsh-zotero-mcp` | Local Zotero research and semantic search |
| `@pirate-608/dsh-calibre-library-tools` | Calibre reading and library analysis |
| `@pirate-608/dsh-after-effects` | After Effects automation through ae-mcp |
| `@pirate-608/dsh-photoshop` | Photoshop automation through Windows COM |
| `@pirate-608/dsh-premiere` | Premiere Pro automation through a CEP bridge |
| `@pirate-608/dsh-autocad-mcp` | AutoCAD and headless DXF automation |
| `@pirate-608/dsh-solidworks-automation` | SolidWorks COM and MCP workflows |
| `@pirate-608/dsh-renpy-visual-novel-dev` | Ren'Py development and validation |
| `@pirate-608/dsh-zju-learning-tools` | Isolated read and assignment-submission presets for ZJU services |

Each domain package derives a managed preset from the active DSH `standard` preset. The shared `@pirate-608/dsh-plugin-kit` keeps lifecycle behavior and fail-closed MCP approval consistent. Packages with unresolved first-party licensing remain private and cannot be published.

## Development

Requires Node.js 22.19+ or 24+ and pnpm 10.

```sh
pnpm install
pnpm run check
```

No package is published by the test or build commands.
