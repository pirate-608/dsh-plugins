# Text-First and Multimodal Fallback

## Baseline

Treat every run as text-only unless the host explicitly exposes image input for the active adapter. Model brand or model name is not capability evidence. DSH currently turns non-text MCP result blocks into placeholders in model context, so an MCP screenshot response is not visible merely because the server returned image data.

## Evidence Order

1. Structural: hierarchy, components, transforms, asset paths, package and scene settings.
2. Runtime: console, compilation readiness, tests, builds, play-state queries.
3. Quantitative: profiler counters, render statistics, memory, camera and layout parameters.
4. Visual artifact: a saved screenshot path for later review.

Never collapse these categories into a generic "verified" statement.

## Screenshot Rule

Use file-output screenshot actions and omit inline-image flags. Return the path and the capture source, camera, resolution, and intended review question. A path proves that an artifact was created, not that its contents are correct.

If the user attaches the screenshot later, inspect it only when the host confirms that the active model can accept images. Otherwise provide a manual checklist and keep visual verification pending.

## Manual Checklists

For UI: clipping, overlap, contrast, focus visibility, text truncation, safe areas, target aspect ratios, loading/disabled/error states.

For 2D/3D scenes: focal points, silhouette, scale, occlusion, lighting, material correctness, camera framing, collision-vs-visible geometry.

For animation/VFX: timing, looping, transitions, particle bounds, shader/pipeline compatibility, audio synchronization.

## Reintroduction Condition

Automated visual closure requires all of the following: end-to-end MCP image projection, an adapter-declared image-input capability, session-log reconstruction of the model-visible image, and separate text-only and multimodal regression coverage.
