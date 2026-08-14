---
name: unity-content-animation-vfx
description: Create, import, configure, and integrate Unity visual or audio content through Unity MCP. Use for textures and sprites, models, materials, shaders, animation clips and Animator Controllers, particles, Visual Effect Graph, LineRenderer and TrailRenderer effects, audio assets, procedural placeholders, asset import settings, prefab assembly, and visual or audiovisual verification.
---

# Unity Content, Animation & VFX

Build content as an auditable pipeline from source asset to imported asset, configured component, reusable prefab, and verified scene result.

## Workflow

1. Read editor state, project info, pipeline, installed content packages, target asset folder, and existing naming/import conventions.
2. Inspect before replacing. Preserve authored assets unless the user explicitly requests regeneration.
3. Create or import into organized `Assets/...` paths. Use MCP asset generation only for requested or clearly temporary content.
4. Configure import settings for the target platform and use case.
5. Create materials or shaders compatible with the detected pipeline; inspect shader properties before setting them.
6. Configure animation, audio, particle, VFX Graph, line, or trail components with the appropriate management tool.
7. Assemble reusable content into prefabs and instantiate prefabs through `mcp__unity__manage_gameobject`.
8. Wait for imports and compilation, inspect the console, enter Play mode when runtime playback matters, and save screenshots without inline image payloads.

## Content Rules

- Keep generated placeholders visibly named and segregated so they are easy to replace.
- For sprites, set type, pixels-per-unit, pivot, sprite mode, filtering, compression, and mipmaps intentionally.
- For 3D models, preserve scale, rig, material, and animation conventions already used by the project.
- Do not assume Standard, URP, or HDRP shader names. Use pipeline info, reflection, and material inspection.
- Prefer material property blocks for per-renderer variation when a new material asset is unnecessary.
- Separate authored animation clips, Animator Controllers, parameters, transitions, and runtime driver code.
- Verify VFX Graph availability before using `vfx_*` actions; provide a ParticleSystem fallback only when it meets the brief.
- Treat audio loudness, looping, spatial blend, mixer routing, and import compression as part of integration.
- Never request inline image payloads. DSH's current MCP bridge renders non-text blocks as placeholders, and the active model may have no image-input capability.

## Verification Gate

Confirm imports, references, pipeline selection, animation/VFX/audio state, and console output through text or structured tool results. Return screenshot paths as evidence and mark visual quality pending until a user or verified multimodal host confirms it.

Read the shared [tool reference](../unity-mcp-skill/references/tools-reference.md) for texture, material, shader, animation, VFX, asset-generation, and prefab parameters.
