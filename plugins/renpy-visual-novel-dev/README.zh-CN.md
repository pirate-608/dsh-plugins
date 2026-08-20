<!-- dsh-package-header -->
# @pirate-608/dsh-renpy-visual-novel-dev

RenPy development, preview, testing, and asset-integration workflows。

先安装到 DSH profile，再创建独立 Preset：

```powershell
dsh plugin --profile web add @pirate-608/dsh-renpy-visual-novel-dev
dsh plugin --profile web exec dsh-renpy-visual-novel-dev preset install
dsh plugin --profile web exec dsh-renpy-visual-novel-dev doctor
```

受管 Preset：`renpy`。标准 Preset 不会得到本包的工具或技能；MCP 写操作和未知工具必须经过一次性审批。
<!-- /dsh-package-header -->
