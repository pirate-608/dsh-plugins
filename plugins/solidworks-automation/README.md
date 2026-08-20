<!-- dsh-package-header -->
# @pirate-608/dsh-solidworks-automation

SolidWorks COM and MCP automation workflows.

Install into a DSH profile, then create the dedicated preset:

```sh
dsh plugin --profile web add @pirate-608/dsh-solidworks-automation
dsh plugin --profile web exec dsh-solidworks-automation preset install
dsh plugin --profile web exec dsh-solidworks-automation doctor
```

Managed preset id: `solidworks`. The standard preset does not receive this package's tools or skills. MCP writes and unknown tools require one-shot approval.
<!-- /dsh-package-header -->

# SolidWorks Automation

面向 Windows DSH 的本地 SolidWorks 自动化插件。插件通过 Python COM 和受控 stdio MCP 操作用户当前桌面会话中的 SolidWorks。

## 能力

- 零件草图、拉伸和常用特征
- 盲孔、通孔、沉孔、沉头孔和槽
- 装配组件与常用 Mate
- Motion Study 与旋转马达
- 外观、工程图、STEP/STL/IGES/PDF/DXF 导出
- 多视图预览、几何测量和结果审查
- VibeCAD、CNC 圆角/倒角和螺纹孔专项工作流

## 环境

- Windows 10/11
- 已安装并至少启动过一次 SolidWorks
- Python 3.8+
- `pywin32`、`comtypes`、`mcp` 和 `pydantic`

插件首次执行前会运行环境自检。缺少 Python COM 依赖时，只有得到用户明确许可后才会安装。

## 结构

```text
.dsh-plugin/plugin.json   插件元数据
preset.json                 受管 Preset 与本地 stdio MCP 配置
skills/solidworks-automation/
  SKILL.md                  核心工作流
  mcp-server/server.py      MCP 服务
  scripts/                  SolidWorks COM 封装
  references/               按需加载的工程参考
  subskills/                专项 CAD 工作流
```

本市场发行包不包含上游 CAD Studio React/Tauri 桌面应用、Rust 工程、壁纸、安装包构建脚本或 UI E2E 测试。需要 CAD Studio 完整桌面产品时，请使用[上游项目](https://github.com/wzyn20051216/solidworks-automation-skill)及其 Releases。

## 安全边界

- MCP 不提供任意 Python 或 VBA 执行工具。
- SolidWorks COM 写操作串行执行。
- 修改和覆盖现有工程文件前需要用户确认。
- 保存或导出后必须检查文件并生成可审查证据。

## 许可证与来源

插件代码源自 `wzyn20051216/solidworks-automation-skill` v0.3.0，按 MIT 许可证使用；市场发行包进行了结构裁剪。详情见 `UPSTREAM.json` 和插件根目录的 `LICENSE`。
