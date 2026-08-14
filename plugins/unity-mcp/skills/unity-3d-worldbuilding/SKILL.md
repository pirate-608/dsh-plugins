---
name: unity-3d-worldbuilding
description: Design, block out, light, and validate Unity 3D scenes through Unity MCP. Use for level grayboxing, ProBuilder geometry, GameObject hierarchy, materials, terrain-like layouts, cameras and Cinemachine, 3D colliders and rigidbodies, lighting, light or reflection probes, skybox, fog, post-processing, URP or HDRP volumes, environment composition, and 3D scene visual review.
---

# Unity 3D Worldbuilding

Turn a scene brief into an editable and navigable 3D environment with structural, runtime, and separately tracked visual evidence.

## Workflow

1. Read editor state, project info, hierarchy, cameras, pipeline info, volumes, and rendering stats.
2. Translate the request into scale, player path, focal points, camera views, lighting mood, and performance constraints.
3. Block out with primitives for simple disposable geometry. When ProBuilder is installed, prefer `mcp__unity__manage_probuilder` for editable level geometry and per-face material work.
4. Organize geometry under named roots; use meaningful layers and static flags. Create prefabs for repeated authored units.
5. Create or reuse materials, then assign them by renderer slot. Do not duplicate materials unintentionally.
6. Configure colliders and `mcp__unity__manage_physics(..., dimension="3d")`; validate gaps, missing colliders, and collision layers.
7. Configure camera composition and lighting. Use `mcp__unity__manage_graphics` for skybox, fog, volumes, probes, baking, and pipeline settings.
8. Save surround and player-view screenshots without inline payloads. Use hierarchy, transforms, camera settings, collision checks, and rendering statistics for text-only iteration.
9. Save the scene and check console plus rendering stats.

## Worldbuilding Rules

- Use consistent real-world scale unless the project establishes another convention.
- Separate gameplay collision, visible meshes, triggers, navigation markers, and decorative props in the hierarchy.
- Keep graybox geometry editable. Do not over-invest in materials before traversal and proportions are approved.
- Treat light baking as an Edit-mode operation. Check bake status and errors; never assume a bake completed.
- Detect Built-in, URP, or HDRP before using shader, post-processing, or renderer-feature assumptions.
- Use reflection and official docs to verify pipeline-specific APIs.
- Measure before adding post effects. Preserve mobile, XR, or WebGL budgets when those targets are present.

## Visual Acceptance Gate

Save at least one gameplay camera image and one Scene View or surround image. Confirm physics validation, camera parameters, hierarchy, rendering statistics, console state, and scene persistence. Report visual route and focal-point review as pending until a user or verified multimodal host confirms it.

Read the shared [ProBuilder guide](../unity-mcp-skill/references/probuilder-guide.md) when modeling and the shared [tool reference](../unity-mcp-skill/references/tools-reference.md) for exact actions.
