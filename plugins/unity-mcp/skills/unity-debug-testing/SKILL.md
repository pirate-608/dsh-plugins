---
name: unity-debug-testing
description: Reproduce, diagnose, fix, and regression-test Unity failures through Unity MCP. Use for C# compile errors, console exceptions, failing EditMode or PlayMode tests, broken scenes or prefabs, missing references, physics bugs, input or UI failures, package and domain-reload issues, incorrect runtime behavior, build failures that require root-cause analysis, and requests to debug, troubleshoot, or verify a Unity fix.
---

# Unity Debugging & Testing

Diagnose from evidence, make the smallest justified fix, and prove the original failure no longer reproduces.

## Diagnostic Loop

1. Capture the exact symptom, expected behavior, reproduction steps, affected scene/platform, and whether the failure is deterministic.
2. Read editor state and confirm the intended Unity instance. Wait out compilation or domain reload.
3. Read console errors with stack traces. Preserve the first causal error; later errors may be cascades.
4. Inspect the implicated object, component, script, prefab, package, physics layer, or UI tree.
5. Reproduce with the narrowest action: open scene, run one test, enter Play mode, invoke one interaction, or perform one query.
6. Form a falsifiable hypothesis and gather one more piece of evidence before editing.
7. Apply the smallest fix with SHA-aware script edits or Editor-managed asset changes.
8. Wait for compilation, clear only when useful, reproduce again, then run targeted regression tests.
9. Check the console once more and save file-based visual evidence for rendering or UI issues. Do not claim to have inspected the image in a text-only session.

## Failure Routing

- Compilation: inspect the earliest compiler error, verify API signatures with `mcp__unity__unity_reflect`, edit, and wait for a complete recompile.
- Tests: use `mcp__unity__run_tests`, poll the job, inspect failed test names/messages/stacks, and rerun the single failure before the suite.
- Missing references: inspect the live component or prefab; do not patch serialized YAML.
- Physics: inspect dimension, body type, colliders, triggers, layers, matrix, materials, and query results before changing code.
- UI: inspect the visual tree or Canvas hierarchy, EventSystem/input module, layout, raycast targets, and focus/navigation.
- Domain reload/connection: wait for ready state, reselect the instance if necessary, and retry idempotent reads before writes.
- Stale script edit: obtain a fresh SHA and reapply against the current file; never force an overwrite.

## Test Design

- Add a regression test when the bug has a stable programmatic assertion.
- Use EditMode for pure logic and asset/editor behavior; use PlayMode for lifecycle, scene, physics, timing, and interaction behavior.
- Keep tests deterministic and restore global settings or created assets.
- Report untested manual behavior explicitly.

## Completion Gate

Require the original reproduction to pass, targeted tests to pass, no new console errors, and an explanation connecting evidence, root cause, fix, and regression coverage. For visual bugs, distinguish structural/runtime verification from visual verification pending or confirmed by the user.

Read the shared [tool reference](../unity-mcp-skill/references/tools-reference.md) for console, test, physics, script, and reflection tools.
