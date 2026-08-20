# pirate-608 DSH 插件

[English](README.md) | 简体中文

面向 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的个人插件与 Agent Preset 扩展集合。

## 插件

| 包 | 用途 |
| --- | --- |
| `@pirate-608/dsh-unity-mcp` | 通过 MCP for Unity 10.1.2 操作 Unity Editor；能力限定在独立 Preset，并采用文本优先验证 |
| `@pirate-608/dsh-modlens` | 通过本地 Codex、OpenAI-compatible 和 Ollama 为文本模型补充视觉证据 |
| `@pirate-608/dsh-everything-search` | Everything 本地文件检索 |
| `@pirate-608/dsh-latex-workflows` | LaTeX 构建与 PDF 验证 |
| `@pirate-608/dsh-zotero-mcp` | Zotero 本地研究资料库与语义检索 |
| `@pirate-608/dsh-calibre-library-tools` | Calibre 阅读与资料库分析 |
| `@pirate-608/dsh-after-effects` | After Effects 自动化 |
| `@pirate-608/dsh-photoshop` | Photoshop Windows COM 自动化 |
| `@pirate-608/dsh-premiere` | Premiere Pro CEP 自动化 |
| `@pirate-608/dsh-autocad-mcp` | AutoCAD 与无界面 DXF 自动化 |
| `@pirate-608/dsh-solidworks-automation` | SolidWorks COM 与 MCP 工作流 |
| `@pirate-608/dsh-renpy-visual-novel-dev` | Ren'Py 开发与验证 |
| `@pirate-608/dsh-zju-learning-tools` | 隔离的浙大只读与作业提交 Preset |

每个领域包都会从当前 DSH `standard` 派生受管 Preset。共享的 `@pirate-608/dsh-plugin-kit` 统一生命周期和默认拒绝放行的 MCP 审批策略；作者代码许可证尚未明确的包保持 private，不能发布。

## 开发

需要 Node.js 22.19+ 或 24+、pnpm 10。

```sh
pnpm install
pnpm run check
```

测试和构建命令不会发布任何包。
