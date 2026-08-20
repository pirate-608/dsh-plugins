# ae-mcp integration

## Architecture

The DSH plugin launches the installed ae-mcp stdio server. The server talks over loopback HTTP to the CEP panel at `http://127.0.0.1:11488`; the panel dispatches maintained ExtendScript operations and, when available, curated native AEGP operations into After Effects.

```text
DSH -> plugin PowerShell launcher -> installed ae-mcp stdio server
      -> 127.0.0.1:11488 -> AE CEP panel -> ExtendScript/native dispatcher -> AE project
```

The plugin intentionally does not download Python packages, rebuild the repository, or install an unsigned development panel. It resolves the official stable launcher from `AE_MCP_LAUNCHER`, `%USERPROFILE%\.ae-mcp\bin`, or `PATH`.

## First-run checklist

1. Use an upstream release that matches the installed After Effects and operating system.
2. Install the official ZXP with a supported installer, restart After Effects, and open `Window > Extensions > ae-mcp`.
3. Complete the panel's runtime/launcher setup. On Windows v0.9.2, the expected launcher is `%USERPROFILE%\.ae-mcp\bin\ae-mcp.exe`.
4. Run `powershell -ExecutionPolicy Bypass -File scripts/start-ae-mcp.ps1 -Check` from the plugin directory if discovery fails.
5. In a new DSH task, call `mcp__after_effects__ae_ping`, then `mcp__after_effects__ae_status`, then `mcp__after_effects__ae_diagnose` if necessary.

Override only when needed:

- `AE_MCP_LAUNCHER`: absolute path to the installed stable launcher.
- `AE_MCP_PLUGIN_URL`: panel URL when the port differs from `11488`.
- `AE_MCP_BACKEND`: defaults to `ae-mcp`.

## Public tool groups

- Connection and diagnostics: `mcp__after_effects__ae_ping`, `mcp__after_effects__ae_status`, `mcp__after_effects__ae_diagnose`.
- Maintained/native execution: `mcp__after_effects__ae_exec`, `mcp__after_effects__ae_nativeExec`.
- Visual and expression verification: `mcp__after_effects__ae_previewFrame`, `mcp__after_effects__ae_validateExpressions`, `mcp__after_effects__ae_snapshot`.
- Recovery: `mcp__after_effects__ae_checkpoint`, `mcp__after_effects__ae_revert`.
- Expert skills: `mcp__after_effects__ae_skillList`, `mcp__after_effects__ae_skillUse`.
- Tool Library: `mcp__after_effects__ae_toolIndex`, `mcp__after_effects__ae_toolSearch`, `mcp__after_effects__ae_toolInspect`, `mcp__after_effects__ae_toolUse`.

The server may expose additional version-specific tools. Discover the active tool list rather than assuming a repository screenshot or old README is authoritative.

## Failure triage

- Launcher missing: run the check command, then use the panel's official setup/repair path. Do not substitute an unrelated PyPI package.
- Server starts but tools fail: verify AE and the panel are open, inspect `mcp__after_effects__ae_status`, then `mcp__after_effects__ae_diagnose`.
- Connection refused: confirm the panel URL/port and that another process has not claimed it.
- Authentication error: the panel and core runtime may be version-skewed. Upgrade them as one matching set.
- Timeout after a write: do not retry. Inspect project state and audit/activity evidence first.
- Tool absent: use the active tool list and diagnostics; the installed version may differ.

Never expose the panel auth token, provider credentials, or unredacted logs in chat.
