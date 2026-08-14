# ProBuilder Through DSH Unity MCP

ProBuilder is optional. Probe availability with `mcp__unity__manage_probuilder(action="ping")`; if the tool or package is absent, use ordinary primitives for disposable grayboxing.

## Workflow

1. Query the target and current mesh information.
2. Create or modify one shape with explicit dimensions and transform.
3. Perform face, edge, or vertex operations against stable target identifiers.
4. Validate the mesh, normals, smoothing, pivot, colliders, and material slots.
5. Save the scene/prefab and re-query the result.

Representative calls:

- `mcp__unity__manage_probuilder(action="create_shape", properties={"shape_type":"Cube","name":"Blockout"})`
- `mcp__unity__manage_probuilder(action="get_mesh_info", target="Blockout", properties={"include":"faces"})`
- `mcp__unity__manage_probuilder(action="extrude_faces", target="Blockout", properties={"faces":[0],"distance":2})`
- `mcp__unity__manage_probuilder(action="auto_smooth", target="Blockout", properties={"angleThreshold":30})`
- `mcp__unity__manage_probuilder(action="center_pivot", target="Blockout")`
- `mcp__unity__manage_probuilder(action="validate_mesh", target="Blockout")`

Keep blockouts editable, avoid over-modeling before traversal is accepted, and use saved screenshots only as pending visual evidence under the shared multimodal fallback.
