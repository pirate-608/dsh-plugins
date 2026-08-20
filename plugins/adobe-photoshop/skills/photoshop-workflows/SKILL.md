---
name: photoshop-workflows
description: Operate Adobe Photoshop through the photoshop MCP server on Windows. Use when the user asks DSH to inspect a Photoshop session or active PSD/PSB/image; open, create, or save documents; inspect selection or layer information; add text layers or filled pixel layers; diagnose Photoshop COM connectivity; or combine MCP with Windows UI control for unsupported Photoshop operations.
---

# Photoshop Workflows

Use the `photoshop` MCP server as the primary integration. It talks to the local Windows Photoshop application through COM and may launch Photoshop when the first session call is made.

## Prepare

1. Read [MCP integration](references/mcp-integration.md) before the first operation in a task.
2. Establish the intended input document, preservation requirements, output path and format, and whether overwrite is allowed.
3. Start with `mcp__photoshop__photoshop_get_session_info`. Treat this as read-only for documents, but warn that it can launch Photoshop.
4. Read document resources only after the session state is known.
5. Leave `PS_VERSION` unset by default so the adapter can discover the newest registered Photoshop COM version. Set it only for an intentional compatibility override.

## Operate Safely

1. Inspect the session, active document, selection, and available layer information.
2. Before `mcp__photoshop__photoshop_create_document` or `mcp__photoshop__photoshop_open_document`, follow [Document safety](references/document-safety.md). These upstream operations close the active document first.
3. Apply one mutation at a time, then read the resulting state back before continuing.
4. Save to a new absolute path by default. The save tool writes a copy; confirm before overwriting an existing file.
5. For text and filled layers, follow [Layers and selection](references/layers-and-selection.md).
6. Verify visual results in Photoshop or by opening the exported file. The MCP server does not provide canvas screenshots or pixel-level visual inspection.

## Route Unsupported Work

The MCP surface is intentionally small. It does not expose undo/history, document close, layer deletion or reordering, opacity, masks, effects, adjustment layers, transforms, filters, export presets, or timeline/video editing.

If the requested operation is unsupported and Windows UI automation is appropriate, read the full `ModLens file evidence or explicit human review:ModLens file evidence or explicit human review` skill before controlling Photoshop's interface. Keep the active document and output-path safeguards from this skill.

## Guardrails

- Obtain action-time confirmation before closing or replacing an unsaved document, or overwriting an existing file.
- Never describe a filled pixel art layer as a native Photoshop Solid Color Fill adjustment/content layer.
- Use absolute Windows paths and RGB channel values from 0 through 255.
- Do not infer success from a tool call alone; inspect the returned state and verify the output file where applicable.
- Do not upload, publish, or send an image unless the user explicitly requests that external action.
- Report unsupported operations accurately instead of implying the MCP can perform them.

## Finish

Summarize the document affected, mutations performed, output path, verification completed, and any compatibility or visual-review caveat.


<!-- dsh-visual-fallback -->
## Visual evidence

When a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call `modlens_read_image` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.
