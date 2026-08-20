# Bundled renpy-mcp runtime

This directory vendors `renpy-mcp` 0.1.0 for the plugin's local stdio MCP
server. The upstream package is licensed under AGPL-3.0-or-later; see
`LICENSE`.

Runtime dependencies are resolved by `uv`. The Ren'Py SDK is not bundled;
`scripts/start_renpy_mcp.py` discovers it from `RENPY_SDK`, the active
project's SDK cache, or common user locations.

Pillow is included in this runtime for the plugin's deterministic
`scripts/prepare_renpy_asset.py` image normalization workflow; image generation
itself remains a Codex host capability and does not use an API key here.
