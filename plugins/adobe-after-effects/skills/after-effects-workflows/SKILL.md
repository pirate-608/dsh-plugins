---
name: after-effects-workflows
description: Operate Adobe After Effects through the ae-mcp integration. Use when the user asks DSH to inspect, diagnose, create, or modify an After Effects project or composition; work with layers, footage, text, shapes, cameras, lights, effects, masks, markers, keyframes, expressions, timing, previews, snapshots, checkpoints, reusable JSX tools, or rendering; or configure and troubleshoot the ae-mcp CEP bridge.
---

# After Effects Workflows

Use the `after_effects` MCP server as the structured interface to After Effects. Treat the active AE project as user data: inspect before editing, checkpoint before non-trivial changes, make bounded mutations, and independently verify results.

## Prepare

1. Read [mcp-integration.md](references/mcp-integration.md) before the first MCP operation in a task.
2. Confirm After Effects is running, the intended project is active, and `Window > Extensions > ae-mcp` is open.
3. Start with `mcp__after_effects__ae_ping`, `mcp__after_effects__ae_status`, and read-only inspection. If they disagree, run `mcp__after_effects__ae_diagnose` and stop writes until the bridge is healthy.
4. Establish the work contract: target project and composition, frame rate, dimensions, duration, deliverable, relevant fonts/plugins/media, and whether existing work may be replaced. Infer only reversible details.
5. For generated or exploratory work, prefer a new clearly named composition or duplicated composition. Never use a production project for tool sweeps or acceptance fixtures.

The upstream server supplies session instructions and an on-demand expert library. For non-trivial execution, load `builtin:skill:ae-execution-guide` through `mcp__after_effects__ae_skillUse` before composing a program.

## Work in verified increments

1. Read current state and retain stable locators.
2. Create `mcp__after_effects__ae_checkpoint` before a multi-step or risky edit.
3. Perform one logical mutation through `mcp__after_effects__ae_exec`, `mcp__after_effects__ae_nativeExec`, or an inspected Tool Library artifact.
4. Read the affected state independently.
5. Use `mcp__after_effects__ae_validateExpressions` when expressions changed.
6. Use `mcp__after_effects__ae_previewFrame` at representative times when appearance or motion matters.
7. Save only when the verified state matches the request.

Do not blindly retry a timeout, disconnect, or `POSSIBLY_SIDE_EFFECTING_FAILURE`. Reconcile AE state and activity/audit evidence first because the write may have completed. Undo availability is not proof of restoration; if recovery matters, execute recovery and verify state again.

## Choose the execution route

- Prefer `mcp__after_effects__ae_exec` for maintained After Effects scripting-object-model operations and ordinary project automation.
- Use `mcp__after_effects__ae_nativeExec` only for a curated native primitive that needs exact graph, time, ratio, or property semantics. Native writes require an `operationKey`, an `undoGroup`, and independent readback.
- Use `mcp__after_effects__ae_toolIndex` -> `mcp__after_effects__ae_toolSearch` -> `mcp__after_effects__ae_toolInspect` -> `mcp__after_effects__ae_toolUse` for reusable local JSX, expressions, recipes, and diagnostics. Inspect before execution; never execute a merely imported candidate artifact.
- Use `mcp__after_effects__ae_snapshot` for viewer/window evidence and `mcp__after_effects__ae_previewFrame` for real composition pixels. Do not substitute a desktop screenshot when render truth matters.
- Use `mcp__after_effects__ae_revert` only to return to an explicit checkpoint after confirming which later changes will be lost.

For animation, keyframes, expressions, text, and shape work, read [animation-and-expressions.md](references/animation-and-expressions.md). For visual review, previews, rendering, and delivery, read [preview-and-render.md](references/preview-and-render.md). Read only the relevant references.

## Guardrails

- Do not delete compositions, footage, layers, effects, keyframes, markers, render-queue items, project files, checkpoints, Tool Library artifacts, or rendered files without action-time confirmation.
- Treat Save As, render, collect-files, and export overwrites as destructive and confirm immediately before replacement.
- Avoid global preferences, color-management defaults, cache locations, third-party plugin settings, and workspace layout unless explicitly requested.
- Preserve source footage. Do not rename, move, transcode, relink, or replace files outside the project without explicit scope.
- Stop on missing footage, font substitution, expression errors, plugin/license dialogs, color-management conflicts, recovery prompts, or an unexpected active project.
- Never claim visual quality was verified from parameter values alone. Use real preview frames or rendered output and state which times were reviewed.
- Never publish, upload, or send output unless the user explicitly requests the destination.

## Finish

Summarize the project and compositions changed, checkpoint or recovery state, key mutations, frames/times inspected, expression validation result, save location, and render settings/output if applicable. Report unresolved warnings and distinguish parameter validation from visual validation.


<!-- dsh-visual-fallback -->
## Visual evidence

When a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call `modlens_read_image` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.
