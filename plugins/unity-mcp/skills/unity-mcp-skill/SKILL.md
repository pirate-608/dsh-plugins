---
name: unity-mcp-orchestrator
description: Orchestrate cross-domain Unity Editor work through the DSH Unity MCP preset. Use for broad Unity tasks, connection recovery, known-instance selection, cross-domain coordination, or requests that do not fit one specialized Unity skill.
---

# Unity MCP Orchestrator

Coordinate Unity work through DSH's server-qualified MCP tools. The public name of every top-level tool is `mcp__unity__<raw-name>`.

## Route Work

Use the narrowest companion skill for project setup, 2D, 3D, gameplay, UI, content/VFX, debugging, performance, or builds. Use this orchestrator for shared connection, compilation, verification, and cross-domain sequencing.

## Operating Loop

1. Start with idempotent queries such as `mcp__unity__manage_scene(action="get_active")`, package or graphics probes, and `mcp__unity__read_console(action="get")`.
2. If the user supplies a known Unity instance id, select it with `mcp__unity__set_active_instance`. DSH v1 cannot enumerate MCP Resources, so never claim that instance discovery occurred.
3. Inspect the smallest relevant hierarchy, assets, components, tests, and settings before mutation.
4. Make bounded changes. Use `mcp__unity__batch_execute` for independent calls only; values in `commands[].tool` are the MCP server's raw names, for example `manage_gameobject`.
5. After script/import changes, call `mcp__unity__refresh_unity(wait_for_ready=true)` and then read console errors.
6. Run the narrowest relevant tests and repeat the original behavior check.
7. Save scenes/assets and report structural, runtime, and visual status separately.

## Text-First Verification

Assume the active model cannot inspect images. Prefer hierarchy, component fields, asset paths, console output, test results, build reports, profiler counters, render statistics, and camera parameters.

Request screenshots only in file-output mode. Return the saved path but never claim to have seen or validated its pixels. Use exactly one honest visual status:

- `Visual verification pending`
- `Visual verification confirmed by user`
- `Visual verification completed by a host that explicitly exposed image input`

Do not upload screenshots, invoke OCR, or call a third-party vision model automatically. Read [multimodal fallback](references/multimodal-fallback.md) before work whose acceptance criteria are primarily visual.

## Recovery

- Busy or compiling: wait through `mcp__unity__refresh_unity(wait_for_ready=true)`, then retry an idempotent query.
- Domain reload or connection loss: allow the DSH MCP supervisor to reconnect; do not repeat a mutation until its outcome is known.
- Stale script edit: obtain a fresh SHA and reapply against current content.
- Wrong instance: ask for a known instance identifier, then call `mcp__unity__set_active_instance`.
- Tool absent: project-scoped tool discovery may omit unavailable packages or groups; do not invent a replacement.

Read the [tool reference](references/tools-reference.md) and [shared workflows](references/workflows.md) selectively.
