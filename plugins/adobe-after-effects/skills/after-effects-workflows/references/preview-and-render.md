# Preview, render, and delivery

## Visual review

Use `mcp__after_effects__ae_previewFrame` for composition pixels. Use `mcp__after_effects__ae_snapshot` only when viewer context itself matters. A desktop screenshot is not render evidence.

Review start/end boundaries, key visual beats, movement/effect extrema, text changes, expression branches, alpha edges, and color-management-sensitive shots. Check clipping, transparency, missing fonts/media, expression warnings, layer order, temporal discontinuities, and aspect ratio.

## Render preparation

Inspect the target composition/work area, dimensions, pixel aspect, frame rate, duration, renderer, color management, output module/codec, channels, alpha, audio, file extension, output path, free space, existing files, and image-sequence collision risk.

Do not guess a delivery codec or overwrite output. Ask when the destination is ambiguous or a preset/plugin is unavailable.

## Render verification

After rendering, verify output exists and is non-empty. When possible, inspect duration, dimensions, frame rate, channels, and representative frames. Report only the highest completed level:

1. queue/settings verified;
2. render completed and output exists;
3. output metadata verified;
4. representative output frames visually reviewed;
5. full playback/audio reviewed.
