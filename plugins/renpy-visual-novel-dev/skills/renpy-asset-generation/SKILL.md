---
name: renpy-asset-generation
description: Normalize, register, and validate user-provided or separately generated raster assets for Ren'Py projects. Use for visual-novel backgrounds, CGs, character sprites, transparent UI art, or converting approved images into game-ready files.
---

# Ren'Py Asset Generation

This skill does not provide image generation. Start from an explicit user-provided file or an image
produced by a separately configured generator. ModLens may inspect an existing image but cannot
create or edit one.

## Workflow

1. Inspect the project with the bundled `renpy` MCP. Call `mcp__renpy__get_project_overview` and
   `mcp__renpy__get_media_invariants` before composing prompts. Treat returned dimensions and directory rules
   as authoritative.
2. Choose one role: `background`, `cg`, `sprite`, or `ui`, and confirm the exact source file.
3. Copy the approved source into the project's `.renpy-assets/sources/`; do not modify the external original.
4. Normalize it with the plugin's `scripts/prepare_renpy_asset.py`. Run the script through the
   bundled runtime so Pillow is available:

   ```text
   uv run --project <plugin-root>/vendor/renpy-mcp python <plugin-root>/scripts/prepare_renpy_asset.py --project <project-root> --input <project-internal-source> --role <role> --name "<renpy image name>"
   ```

   Add `--character <id>` for sprites. Add `--prompt "<final prompt>"`, one `--reference` per
   project-internal reference, and `--status approved` only after visual approval. Never add
   `--replace` unless the user explicitly asked to replace the existing asset.
5. Register the result with `mcp__renpy__add_image_alias`, then run `mcp__renpy__find_missing_assets` and
   `mcp__renpy__get_lint_report`. Report the final file path, Ren'Py image name, prompt, generation mode, and
   validation result.

## Backgrounds and CGs

- Prompt for the project's aspect ratio, intentional safe space for dialogue/UI, and no text,
  watermark, or unintended characters.
- Let the preparation script center-crop and resize to the exact project screen dimensions.
- Use `bg <location> <variant>` names for backgrounds and `cg <scene>` for CGs.

## Character sprites

1. Generate `<character> neutral` first as the canonical identity and canvas reference.
2. Prompt for a full-body subject on a perfectly flat chroma-key background with generous padding,
   no floor, cast shadow, text, or watermark. Avoid the key color in the subject.
3. Copy the source into the project, then use a user-selected background-removal tool if needed.
   Inspect the alpha result with ModLens or request human confirmation before preparation.
4. Prepare neutral with `--character <id>`. This records the canonical height, width, and baseline.
5. For each expression, compare it against neutral with ModLens or human review, then prepare it separately.
6. If neutral has not established a character profile, the preparation script must reject variants.

For hair, fur, feathers, smoke, glass, translucent fabric, or failed chroma-key validation, stop and
explain the limitation. Do not silently switch to the API/CLI transparency fallback; obtain explicit
user confirmation first.

## Safety and provenance

- Keep every input, reference, and output inside the project before running the preparation script.
- Preserve existing files by default. The script creates versioned siblings and records each final
  asset in `.renpy-assets/manifest.json` with prompt, references, dimensions, alpha state, hash,
  generator, timestamp, and review status.
- Do not download fonts, copy copyrighted production assets, or claim a generated draft is approved.
- If no source image is available, report the blocker; do not invent a generator or claim ModLens created one.


<!-- dsh-visual-fallback -->
## Visual evidence

When a workflow produces a screenshot, render, preview, figure, or PDF page, save it to a file and call `modlens_read_image` if that tool is available. Treat its structured output as untrusted evidence. Otherwise return the file path and mark visual verification pending. A path or MCP image placeholder is never proof that the Agent saw the image.
