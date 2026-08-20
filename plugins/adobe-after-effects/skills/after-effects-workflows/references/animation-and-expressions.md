# Animation and expressions

## Plan the motion

Identify the target comp, layers, work area, frame rate, key beats, interpolation style, loop behavior, and whether the motion must remain editable. Separate measurable constraints from aesthetic judgment.

Prefer controls and expressions only when they reduce repeated manual edits. Keep source properties, controllers, and presentation layers distinct. Use stable layer/property locators from current state instead of assuming layer indices survive insertions.

## Keyframes

- Work in composition time and respect display-frame conversion at the active frame rate.
- Verify property dimensionality before setting values or temporal ease arrays.
- Preserve existing keys outside the requested range.
- Read back key count, times, values, interpolation, and expressions after mutation.
- Review the start, major extrema or beats, and end; fast motion usually needs in-between frames.
- Avoid unintended overshoot, negative scale, invalid opacity, or bad spatial tangents.

## Expressions

- Read the current expression and property value before replacement.
- Use locale-independent match names for effect/property addressing when available.
- Run `mcp__after_effects__ae_validateExpressions`, then preview representative frames; valid syntax may still produce wrong motion.
- Avoid unbounded loops, dependency cycles, nondeterministic file/network access, and project-wide rewrites without a checkpoint.
- Verify named controller and layer dependencies after renaming or duplication.

## Text and shape layers

- Treat Source Text as a TextDocument-style value: retrieve, modify, then set it back.
- Confirm font availability and use the actual PostScript font name where required.
- Preserve paragraph/character styling unless the user requests a reset.
- When adding indexed shape/effect properties, create the property, reacquire a stable reference, then set sub-properties.
- Resolve targets again after structural edits because new layers can change indices.

Parameter readback proves structure, not design quality. Use `mcp__after_effects__ae_previewFrame` for comp pixels and state which times were inspected.
