<!-- dsh-package-header -->
# @pirate-608/dsh-premiere

Adobe Premiere Pro automation through a bundled CEP MCP bridge。

先安装到 DSH profile，再创建独立 Preset：

```powershell
dsh plugin --profile web add @pirate-608/dsh-premiere
dsh plugin --profile web exec dsh-premiere preset install
dsh plugin --profile web exec dsh-premiere doctor
```

受管 Preset：`premiere`。标准 Preset 不会得到本包的工具或技能；MCP 写操作和未知工具必须经过一次性审批。

**禁止发布：**补齐作者代码许可证之前，本包保持 private。
<!-- /dsh-package-header -->
