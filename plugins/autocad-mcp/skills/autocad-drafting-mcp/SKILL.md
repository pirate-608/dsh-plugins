---
name: autocad-drafting-mcp
description: "Use the integrated autocad-mcp tools to create, inspect, modify, annotate, verify, and export AutoCAD DWG/DXF drawings or headless DXF files. Trigger for AutoCAD, CAD, DWG, DXF, 2D drafting, layers, blocks, dimensions, P&ID, mcp__autocad__drawing screenshots, plotting, batch mcp__autocad__drawing changes, and diagnosing the AutoCAD MCP connection on Windows."
---

# AutoCAD drafting with MCP

Use the eight `autocad-mcp` tools as a structured CAD API. Prefer the live File IPC backend when AutoCAD is available; use the `ezdxf` backend for headless DXF work.

## Start every task

1. Call `mcp__autocad__system(operation="status")`.
2. Read the returned backend and capabilities before choosing operations.
3. Confirm or state units, model-space scale, target format, output path, and overwrite policy.
4. For an existing mcp__autocad__drawing, preserve the source and save to a new absolute path unless the user explicitly authorizes overwrite.
5. Execute MCP calls serially. AutoCAD desktop dispatch supports one in-flight command.

If the status reports `ezdxf`, work with DXF only. Do not claim that a DWG was opened, a PDF was plotted, or AutoCAD was controlled.

## Choose the backend

- Use `file_ipc` for live AutoCAD/AutoCAD LT, DWG operations, plotting PDF, zooming, undo/redo, and commands unavailable in ezdxf.
- Use `ezdxf` for offline DXF creation, inspection, layers, entities, blocks, annotations, and rendered review images.
- If the user requires live AutoCAD and status falls back to `ezdxf`, stop before mcp__autocad__drawing and read [setup.md](references/setup.md).

## Drafting workflow

1. Create or open the mcp__autocad__drawing with `mcp__autocad__drawing`.
2. Create named layers before geometry. Keep model space at 1:1 and record the assumed units.
3. Add geometry with `mcp__autocad__entity`; retain returned handles for later edits.
4. Add blocks with `mcp__autocad__block` and real dimensions/text/leaders with `mcp__autocad__annotation`.
5. Use `mcp__autocad__view(operation="zoom_extents")` when supported, then request `mcp__autocad__view(operation="get_screenshot")`.
6. Call `mcp__autocad__drawing(operation="info")`, `mcp__autocad__layer(operation="list")`, and `mcp__autocad__entity(operation="count")` to verify the result.
7. Save to an absolute path. Prefer DXF for portable/headless output; use DWG or PDF only when File IPC reports support.
8. Check that the saved file exists and report its path, backend, mcp__autocad__entity/mcp__autocad__layer counts, and remaining manual review items.

For exact operation names and backend differences, read [tool-catalog.md](references/tool-catalog.md).

## Engineering mcp__autocad__drawing rules

- Use millimetres unless the user or source mcp__autocad__drawing states otherwise.
- Separate outlines, centres, hidden lines, dimensions, text, hatches, and construction geometry into named layers.
- For manufacturable parts, include overall size plus complete hole/slot sizes and locations from explicit datums.
- Use actual dimension entities through `mcp__autocad__annotation`; do not imitate dimensions with loose lines and text.
- Treat P&ID headless symbols as simplified placeholders unless the required CTO library is installed and verified.
- A screenshot is a review aid, not proof of drafting-standard compliance.

## Safety

- Do not use, request, or recreate arbitrary AutoLISP/Python/shell execution through MCP. The integrated upstream `execute_lisp` route is intentionally disabled.
- Do not overwrite a user mcp__autocad__drawing without explicit permission.
- Do not fabricate success after an unsupported operation or timeout. Use undo when available, inspect the mcp__autocad__drawing, and retry only after resolving the cause.
- Avoid loading untrusted LISP, blocks, templates, or external references.

## Recovery

On connection or dispatch failure, read [troubleshooting.md](references/troubleshooting.md). Re-run `mcp__autocad__system(operation="status")` after AutoCAD starts or the bundle loads. If a write partially succeeds, call `mcp__autocad__drawing(operation="undo")` only on File IPC, then verify counts before continuing.

## Final response

State the assumptions, active backend, files produced, verification performed, and anything that still needs AutoCAD-side or human review.


<!-- dsh-visual-fallback -->
## Visual evidence

When a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call `modlens_read_image` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.
