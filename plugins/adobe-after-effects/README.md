<!-- dsh-package-header -->
# @pirate-608/dsh-after-effects

Adobe After Effects automation through ae-mcp.

Install into a DSH profile, then create the dedicated preset:

```sh
dsh plugin --profile web add @pirate-608/dsh-after-effects
dsh plugin --profile web exec dsh-after-effects preset install
dsh plugin --profile web exec dsh-after-effects doctor
```

Managed preset id: `after-effects`. The standard preset does not receive this package's tools or skills. MCP writes and unknown tools require one-shot approval.

**Publication blocked:** this package remains private until its first-party license is resolved.
<!-- /dsh-package-header -->

# Adobe After Effects DSH plugin

This local DSH plugin connects to [JUNKDOGE-JOE/after-effects-mcp](https://github.com/JUNKDOGE-JOE/after-effects-mcp) through its installed stable launcher and adds the `after-effects-workflows` skill.

It does not vendor or rebuild the upstream runtime. Install the matching official ae-mcp panel/runtime first, open `Window > Extensions > ae-mcp` in After Effects, and start a new DSH task after installing this plugin.

Run the local launcher check from this directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-ae-mcp.ps1 -Check
```

The default Windows launcher path is `%USERPROFILE%\.ae-mcp\bin\ae-mcp.exe`. Set `AE_MCP_LAUNCHER` only when the official launcher is installed elsewhere.

Compatibility snapshot: ae-mcp v0.9.2, Windows 11 24H2+ x64, After Effects 25.x hardware-validated. Consult upstream release notes for newer information.
