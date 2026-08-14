---
name: unity-gameplay-development
description: Implement and refactor Unity gameplay systems through Unity MCP. Use for C# MonoBehaviours, ScriptableObjects, input, character or vehicle controllers, combat, interactions, spawning, inventory, state machines, events, save data, prefabs, scene flow, gameplay architecture, package-backed features, EditMode or PlayMode tests, and attaching verified scripts to live scene objects.
---

# Unity Gameplay Development

Implement one testable gameplay slice at a time while keeping scene state and C# compilation synchronized.

## Workflow

1. Read editor state, project info, relevant hierarchy nodes, components, prefabs, scripts, tests, and console output.
2. State the behavior contract: inputs, state, outputs, failure cases, and acceptance checks.
3. Verify Unity and package APIs with `mcp__unity__unity_reflect`; use `mcp__unity__unity_docs` when reflection or project assets do not answer the question.
4. Reuse the project's architecture and naming. Prefer serialized references, ScriptableObjects, or existing services over global object searches in hot paths.
5. Create or edit scripts with script tools. Use SHA-aware edits; never overwrite a changed file blindly.
6. Wait until compilation and domain reload finish, then read full compile errors.
7. Attach components and configure serialized fields only after the type compiles.
8. Create focused EditMode tests for pure logic and PlayMode tests for scene/runtime behavior. Run the narrowest relevant tests first, then the affected suite.
9. Exercise the feature in Play mode. Save screenshots for visual behavior, return their paths, and leave visual inspection pending in text-only sessions.
10. Stop Play mode, save persistent changes, and summarize code, scene, prefab, and test changes separately.

## Engineering Rules

- Do not edit `.unity`, `.prefab`, or `.asset` YAML while the Editor is connected.
- Avoid unrelated refactors. Preserve public serialized field names or use migration attributes when renaming.
- Keep frame-loop code allocation-aware. Cache stable references and avoid repeated hierarchy searches.
- Make input-system assumptions explicit. Inspect whether the project uses the legacy Input Manager, Input System package, or both.
- Keep editor-only APIs out of player assemblies and runtime paths.
- Use `mcp__unity__execute_code` for bounded editor automation or inspection, not as a hidden replacement for maintainable project code.
- Add Undo support and mark assets/scenes dirty when custom editor code mutates serialized state.

## Completion Gate

Require successful compilation, no new console errors, passing targeted tests, observed non-visual behavior in Play mode when applicable, and saved scene/prefab assets. Never infer visual correctness from a screenshot path alone.

Read the shared [tool reference](../unity-mcp-skill/references/tools-reference.md) for script, prefab, test, reflection, and docs tool details.
