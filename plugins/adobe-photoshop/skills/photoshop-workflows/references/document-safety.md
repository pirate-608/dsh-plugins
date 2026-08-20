# Document Safety

## Upstream Close Behavior

`mcp__photoshop__photoshop_create_document` and `mcp__photoshop__photoshop_open_document` close the currently active document before creating or opening the target. The adapter does not expose a save-choice parameter for this close operation. Depending on Photoshop state, this can discard work or trigger an application prompt.

Never call either tool blindly when an active document exists.

## Safe Create or Open Sequence

1. Call `mcp__photoshop__photoshop_get_session_info` and `mcp__photoshop__photoshop_get_active_document_info`.
2. If there is an active document, determine whether it has unsaved work. MCP metadata alone may not establish this reliably.
3. Ask for action-time confirmation before replacing or closing the active document.
4. Prefer having the user save and close it in Photoshop, or save an explicit copy to a new absolute path first.
5. Call create/open only once the active-document risk is resolved.
6. Read back active-document information and confirm the expected name, dimensions, and mode.

## Safe Save Sequence

`mcp__photoshop__photoshop_save_document` uses Photoshop Save As with `asCopy=True` for PSD, JPEG, and PNG. Treat it as writing an output copy rather than changing the active document's canonical file association.

1. Choose an absolute output path with a supported extension: `.psd`, `.jpg`/`.jpeg`, or `.png`.
2. Default to a new filename. If the path exists, request confirmation immediately before overwrite.
3. Save the copy.
4. Confirm the tool result and verify that the output path exists.
5. Keep reporting which document remains active; do not imply that Save As Copy renamed or relocated it.

Saving a copy is not a substitute for preserving every application state. For high-value documents, have the user confirm the document in Photoshop before any close or replacement.
