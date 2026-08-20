---
name: zju-auth-session
description: Diagnose and manage the private local authentication session for ZJU Learning Tools. Use when the user asks to set up, log in to, log out of, check, repair, or troubleshoot 学在浙大/ZJU access, or when another ZJU tool returns auth_required or a runtime readiness error.
---

# ZJU Auth Session

Keep credential entry outside the agent. Use only `mcp__zju_learning__zju_doctor` and `mcp__zju_learning__zju_auth_status` for diagnosis.

## Diagnose

1. Call `mcp__zju_learning__zju_doctor` to check Windows, `uv`, the locked runtime, the credential store, and session-file readiness.
2. Call `mcp__zju_learning__zju_auth_status` to report whether a session exists, when it expires, and only the masked account suffix.
3. Translate structured failures without exposing raw exceptions or secret material.

## Ask the user to authenticate

Resolve `<plugin-root>` as the directory two levels above this skill directory. Tell the user to run the appropriate command in a PowerShell they opened themselves:

```powershell
powershell -ExecutionPolicy Bypass -File <plugin-root>/scripts/zju-auth.ps1 login
powershell -ExecutionPolicy Bypass -File <plugin-root>/scripts/zju-auth.ps1 status
powershell -ExecutionPolicy Bypass -File <plugin-root>/scripts/zju-auth.ps1 logout
```

Never run `login` through an agent-controlled shell. Never ask for or accept a password, Cookie, CAS ticket, Bearer token, session file, encryption key, or copied browser/ZLA credential in chat, tool arguments, environment variables, or configuration.

If login reports CAPTCHA, MFA, or an upstream-form change, stop and direct the user to the official site. Do not loop, scrape browser credentials, or weaken validation. After the user finishes login, ask them to retry `mcp__zju_learning__zju_auth_status`; do not claim success before checking.

If the MCP cannot start, register tools, complete its handshake, or maintain its transport, route to `$zju-tronclass-fallback`. That fallback has separate `configure`, `login`, `status`, and `logout` commands and never reuses this encrypted MCP session. Do not select it for a normal `auth_required` response.

## Boundaries

Authentication authorizes read-only queries and bounded official downloads. Ordinary-homework submission additionally requires the separate user-owned `zju-write-access.ps1` opt-in plus a fresh prepare/confirm/commit transaction. Authentication alone never authorizes submission, posting, attendance, progress fabrication, or raw API access.


<!-- dsh-visual-fallback -->
## Visual evidence

When a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call `modlens_read_image` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.
