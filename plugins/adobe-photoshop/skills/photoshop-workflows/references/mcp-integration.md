# MCP Integration

## Architecture

The integration path is:

`DSH -> stdio MCP -> photoshop-mcp-server -> photoshop-python-api -> Windows COM -> Adobe Photoshop`

It is Windows-only. The packaged launcher is `scripts/start-photoshop-mcp.ps1`; use its `-Check` switch to diagnose the executable, `PS_VERSION`, and registered Photoshop COM versions without starting the MCP server.

The plugin pins the tested runtime set:

- `photoshop-mcp-server==0.1.11`
- `mcp==1.29.0`
- `photoshop-python-api==0.24.2`
- Python 3.12 managed by `uv`

The upstream project documents Photoshop CC 2017 through 2024 as tested. Newer Photoshop releases may work through COM registry discovery but remain outside that published compatibility range.

## Photoshop Version Selection

Do not set `PS_VERSION` by default. `photoshop-python-api` can inspect the Windows registry and choose the newest registered Photoshop COM application. Define `PS_VERSION` only when deliberately targeting a supported installed major version, for example in the environment inherited by DSH.

## Exposed Tools

The server exposes exactly these tools:

- `mcp__photoshop__photoshop_create_document`
- `mcp__photoshop__photoshop_open_document`
- `mcp__photoshop__photoshop_save_document`
- `mcp__photoshop__photoshop_create_text_layer`
- `mcp__photoshop__photoshop_create_solid_color_layer`
- `mcp__photoshop__photoshop_get_session_info`
- `mcp__photoshop__photoshop_get_active_document_info`
- `mcp__photoshop__photoshop_get_selection_info`

All tool names use the `photoshop_` namespace.

## Exposed Resources

- `photoshop://info`
- `photoshop://document/info`
- `photoshop://document/layers`

The layers resource enumerates art layers rather than a complete nested layer-tree model.

## Known Surface Limits

There are no MCP operations for close, undo/history, layer deletion or movement, opacity, masks, effects, adjustment layers, smart objects, transforms, filters, color profiles, export presets, or Photoshop timeline/video editing. Do not convert README aspirations into claimed callable capabilities.

The MCP protocol may report the SDK version as the server version during initialization. Use the installed package metadata or the launcher check to verify the actual `photoshop-mcp-server` version.

## Diagnostics

From the plugin directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-photoshop-mcp.ps1 -CheckOnly
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-photoshop-mcp.ps1 -Check
```

If the executable is absent, run the installation script. If COM connection fails, confirm Photoshop is installed and registered, then retry with `PS_VERSION` unset. A first real MCP session call can launch Photoshop.
