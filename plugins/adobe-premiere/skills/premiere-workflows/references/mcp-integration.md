# Premiere MCP integration

## Architecture

The plugin starts the bundled Node MCP server over stdio. The server writes commands into `%TEMP%\premiere-mcp-bridge`; the installed `MCP Bridge (CEP)` panel polls that directory, executes ExtendScript through Premiere, and writes structured responses back.

Both sides must use the same temp directory. The plugin launcher defaults to:

```text
%TEMP%\premiere-mcp-bridge
```

## One-time Windows setup

Run `scripts/install-premiere-bridge.ps1` from the plugin root with elevated filesystem permission. The script:

- installs the bundled CEP extension under `%APPDATA%\Adobe\CEP\extensions\MCPBridgeCEP`;
- backs up an existing extension instead of deleting it;
- enables Adobe CEP `PlayerDebugMode` for CSXS 9 through 15;
- creates the shared temp directory;
- does not edit VS Code, Claude Desktop, or global DSH MCP configuration.

Restart Premiere afterward. Open `Window > Extensions > MCP Bridge (CEP)`, save the displayed temp directory, start the bridge, and test the connection.

## Safe operating sequence

1. Read `the documented MCP Tools inventory` when resources are available.
2. Inspect the project with `mcp__premiere_pro__get_project_info`.
3. List sequences and identify the active or user-requested sequence.
4. List project items and resolve stable item IDs before timeline operations.
5. Create a new sequence for experiments or generated assemblies.
6. Apply one logical mutation.
7. Read back the affected sequence, tracks, clips, effects, markers, captions, or metadata.
8. Save only after the verified state matches the request.

Prefer high-level tools such as `mcp__premiere_pro__assemble_product_spot` only when the request matches their contract and all referenced assets are real and imported. For precise edits, use sequence-aware tools and pass `sequenceId` whenever supported.

## Exports

Run `mcp__premiere_pro__validate_project_for_export` before export. Confirm the output path, preset, source range, and overwrite behavior. `mcp__premiere_pro__export_sequence` requires a real readable Adobe Media Encoder `.epr` preset; do not invent a preset path. `mcp__premiere_pro__get_render_queue_status` depends on Adobe Media Encoder integration.

## Diagnostics

When tools time out or return bridge errors:

1. Confirm Premiere is open and a project is loaded.
2. Confirm the CEP panel is open and says the bridge is started.
3. Confirm the panel directory equals `%TEMP%\premiere-mcp-bridge`.
4. Use `Test Connection`.
5. Use `Run Diagnostics`.
6. Inspect `%TEMP%\premiere-mcp-bridge\premiere-mcp-diagnostics-latest.json`.
7. Retry only after identifying the failure.

`mcp__premiere_pro__detect_silence` requires `ffmpeg` on `PATH` and analyzes source media directly; it does not read Premiere waveforms. Detection does not edit the timeline.

## Limits

Premiere's scripting APIs do not cover every UI operation. Use Windows app control for unsupported UI-only work and for visual review. Professional motion graphics require real MOGRT files and design assets. Do not treat successful script execution as proof that editorial or visual quality is acceptable.
