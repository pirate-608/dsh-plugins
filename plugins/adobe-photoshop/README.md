<!-- dsh-package-header -->
# @pirate-608/dsh-photoshop

Adobe Photoshop automation through a local COM MCP bridge.

Install into a DSH profile, then create the dedicated preset:

```sh
dsh plugin --profile web add @pirate-608/dsh-photoshop
dsh plugin --profile web exec dsh-photoshop preset install
dsh plugin --profile web exec dsh-photoshop doctor
```

Managed preset id: `photoshop`. The standard preset does not receive this package's tools or skills. MCP writes and unknown tools require one-shot approval.

**Publication blocked:** this package remains private until its first-party license is resolved.
<!-- /dsh-package-header -->

# Adobe Photoshop DSH Plugin

This plugin integrates the Windows-only `loonghao/photoshop-python-api-mcp-server` with DSH and adds a safety-focused Photoshop workflow skill.

## Install the MCP Runtime

Install `uv`, then run from this plugin directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-photoshop-mcp.ps1
```

Check the installation and local Photoshop registration without starting the server:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-photoshop-mcp.ps1 -CheckOnly
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-photoshop-mcp.ps1 -Check
```

The launcher intentionally leaves `PS_VERSION` unset so the Python adapter can discover the newest registered Photoshop COM version. Define it only when deliberately overriding discovery.

## Use

Start a new DSH task after installing or updating the plugin so its MCP server and skill are loaded. Ask DSH to inspect the Photoshop session first, then make document changes with explicit output and preservation requirements.

The upstream MCP surface is limited to session/document/selection inspection, document create/open/save-copy, text-layer creation, and raster filled-layer creation. Read the included skill before expanding the workflow with UI automation.
