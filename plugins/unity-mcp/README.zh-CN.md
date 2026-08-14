# @pirate-608/dsh-unity-mcp

[English](README.md) | 简体中文

面向 DeepSeek Harness 的 Unity MCP 工具与技能包。它从当前 DSH 随附的 `standard` 派生独立 `unity` Agent Preset，因此普通会话不会得到 Unity 工具，也无需承担其 schema 开销。

## 依赖

- DSH `>=0.0.1-rc.5 <0.2.0`
- Node.js 22.19+ 或 24+
- `uvx` 与 Python 3.10+
- Unity 项目已安装并启用 MCP for Unity

生成 Preset 时会从当前 DSH 安装中解析 MCP 与文件系统技能插件，避免混用不同 rc generation；随后通过 stdio 启动固定版本 `mcpforunityserver==10.1.2`，并启用 project-scoped tools。`uvx` 首次启动可能需要联网。

## 安装

```sh
dsh plugin --profile web add @pirate-608/dsh-unity-mcp
dsh plugin --profile web exec dsh-unity-mcp preset install
```

在 WebUI 新建会话并选择 `unity`。工具名采用 `mcp__unity__<原始名称>`。

管理命令：

```sh
dsh plugin --profile web exec dsh-unity-mcp preset status
dsh plugin --profile web exec dsh-unity-mcp preset update
dsh plugin --profile web exec dsh-unity-mcp preset remove
```

`update` 会从当前 DSH 的 `standard` 重新生成。检测到本地修改时，更新和删除都会停止；显式 `--force` 会先将完整目录移动到带时间戳的备份。

卸载 npm 包前先删除 Preset：

```sh
dsh plugin --profile web exec dsh-unity-mcp preset remove
dsh plugin --profile web remove @pirate-608/dsh-unity-mcp
```

## 文本优先的多模态回退

技能默认当前模型不能读取图片。DSH 目前会把 MCP 非文本块渲染成占位符，因此截图只保存为文件并返回路径。路径不等于视觉证据：Agent 必须分别报告结构验证、运行验证和视觉验证状态；只有用户或明确支持图像输入的宿主确认后，才能关闭视觉验收项。

插件不会自动上传截图、调用 OCR 或切换到其他视觉提供方。

## 安全边界

MCP 工具调用会经过 DSH 的工具审批流程，但 `uvx` MCP 子进程和 Unity Editor 位于 DSH 文件沙箱之外，可以修改所连接的 Unity 项目。请使用独立 Preset、审阅审批请求并保留版本控制。

## 已知限制

- DSH 只桥接 MCP Tools；Resources 与 Prompts 不可用。
- 插件不能枚举 Unity 实例，只能通过 `mcp__unity__set_active_instance` 选择用户提供的实例 id。
- 刻意不使用内联截图数据。
- 已运行会话保留启动时的 Preset generation；更新只影响新会话。
