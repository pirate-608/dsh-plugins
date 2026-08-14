# pirate-608 DSH 插件

[English](README.md) | 简体中文

面向 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的个人插件与 Agent Preset 扩展集合。

## 插件

| 包 | 用途 |
| --- | --- |
| `@pirate-608/dsh-unity-mcp` | 通过 MCP for Unity 10.1.2 操作 Unity Editor；能力限定在独立 Preset，并采用文本优先验证 |

每个插件都是 `plugins/` 下独立版本化的 npm 包，只影响安装它的 DSH profile。启用外部进程或可写工具前，请阅读对应插件的安全说明。

## 开发

需要 Node.js 22.19+ 或 24+、pnpm 10。

```sh
pnpm install
pnpm run check
```

测试和构建命令不会发布任何包。
