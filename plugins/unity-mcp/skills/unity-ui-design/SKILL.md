---
name: unity-ui-design
description: Design, build, and visually validate Unity interfaces through Unity MCP. Use for UI Toolkit UXML and USS, UIDocument and PanelSettings, uGUI Canvas hierarchies, TextMeshPro, menus, HUDs, dialogs, settings, inventory, responsive anchors and layouts, controller or keyboard navigation, accessibility states, UI interaction wiring, and screenshot-driven UI review.
---

# Unity UI Design

Choose the project's existing UI system and build a complete interaction slice. Treat visual validation as a separate capability that may require the user because the active model can be text-only.

## Choose the UI System

1. Inspect existing UI assets and scene components with UI, package, hierarchy, and component tools. DSH does not bridge the project-info MCP Resource.
2. Continue with the established system unless the user asks for a migration.
3. Prefer UI Toolkit for UXML/USS-based runtime or editor UI in projects already using it.
4. Prefer uGUI for existing Canvas workflows, world-space UI, or package integrations built around Canvas components.
5. Use IMGUI only for custom Editor tooling that requires it; implement it in C# rather than forcing it through runtime UI tools.

## UI Toolkit Workflow

1. Use `mcp__unity__manage_ui(action="list")` and read existing UXML, USS, UIDocument, and PanelSettings assets.
2. Create semantic UXML structure and reusable USS classes.
3. Link stylesheets with `mcp__unity__manage_ui(action="link_stylesheet")`; use `<ui:Style>`, never a bare `<Style>` element.
4. Create or reuse PanelSettings with explicit scale mode and reference resolution.
5. Attach the UIDocument, inspect the visual tree, and modify named live elements when iterating.
6. Use `mcp__unity__render_ui` only in file-output mode. Return the saved path and mark visual verification pending; never request or claim analysis of inline image output.

## uGUI Workflow

1. Inspect Canvas, EventSystem, TextMeshPro, Input System, and existing layout conventions.
2. Create the hierarchy in batches: Canvas, safe-area/root layout, panels, controls, text, and feedback layers.
3. Configure anchors, pivots, offsets, CanvasScaler, Layout Groups, ContentSizeFitter, navigation, and raycast targets deliberately.
4. Wire behavior through compiled scripts and serialized references. Avoid fragile name-based lookups.
5. Enter Play mode and save Game View captures at representative aspect ratios. Report their paths for user or future multimodal review.

## Design and Accessibility Rules

- Define states for normal, hover/focus, pressed, selected, disabled, validation error, loading, empty, and success where relevant.
- Keep touch targets, contrast, text size, focus order, controller navigation, and localization expansion in scope.
- Reuse typography, spacing, color, and component tokens instead of styling each control independently.
- Verify safe areas and wide/tall aspect ratios for mobile UI.
- Do not declare visual success from hierarchy alone. A text-only run may complete structural and interaction checks while leaving visual verification pending.

## Completion Gate

Require a clean console, functional pointer and configured non-pointer navigation, correct state transitions, and saved UI assets/scenes. Report one of `Visual verification pending` or `Visual verification confirmed by user`; only a host that explicitly exposes image input may report model-performed visual verification.

Read the shared [UI workflows](../unity-mcp-skill/references/workflows.md#ui-creation-workflows) and [tool reference](../unity-mcp-skill/references/tools-reference.md) as needed.
