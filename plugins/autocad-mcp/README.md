<!-- dsh-package-header -->
# @pirate-608/dsh-autocad-mcp

AutoCAD and headless DXF automation through a text-first MCP preset.

Install into a DSH profile, then create the dedicated preset:

```sh
dsh plugin --profile web add @pirate-608/dsh-autocad-mcp
dsh plugin --profile web exec dsh-autocad-mcp preset install
dsh plugin --profile web exec dsh-autocad-mcp doctor
```

Managed preset id: `autocad`. The standard preset does not receive this package's tools or skills. MCP writes and unknown tools require one-shot approval.

**Publication blocked:** this package remains private until its first-party license is resolved.
<!-- /dsh-package-header -->
