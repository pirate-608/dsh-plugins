# Layers and Selection

## Text Layers

`mcp__photoshop__photoshop_create_text_layer` can set:

- text content
- x/y position
- point size
- RGB color

It does not expose font family, weight, alignment, tracking, leading, layer name, text box bounds, or style effects. Inspect active-document information after creation and perform a visual check in Photoshop. Use UI control only when the unsupported typography settings are required.

## Filled Pixel Layers

Despite its name, `mcp__photoshop__photoshop_create_solid_color_layer` does not create a native Photoshop Solid Color Fill content/adjustment layer. It creates a normal art layer, selects the full canvas, fills pixels with the requested RGB color, and then deselects.

Consequences:

- The result is raster pixel content, not an editable fill-layer color property.
- Any selection that existed before the call is lost.
- The filled layer covers the full current canvas unless later edited.

Before using it:

1. Call `mcp__photoshop__photoshop_get_selection_info`.
2. If a selection is present and matters, stop; the MCP has no selection save/restore operation.
3. Explain the raster-layer result when the user's wording could mean a native fill layer.
4. Create the layer only after that distinction is acceptable.
5. Read layer information back and visually verify ordering, coverage, and color.

## Layer Inspection Limits

The `photoshop://document/layers` resource reports art layers and is not a complete representation of nested groups, adjustment/content layers, masks, or all Photoshop layer metadata. Do not use it as sole proof of visual correctness.
