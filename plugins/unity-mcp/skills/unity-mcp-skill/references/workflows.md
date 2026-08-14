# Shared Unity Workflows

## Safe Mutation

1. Query the active scene and relevant target ids.
2. Read the narrowest available settings and console evidence.
3. Apply one bounded mutation or an independent batch.
4. Wait for imports/compilation when applicable.
5. Re-query the changed state, run focused tests, and save.

## Script Change

1. Read the current file and SHA through the appropriate script tool.
2. Apply a SHA-aware edit.
3. Call `mcp__unity__refresh_unity(scope="scripts", compile="request", wait_for_ready=true)`.
4. Read `mcp__unity__read_console(action="get", types=["error"], include_stacktrace=true)`.
5. Attach or invoke the component only after compilation succeeds.

## UI Creation

1. Inspect existing UI system, packages, assets, Canvas/UIDocument hierarchy, and input module.
2. Create semantic structure, reusable styles, explicit scaling, and navigation.
3. Enter Play mode and exercise pointer plus configured keyboard/controller paths.
4. Save file-output captures at representative aspect ratios.
5. Report structural and runtime status; leave visual verification pending unless explicitly confirmed.

## Visual Artifact Handoff

For each saved capture report: absolute or project-relative path, capture source, camera/view, resolution, state under test, and a concise manual checklist. Never say that a text-only model inspected the image.

## Multi-Instance

When the user provides an instance id, select it once with `mcp__unity__set_active_instance` and verify with an idempotent scene query. If the id is unknown, ask the user to obtain it from the Unity MCP UI; do not claim DSH enumerated the Resources endpoint.
