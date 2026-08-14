---
name: unity-project-setup
description: Configure and audit an existing Unity project through Unity MCP. Use for project initialization, package installation or removal, render-pipeline checks, Input System or Cinemachine setup, tags, layers, physics defaults, scene lists, ScriptableObject configuration, and project readiness before feature work. Trigger on requests such as setup/configure this Unity project, install a Unity package, prepare a 2D or 3D project, or fix missing project dependencies.
---

# Unity Project Setup

Prepare a connected Unity project for reliable feature work without hand-editing serialized Unity files.

## Workflow

1. Establish readiness with an idempotent query. After imports or script changes, use `mcp__unity__refresh_unity(wait_for_ready=true)` before continuing.
2. Derive project facts from tool queries: package inventory, active scene and build settings, graphics-pipeline probes, and configured physics dimensions. DSH does not bridge MCP Resources, so do not claim a consolidated project-info resource was read.
3. Read installed packages with `mcp__unity__manage_packages(action="list")`. Query package details before changing dependencies.
4. Inspect existing scenes, tags, layers, physics settings, and pipeline settings before mutation.
5. Propose the smallest configuration delta. Preserve the project's chosen pipeline and conventions unless the user asks for a migration.
6. Apply related independent changes with `mcp__unity__batch_execute`; keep dependency-changing calls sequential and poll their job status.
7. Wait for imports and compilation, then read console errors and warnings.
8. Save affected scenes/assets and report exact packages and settings changed.

## Package Rules

- Use `mcp__unity__manage_packages`; never hand-edit `Packages/manifest.json` while the Editor is connected.
- Prefer released package versions compatible with the detected Editor. Use `mcp__unity__unity_docs` or package info instead of guessing versions.
- Check dependents before removal. Use force only after explaining what will break.
- Treat Git URLs and scoped registries as supply-chain changes; show the source before installing.
- Install only what the requested workflow needs. Typical optional packages include Input System, Cinemachine, ProBuilder, UI Toolkit dependencies, Test Framework, Memory Profiler, and platform-specific packages.

## Project Configuration

- Use `mcp__unity__manage_editor` for tags and layers; read existing names first and avoid repurposing occupied slots.
- Use `mcp__unity__manage_build(action="scenes")` to audit or update build scenes.
- Use `mcp__unity__manage_graphics(action="ping")` and pipeline query actions before URP/HDRP changes.
- Use `mcp__unity__manage_physics` with `dimension="2d"` or `dimension="3d"`; do not mix settings implicitly.
- Create reusable configuration as ScriptableObjects when it is project data, not scene state.
- For multiple open Editors, call `mcp__unity__set_active_instance` only when the user supplies a known instance identifier. DSH v1 cannot enumerate the MCP instances resource.

## Verification Gate

Do not call setup complete until the Editor is ready, the console has no new compile errors, installed packages match the plan, and at least one target scene opens successfully.

For exact tool parameters, read the shared [tool reference](../unity-mcp-skill/references/tools-reference.md) only for the tools used.
