---
name: premiere-workflows
description: Operate Adobe Premiere Pro through the bundled Premiere MCP integration with Windows app control as a fallback. Use when the user asks DSH to inspect, open, or create a Premiere project; import and organize media; edit sequences or timelines; trim clips; add transitions, effects, titles, captions, markers, or keyframes; mix audio; adjust color; diagnose the CEP bridge; validate an edit; or configure and export a video.
---

# Premiere Workflows

Use the bundled `premiere_pro` MCP tools as the primary structured editing interface. Use the documented local installer for CEP bridge setup, visual verification, and UI operations that the MCP cannot perform. Treat verified Premiere project state as the source of truth and preserve the user's existing edit.

## Prepare

1. Read [mcp-integration.md](references/mcp-integration.md) before the first MCP operation in a task.
2. Confirm Premiere is running, a project is open when required, and `Window > Extensions > MCP Bridge (CEP)` reports that the bridge is started.
3. Begin with read-only MCP discovery such as `mcp__premiere_pro__get_project_info`, `mcp__premiere_pro__list_sequences`, `mcp__premiere_pro__get_active_sequence`, and `mcp__premiere_pro__list_project_items`.
4. Establish the edit contract: intended project and sequence, source media, deliverable, aspect ratio, frame rate, duration target, and whether overwriting existing work is allowed. Infer only reversible details.
5. Prefer a new clearly named sequence for generated or experimental edits. Never overwrite an existing project or export unless the user explicitly requests it.

If the MCP tools are absent or the CEP panel must be configured, read the complete `ModLens file evidence or explicit human review` skill before Windows automation and follow its initialization, confirmation, and observation rules.

## Work in verified increments

For MCP operations, use a read -> one logical mutation -> read-back loop. Pass stable project item and sequence IDs returned by discovery tools instead of guessing names. If a response returns `success: false`, report the exact error and diagnose the bridge before retrying.

- Inspect the active project, sequence, playhead, selection, and focused panel before edits.
- Make one logical edit at a time, then verify it through a read tool and, when visual quality matters, inside Premiere.
- Preserve source media; edit non-destructively inside the project.
- Avoid changing global preferences, scratch disks, color-management defaults, or cache locations unless requested.
- Save after meaningful milestones. Use Save As for risky restructuring or alternate versions.
- Keep a concise action log in commentary: sequence affected, edit made, and verification result.

For Windows UI fallback, use an observe -> one action -> refresh loop. Premiere panels and coordinates vary by workspace, language, version, and display scaling; never reuse stale coordinates.

## Choose the workflow

- For MCP setup, tool selection, bridge diagnostics, and architecture, read [mcp-integration.md](references/mcp-integration.md).
- For ingest, bins, sequences, trimming, ripple edits, transitions, titles, and reframing, read [editing.md](references/editing.md).
- For captions, dialogue cleanup, loudness, music balance, and color correction, read [finishing.md](references/finishing.md).
- For review, delivery settings, naming, export, and post-export checks, read [export.md](references/export.md).

Read only the relevant reference files.

## Guardrails

- Do not delete media, project files, sequences, bins, tracks, captions, clips, or exports without action-time confirmation.
- Treat replacing a file during Save As or export as deletion or overwrite and confirm immediately before it.
- Before closing a changed project, verify it is saved. Confirm before discarding changes.
- Do not publish, upload, share, or send exported media unless the user explicitly requests the destination and confirms any required transmission.
- Stop on missing media, offline proxies, unknown color-space warnings, autosave recovery prompts, plugin or license dialogs, or conflicting sequence settings. Report the exact prompt and ask when the choice affects output.
- Never run the upstream live-tool sweep against a working project; it creates disposable sequences and imports fixtures. Use a scratch project only with explicit permission.

## Finish

Summarize the project and sequence changed, major edits, save location, export location and settings if applicable, and anything left unresolved. Do not claim visual or audio quality was verified unless it was actually reviewed in Premiere or from the rendered output.


<!-- dsh-visual-fallback -->
## Visual evidence

When a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call `modlens_read_image` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.
