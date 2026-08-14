# DSH Unity MCP Tool Reference

All top-level calls use the `mcp__unity__` namespace. The MCP server may expose a subset based on the connected project and `--project-scoped-tools`.

## Connection and Readiness

- `mcp__unity__set_active_instance(instance="Project@hash")`: route to a known instance. It does not enumerate instances.
- `mcp__unity__refresh_unity(scope="all", compile="request", wait_for_ready=true)`: refresh/import and wait for readiness.
- `mcp__unity__read_console(action="get", types=["error", "warning"], include_stacktrace=true)`: inspect console output.

## Scene and Objects

- `mcp__unity__manage_scene(action="get_active")`: active scene facts.
- `mcp__unity__manage_scene(action="get_hierarchy", page_size=50, cursor=0, include_transform=true)`: paged hierarchy.
- `mcp__unity__find_gameobjects(search_term="Player", search_method="by_name")`: locate instance ids.
- `mcp__unity__manage_gameobject(action="create", name="Cube", primitive_type="Cube")`: create an object.
- `mcp__unity__manage_gameobject(action="modify", target="Player", position=[0, 1, 0])`: modify an object.
- `mcp__unity__manage_components(action="add", target="Player", component_type="Rigidbody")`: add a component.
- `mcp__unity__manage_components(action="set_property", target="Player", component_type="Rigidbody", property="mass", value=2)`: change a component property.

## Scripts, Tests, and Play Mode

- Use the server's script create/edit/validate tools with their `mcp__unity__` names and SHA-aware editing.
- `mcp__unity__manage_editor(action="play")`, `pause`, and `stop`: control play state.
- `mcp__unity__run_tests(mode="EditMode")`: start tests; poll with `mcp__unity__get_test_job` when a job id is returned.
- `mcp__unity__unity_reflect`: inspect live C# APIs; `mcp__unity__unity_docs` supplies documentation when available.

## Project Capabilities

- `mcp__unity__manage_packages`: installed packages, package details, and dependency changes.
- `mcp__unity__manage_build`: platform, settings, scenes, profiles, builds, and job status.
- `mcp__unity__manage_graphics`: pipeline, volumes, probes, renderer features, and render statistics.
- `mcp__unity__manage_physics(dimension="2d" | "3d", ...)`: settings, collision matrices, queries, bodies, forces, joints, and validation.
- `mcp__unity__manage_ui`: UI Toolkit assets and live UI operations.
- `mcp__unity__manage_profiler`: frame timing, counters, memory, captures, and Frame Debugger operations.
- `mcp__unity__manage_probuilder`: ProBuilder queries and mesh operations when installed.

## Batch Calls

The top-level call is `mcp__unity__batch_execute`. Its nested `commands[].tool` field is interpreted by MCP for Unity and therefore keeps raw names:

```json
{
  "commands": [
    { "tool": "find_gameobjects", "params": { "search_term": "Camera", "search_method": "by_component" } },
    { "tool": "find_gameobjects", "params": { "search_term": "Player", "search_method": "by_tag" } }
  ],
  "fail_fast": true
}
```

Do not batch dependency changes, compilation-sensitive edits, or operations whose target is produced by an earlier command.

## Screenshots

Use `mcp__unity__manage_camera(action="screenshot")` or the corresponding scene/UI file-output action. Omit inline-image options. Record the returned path and follow the text-first policy; a saved file is not proof that the model saw it.

## Unsupported MCP Capabilities

DSH v1 bridges Tools only. MCP Resources and Prompts are not callable, including consolidated project/editor state, instance enumeration, and resource-only object/component views. Use Tool queries where available and state the gap where no equivalent exists.
