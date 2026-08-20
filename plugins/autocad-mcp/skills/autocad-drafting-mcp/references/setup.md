# Setup

Read this file when MCP status is unavailable, the backend is not the one the task requires, or AutoCAD reports that the dispatcher is not loaded.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer
- `uv` on `PATH`
- AutoCAD LT 2024 or newer for File IPC; full AutoCAD is also supported

The MCP config defaults to `AUTOCAD_MCP_BACKEND=auto`. It uses File IPC when a compatible AutoCAD window is found and otherwise falls back to the headless `ezdxf` backend.

## Install the DSH plugin

Install `@pirate-608/dsh-autocad-mcp`, run its managed Preset installer, then start a new DSH session on the `autocad` Preset. The generated MCP row runs:

```text
uv run --project ./vendor/autocad-mcp python -m autocad_mcp
```

## Install the AutoCAD-side bundle

Run:

```powershell
.\scripts\install.ps1
```

It synchronizes Python dependencies and copies `DSHAutoCADMCP.bundle` to `%APPDATA%\Autodesk\ApplicationPlugins`.

Restart AutoCAD after installation. The command line should report:

```text
=== MCP Dispatch v3.1 loaded ===
IPC directory: C:/temp/codex-autocad-mcp/
```

User-profile bundles may require a trust prompt or trusted-path setting. Do not disable secure loading globally.

## Environment variables

- `AUTOCAD_MCP_BACKEND`: `auto`, `file_ipc`, or `ezdxf`
- `AUTOCAD_MCP_IPC_DIR`: defaults here to `C:/temp/codex-autocad-mcp`
- `AUTOCAD_MCP_IPC_TIMEOUT`: defaults here to `30` seconds
- `AUTOCAD_MCP_ONLY_TEXT`: set to `true` to disable screenshots

The Python and AutoLISP IPC directories must match exactly.

## Sources

- Upstream MCP: https://github.com/puran-water/autocad-mcp
- Autodesk bundle deployment: https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-Customization/files/GUID-5E50A846-C80B-4FFD-8DD3-C20B22098008.htm
- Autodesk package format: https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-Customization/files/GUID-BC76355D-682B-46ED-B9B7-66C95EEF2BD0.htm
