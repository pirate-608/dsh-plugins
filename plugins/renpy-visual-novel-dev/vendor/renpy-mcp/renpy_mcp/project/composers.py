"""Visual composer code generators.

Each composer turns a typed JSON tree into one Ren'Py construct.
Generators here are pure (no I/O); the Tier 3 tools that wrap them
route the produced text through `apply_write`.

Phase 7 ships the Screen Layout composer first because its grammar is
the most regular: every widget is either a container with children or a
leaf with properties. Future composers (Scene, ImageMap, Menu) will
follow the same pure-generator + Tier-3-wrapper shape.
"""

from __future__ import annotations

from typing import Any

from ..guardrails.dialogue import escape_dialogue, reject_multiline
from ..tools._shared import BODY_INDENT, quote


class CompositionError(Exception):
    """Raised when a composer tree fails validation."""


# ---------- Screen Layout composer --------------------------------------------


_CONTAINER_KINDS = frozenset({"vbox", "hbox", "frame"})
_LEAF_TEXT_KINDS = frozenset({"text", "textbutton"})
_KNOWN_KINDS = _CONTAINER_KINDS | _LEAF_TEXT_KINDS | frozenset({"button", "spacer"})


def generate_screen_layout(name: str, root: dict[str, Any]) -> str:
    """Produce the source text for `screen <name>():` from a typed tree.

    `root` is a widget node:
        {kind: "vbox" | "hbox" | "frame", children: [...], props?: {...}}
        {kind: "text", text: "...", props?: {...}}
        {kind: "textbutton", text: "...", action: "...", props?: {...}}
        {kind: "button", action: "...", children: [...], props?: {...}}
        {kind: "spacer", height?: <int>, width?: <int>}

    Properties render as indented body lines (`xalign 0.5`). Text values
    are auto-escaped through the dialogue guardrail. Containers and the
    `button` kind nest their children one indent level deeper.
    """
    if not isinstance(name, str) or not name.isidentifier():
        raise CompositionError(f"screen name `{name}` is not a valid identifier")
    if not isinstance(root, dict):
        raise CompositionError("root must be a widget object")
    body = _render_widget(root, depth=1)
    return "\n".join([f"screen {name}():", *body, ""])  # trailing newline


def _render_widget(node: Any, *, depth: int) -> list[str]:
    if not isinstance(node, dict):
        raise CompositionError("each widget must be an object")
    kind = node.get("kind")
    if kind not in _KNOWN_KINDS:
        raise CompositionError(
            f"unknown widget kind `{kind}` (allowed: {sorted(_KNOWN_KINDS)})"
        )
    indent = BODY_INDENT * depth
    body_indent = BODY_INDENT * (depth + 1)
    props = node.get("props") or {}
    if not isinstance(props, dict):
        raise CompositionError(f"`{kind}` props must be an object")
    prop_lines = [f"{body_indent}{_render_prop(k, v)}" for k, v in props.items()]

    if kind in _CONTAINER_KINDS:
        out = [f"{indent}{kind}:"]
        out.extend(prop_lines)
        for child in node.get("children", []):
            out.extend(_render_widget(child, depth=depth + 1))
        if not prop_lines and not node.get("children"):
            # Empty container — Ren'Py needs SOMETHING in the block, so
            # emit a `null` body to keep it parse-clean.
            out.append(f"{body_indent}null")
        return out

    if kind == "text":
        text = node.get("text")
        if not isinstance(text, str):
            raise CompositionError("`text` widget needs a `text` string")
        if msg := reject_multiline(text):
            raise CompositionError(f"text: {msg}")
        rendered = quote(escape_dialogue(text))
        if prop_lines:
            return [f"{indent}text {rendered}:", *prop_lines]
        return [f"{indent}text {rendered}"]

    if kind == "textbutton":
        text = node.get("text")
        action = node.get("action")
        if not isinstance(text, str):
            raise CompositionError("`textbutton` needs a `text` string")
        if not isinstance(action, str) or not action.strip():
            raise CompositionError("`textbutton` needs a non-empty `action` expression")
        if msg := reject_multiline(text):
            raise CompositionError(f"textbutton text: {msg}")
        rendered = quote(escape_dialogue(text))
        head = f"{indent}textbutton {rendered} action {action.strip()}"
        if prop_lines:
            return [f"{head}:", *prop_lines]
        return [head]

    if kind == "button":
        action = node.get("action")
        if not isinstance(action, str) or not action.strip():
            raise CompositionError("`button` needs a non-empty `action` expression")
        out = [f"{indent}button:"]
        out.append(f"{body_indent}action {action.strip()}")
        out.extend(prop_lines)
        for child in node.get("children", []):
            out.extend(_render_widget(child, depth=depth + 1))
        return out

    if kind == "spacer":
        parts = []
        height = node.get("height")
        width = node.get("width")
        if height is not None:
            if not isinstance(height, (int, float)):
                raise CompositionError("`spacer.height` must be numeric")
            parts.append(f"height={_num(height)}")
        if width is not None:
            if not isinstance(width, (int, float)):
                raise CompositionError("`spacer.width` must be numeric")
            parts.append(f"width={_num(width)}")
        if not parts:
            raise CompositionError("`spacer` needs at least one of height/width")
        return [f"{indent}add Null({', '.join(parts)})"]

    # Unreachable — _KNOWN_KINDS check above.
    raise CompositionError(f"unhandled widget kind `{kind}`")


def _render_prop(name: Any, value: Any) -> str:
    """Render a single property line. Property names must be identifiers."""
    if not isinstance(name, str) or not name.isidentifier():
        raise CompositionError(f"property name `{name}` is not a valid identifier")
    if isinstance(value, bool):
        rendered = "True" if value else "False"
    elif isinstance(value, (int, float)):
        rendered = _num(value)
    elif isinstance(value, str):
        # Properties accept either bare identifiers (`xalign 0.5`) or
        # quoted strings. We pass strings through quote() so spaces and
        # special characters survive cleanly. Bare-identifier values
        # should be passed as numbers or via a separate API later.
        rendered = quote(value)
    elif value is None:
        rendered = "None"
    else:
        raise CompositionError(
            f"unsupported value type for property `{name}`: {type(value).__name__}"
        )
    return f"{name} {rendered}"


def _num(n: float) -> str:
    if isinstance(n, bool):  # bool is an int subclass; should never reach here
        return "True" if n else "False"
    if isinstance(n, int) or n == int(n):
        return str(int(n))
    return f"{n:g}"


# ---------- Stage composer (Vangard's "Scene Composer") -----------------------
#
# Generates the body lines for a layered stage setup:
#
#     scene <bg>
#     show <tag1> [<expr>] [at <pos>]
#     show <tag2> [<expr>] [at <pos>]
#     with <transition>
#
# This is the Tier 3 "compose multi-sprite stage" intent. Renamed from
# "Scene Composer" to dodge Ren'Py's `scene` keyword collision — agents
# scanning the tool list shouldn't have to disambiguate two `scene`-
# adjacent tools (`create_scene`, the new composer). The Composers panel
# section title still reads "Stage Composer" for the same reason.


def generate_stage(
    background: str | None = None,
    sprites: list[dict[str, Any]] | None = None,
    transition: str | None = None,
) -> list[str]:
    """Return the unindented body lines for a stage setup.

    Caller is responsible for indentation — `insert_into_label_body`
    indents at one BODY_INDENT for label bodies. Raises CompositionError
    on bad input.
    """
    sprites = sprites or []
    if not background and not sprites:
        raise CompositionError(
            "stage needs at least a background or one sprite"
        )

    out: list[str] = []
    if background is not None:
        if not isinstance(background, str) or not background.strip():
            raise CompositionError("background must be a non-empty string")
        if msg := reject_multiline(background):
            raise CompositionError(f"background: {msg}")
        out.append(f"scene {background.strip()}")

    for i, sprite in enumerate(sprites):
        if not isinstance(sprite, dict):
            raise CompositionError(f"sprite #{i} must be an object")
        tag = sprite.get("tag")
        if not isinstance(tag, str) or not tag.isidentifier():
            raise CompositionError(f"sprite #{i} `tag` must be a Python identifier")
        expression = sprite.get("expression")
        position = sprite.get("position")
        if expression is not None:
            if not isinstance(expression, str):
                raise CompositionError(f"sprite #{i} `expression` must be a string")
            if not all(p.isidentifier() for p in expression.split()):
                raise CompositionError(
                    f"sprite #{i} `expression` must be space-separated identifiers"
                )
        if position is not None:
            if not isinstance(position, str) or not position.strip():
                raise CompositionError(f"sprite #{i} `position` must be a non-empty string")
            if msg := reject_multiline(position):
                raise CompositionError(f"sprite #{i} position: {msg}")
        parts = ["show", tag]
        if expression:
            parts.append(expression)
        if position:
            parts.append(f"at {position.strip()}")
        out.append(" ".join(parts))

    if transition is not None:
        if not isinstance(transition, str) or not transition.strip():
            raise CompositionError("transition must be a non-empty string")
        if msg := reject_multiline(transition):
            raise CompositionError(f"transition: {msg}")
        out.append(f"with {transition.strip()}")

    return out


# ---------- ImageMap composer -------------------------------------------------
#
# Generates a screen block whose body is a single `imagemap:` definition.
# A hotspot is a `(x y w h)` rect bound to an action expression.


def generate_imagemap(
    name: str,
    ground: str,
    hover: str,
    hotspots: list[dict[str, Any]],
) -> str:
    """Render a `screen <name>():` block whose body is an `imagemap:`."""
    if not isinstance(name, str) or not name.isidentifier():
        raise CompositionError(f"screen name `{name}` is not a valid identifier")
    if not isinstance(ground, str) or not ground.strip():
        raise CompositionError("`ground` must be a non-empty image path")
    if not isinstance(hover, str) or not hover.strip():
        raise CompositionError("`hover` must be a non-empty image path")
    if not isinstance(hotspots, list) or not hotspots:
        raise CompositionError("`hotspots` must be a non-empty list")

    body: list[str] = [f"screen {name}():"]
    body.append(f"{BODY_INDENT}imagemap:")
    body.append(f"{BODY_INDENT * 2}ground {quote(ground)}")
    body.append(f"{BODY_INDENT * 2}hover {quote(hover)}")
    for i, hs in enumerate(hotspots):
        body.append(f"{BODY_INDENT * 2}{_render_hotspot(hs, i)}")
    body.append("")
    return "\n".join(body)


def _render_hotspot(hs: Any, idx: int) -> str:
    if not isinstance(hs, dict):
        raise CompositionError(f"hotspot #{idx} must be an object")
    rect_keys = ("x", "y", "w", "h")
    rect: list[str] = []
    for key in rect_keys:
        v = hs.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise CompositionError(f"hotspot #{idx} `{key}` must be numeric")
        rect.append(_num(v))
    action = hs.get("action")
    if not isinstance(action, str) or not action.strip():
        raise CompositionError(f"hotspot #{idx} needs a non-empty `action` expression")
    if msg := reject_multiline(action):
        raise CompositionError(f"hotspot #{idx} action: {msg}")
    return f"hotspot ({' '.join(rect)}) action {action.strip()}"
