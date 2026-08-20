"""Tier 2 — guarded write primitives.

Each tool mutates exactly one creator-visible thing. Inputs are structured;
the tool builds the .rpy text itself rather than accepting raw fragments.
Every tool routes through `project.writer.apply_write` so guardrails (indent
normalization, label-uniqueness check, .rpyc cleanup, atomic write, diff
generation, index refresh) are enforced uniformly.

Responses always include a unified diff. Harness UIs (hermes-agent,
Claude Code) render this for per-change approval.
"""

from __future__ import annotations

import re
from typing import Any

import mcp.types as types

from ..config import ServerConfig
from ..guardrails.dialogue import escape_dialogue, reject_multiline
from ..guardrails.reserved import reject_reserved_identifier
from ..project.canvas import CanvasError, set_positions
from ..project.diagnostics import DiagnosticsError, set_ignored
from ..project.label_tree import iter_statements, parse_label_from_disk
from ..project.media import compliance_warnings_for_alias
from ..project.scanner import ProjectIndex
from ..project.writer import WriteRejected, WriteResult, apply_write
from ._shared import (
    BODY_INDENT,
    append_block,
    err,
    find_default_insertion,
    find_single_label,
    find_top_level_decl_insertion,
    insert_into_label_body,
    label_terminator_line,
    num_str,
    ok,
    quote,
    splice_line,
    write_response,
)
from .registry import ToolDef, ToolRegistry

DEFAULT_SCRIPT = "game/script.rpy"


def register(registry: ToolRegistry, config: ServerConfig, index: ProjectIndex) -> None:
    registry.add(_add_label(config, index))
    registry.add(_add_say(config, index))
    registry.add(_add_jump(config, index))
    registry.add(_add_call(config, index))
    registry.add(_add_menu(config, index))
    registry.add(_update_menu_choice(config, index))
    registry.add(_add_condition_branch(config, index))
    registry.add(_set_variable_default(config, index))
    registry.add(_rename_label(config, index))
    registry.add(_add_audio_play(config, index))
    registry.add(_add_image_alias(config, index))
    registry.add(_add_character(config, index))
    registry.add(_update_character(config, index))
    registry.add(_add_layered_image(config, index))
    registry.add(_add_transform(config, index))
    registry.add(_add_screen(config, index))
    registry.add(_update_options_field(config, index))
    registry.add(_set_canvas_positions(config))
    registry.add(_set_ignored_diagnostics(config))
    registry.add(_add_menu_branch(config, index))
    registry.add(_redirect_jump(config, index))
    registry.add(_delete_label(config, index))
    registry.add(_add_pause(config, index))
    registry.add(_add_setvar(config, index))
    registry.add(_add_show(config, index))
    registry.add(_add_with_effect(config, index))
    registry.add(_add_flash(config, index))


# ---------- set_ignored_diagnostics ---------------------------------------------


def _set_ignored_diagnostics(config: ServerConfig) -> ToolDef:
    """Persist suppression entries for the diagnostic tools.

    The ignored-diagnostics sidecar is GUI/agent metadata, not Ren'Py
    syntax — same exemption from `apply_write` as the canvas sidecar
    (DESIGN.md §3 / `project/diagnostics.py`). Atomic write + path
    containment still apply.
    """
    schema = {
        "type": "object",
        "properties": {
            "entries": {
                "type": "array",
                "description": (
                    "List of suppression patterns. Each entry must include "
                    "`rule` and may narrow with optional `file`, `line`, "
                    "`label` fields. A diagnostic is suppressed when every "
                    "field in the entry equals the diagnostic's value."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "rule": {"type": "string"},
                        "file": {"type": "string"},
                        "line": {"type": "integer"},
                        "label": {"type": "string"},
                    },
                    "required": ["rule"],
                    "additionalProperties": False,
                },
            },
            "replace": {
                "type": "boolean",
                "default": False,
                "description": (
                    "If true, replace the entire saved list with `entries`. "
                    "If false (default), append `entries` to the existing "
                    "list, dropping exact-equal duplicates."
                ),
            },
        },
        "required": ["entries"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        entries = arguments["entries"]
        replace = bool(arguments.get("replace", False))
        if not isinstance(entries, list):
            return err("entries must be a list of suppression patterns")
        try:
            new_state = set_ignored(config, entries, replace=replace)
        except DiagnosticsError as exc:
            return err(str(exc))
        return ok(
            {
                "summary": (
                    f"saved {len(entries)} entry(ies); "
                    f"sidecar now holds {len(new_state.ignored)} suppression(s)"
                ),
                "version": new_state.version,
                "ignored": new_state.ignored,
                "count": len(new_state.ignored),
            }
        )

    return ToolDef(
        name="set_ignored_diagnostics",
        description=(
            "Persist suppression entries for the `find_*` diagnostic tools "
            "into `.renpy-mcp/ignored_diagnostics.json`. Default behaviour "
            "appends to the existing list (de-duplicating exact matches); "
            "pass `replace: true` to overwrite. Each entry is "
            "`{rule, file?, line?, label?}`. The sidecar is editor metadata "
            "(not Ren'Py syntax) and so does NOT route through the "
            "`apply_write` pipeline — see DESIGN.md §3."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- set_canvas_positions ------------------------------------------------


def _set_canvas_positions(config: ServerConfig) -> ToolDef:
    """Persist Story Map positions for one or more labels.

    The canvas sidecar is GUI metadata, not Ren'Py syntax — Ren'Py never
    reads it and `ProjectIndex` does not index it. This is the second
    sanctioned exception to "every mutation goes through `apply_write`"
    alongside `new_project`. See `project.canvas` for the rationale.
    """
    schema = {
        "type": "object",
        "properties": {
            "positions": {
                "type": "object",
                "description": (
                    "Map of label name to `{x, y}` (numbers). Keys must be "
                    "label names; coordinates are in the GUI's world space. "
                    "Labels not present in the map are left untouched unless "
                    "`replace` is true."
                ),
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                    },
                    "required": ["x", "y"],
                    "additionalProperties": True,
                },
            },
            "replace": {
                "type": "boolean",
                "default": False,
                "description": (
                    "If true, replace the entire saved map with `positions`. "
                    "If false (default), merge `positions` over the existing "
                    "saved map."
                ),
            },
        },
        "required": ["positions"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        positions = arguments["positions"]
        replace = bool(arguments.get("replace", False))
        if not isinstance(positions, dict):
            return err("positions must be an object keyed by label name")
        try:
            new_state = set_positions(config, positions, replace=replace)
        except CanvasError as exc:
            return err(str(exc))
        return ok(
            {
                "summary": (
                    f"saved {len(positions)} position(s); "
                    f"sidecar now tracks {len(new_state.labels)} label(s)"
                ),
                "version": new_state.version,
                "labels": new_state.labels,
                "count": len(new_state.labels),
            }
        )

    return ToolDef(
        name="set_canvas_positions",
        description=(
            "Persist Story Map positions for one or more labels into the "
            "`.renpy-mcp/canvas.json` sidecar. Use after the GUI commits a "
            "drag. Default behaviour merges `positions` over the existing map "
            "so untouched labels keep their saved coordinates; pass "
            "`replace: true` to overwrite the entire map. The sidecar is GUI "
            "metadata (not Ren'Py syntax) and so does NOT route through the "
            "standard `apply_write` pipeline — no diff, no `.rpyc` cleanup, "
            "no index refresh. Atomic write + path containment still apply."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- add_label -----------------------------------------------------------


def _add_label(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "New label name. Must be a valid Python identifier."},
            "body": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of body lines (without indentation; the tool "
                    "indents at 4 spaces). Defaults to `[\"pass\"]` so the label is well-formed."
                ),
            },
            "file": {
                "type": "string",
                "description": "Target .rpy file relative to project root. Defaults to `game/script.rpy`.",
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        name: str = arguments["name"]
        body: list[str] = arguments.get("body") or []
        rel_file: str = arguments.get("file") or DEFAULT_SCRIPT

        if not name.isidentifier():
            return err(f"`{name}` is not a valid Python identifier")
        if msg := reject_reserved_identifier(name):
            return err(msg)

        snap = index.snapshot()
        if any(l.name == name for l in snap.labels):
            existing = next(l for l in snap.labels if l.name == name)
            return err(
                f"label `{name}` already exists",
                existing={"file": existing.range.file, "line": existing.range.start_line},
            )

        body_lines = [f"{BODY_INDENT}{ln}" for ln in (body or ["pass"])]
        block_lines = [f"label {name}:", *body_lines]
        target = config.project_root / rel_file
        original = target.read_text(encoding="utf-8") if target.is_file() else ""
        new_text = append_block(original, block_lines)
        return write_response(config, index, rel_file, new_text, summary=f"added label `{name}`")

    return ToolDef(
        name="add_label",
        description=(
            "Create a new top-level Ren'Py label. Provide the name and an "
            "optional list of body lines (the tool indents them at 4 spaces and "
            "emits `pass` if you give no body). Refuses if the name is already "
            "in use anywhere in the project, is a reserved keyword, or is not a "
            "valid Python identifier. Default target file is `game/script.rpy`."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- add_say -------------------------------------------------------------


def _add_say(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Existing label whose body the say-statement is appended to."},
            "character": {
                "type": "string",
                "description": (
                    "Character variable name (e.g. `e`, `m`). Omit for narration. "
                    "Validated against the project's defined Characters."
                ),
            },
            "text": {
                "type": "string",
                "description": (
                    "Dialogue text. The tool escapes Ren'Py text-tag and "
                    "substitution metacharacters (`{`, `}`, `[`, `]`) for you. "
                    "Set `raw: true` if you have already escaped them yourself."
                ),
            },
            "raw": {
                "type": "boolean",
                "default": False,
                "description": "Skip dialogue escaping. Use only when you know what you are doing.",
            },
        },
        "required": ["label", "text"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        label_name: str = arguments["label"]
        character: str | None = arguments.get("character")
        raw_text: str = arguments["text"]
        raw_flag: bool = bool(arguments.get("raw", False))

        if msg := reject_multiline(raw_text):
            return err(msg)

        snap = index.snapshot()
        label = find_single_label(snap.labels, label_name)
        if isinstance(label, str):
            return err(label)
        if character is not None and not any(c.var_name == character for c in snap.characters):
            return err(
                f"unknown character var: `{character}`",
                known=[c.var_name for c in snap.characters],
            )

        body_text = raw_text if raw_flag else escape_dialogue(raw_text)
        quoted = quote(body_text)
        say = f"{character} {quoted}" if character else quoted
        return insert_into_label_body(
            config, index, label, [say], summary=f"appended say-statement to `{label_name}`"
        )

    return ToolDef(
        name="add_say",
        description=(
            "Append a say-statement to the end of an existing label's body. "
            "Provide the target `label`, optional `character` (variable name), "
            "and the dialogue `text`. The tool double-escapes `{`, `}`, `[`, "
            "`]` for you (set `raw: true` to opt out) and validates the "
            "character variable against `list_characters`."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- add_jump / add_call -----------------------------------------------


def _add_jump(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    return _make_jumplike(config, index, keyword="jump")


def _add_call(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    return _make_jumplike(config, index, keyword="call")


def _make_jumplike(config: ServerConfig, index: ProjectIndex, *, keyword: str) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": f"Existing label whose body receives the {keyword}."},
            "target": {"type": "string", "description": "Label name to transfer control to."},
            "validate_target": {
                "type": "boolean",
                "default": True,
                "description": "Refuse the write when `target` does not yet exist. Disable for forward-references.",
            },
        },
        "required": ["label", "target"],
        "additionalProperties": False,
    }
    if keyword == "jump":
        schema["properties"]["replace_terminator"] = {
            "type": "boolean",
            "default": False,
            "description": (
                "If true, replace the label's existing trailing `jump`/`return` "
                "with the new jump. Default false so a stray double-jump fails loudly."
            ),
        }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        label_name: str = arguments["label"]
        target_name: str = arguments["target"]
        validate_target: bool = bool(arguments.get("validate_target", True))
        replace_terminator: bool = bool(arguments.get("replace_terminator", False))

        if not target_name.isidentifier():
            return err(f"`{target_name}` is not a valid label identifier")

        snap = index.snapshot()
        label = find_single_label(snap.labels, label_name)
        if isinstance(label, str):
            return err(label)

        if validate_target and not any(l.name == target_name for l in snap.labels):
            return err(
                f"{keyword} target `{target_name}` does not exist; pass `validate_target: false` to allow forward-references"
            )

        # `jump` is a terminator. Refuse to add a second one unless caller opts in.
        if keyword == "jump":
            rel = label.range.file
            file_lines = (config.project_root / rel).read_text(encoding="utf-8").splitlines()
            term_idx = label_terminator_line(label, file_lines)
            if term_idx is not None:
                if not replace_terminator:
                    return err(
                        f"label `{label_name}` already terminates with `{file_lines[term_idx].strip()}`; "
                        "pass `replace_terminator: true` to overwrite it",
                    )
                file_lines[term_idx] = f"{BODY_INDENT}jump {target_name}"
                text = (config.project_root / rel).read_text(encoding="utf-8")
                new_text = "\n".join(file_lines) + ("\n" if text.endswith("\n") else "")
                return write_response(
                    config, index, rel, new_text,
                    summary=f"replaced terminator of `{label_name}` with `jump {target_name}`",
                )

        return insert_into_label_body(
            config,
            index,
            label,
            [f"{keyword} {target_name}"],
            summary=f"added `{keyword} {target_name}` to `{label_name}`",
        )

    if keyword == "jump":
        description = (
            "Append a `jump <target>` statement to the end of an existing "
            "label's body. By default the target label must already exist; "
            "pass `validate_target: false` to permit a forward-reference. "
            "Refuses if the label already terminates with `jump`/`return` "
            "(common for scenes created via `create_scene` or the scaffold's "
            "`start` label) — pass `replace_terminator: true` to rewire."
        )
    else:
        description = (
            "Append a `call <target>` statement. Unlike `jump`, `call` pushes "
            "onto the call stack and control returns to the next statement after "
            "`target` returns. Target validation matches `add_jump`."
        )
    return ToolDef(name=f"add_{keyword}", description=description, input_schema=schema, handler=handler)


# ---------- add_menu ------------------------------------------------------------


def _add_menu(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Existing label whose body receives the menu."},
            "choices": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Choice prompt. Auto-escaped like `add_say` text."},
                        "body": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Lines executed when this choice is picked. Defaults to `[\"pass\"]`.",
                        },
                        "condition": {
                            "type": "string",
                            "description": "Optional Python expression gating the choice (`\"text\" if <condition>:`).",
                        },
                        "raw": {
                            "type": "boolean",
                            "default": False,
                            "description": "If true, skip metacharacter escaping on `text`.",
                        },
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["label", "choices"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        label_name: str = arguments["label"]
        choices: list[dict[str, Any]] = arguments["choices"]

        snap = index.snapshot()
        label = find_single_label(snap.labels, label_name)
        if isinstance(label, str):
            return err(label)

        menu_lines: list[str] = ["menu:"]
        for ch in choices:
            if msg := reject_multiline(ch["text"]):
                return err(f"choice text: {msg}")
            text = ch["text"] if ch.get("raw") else escape_dialogue(ch["text"])
            quoted = quote(text)
            condition = ch.get("condition")
            header = f"{quoted} if {condition}:" if condition else f"{quoted}:"
            menu_lines.append(f"{BODY_INDENT}{header}")
            for body_line in ch.get("body") or ["pass"]:
                menu_lines.append(f"{BODY_INDENT * 2}{body_line}")

        return insert_into_label_body(
            config,
            index,
            label,
            menu_lines,
            summary=f"added menu with {len(choices)} choice(s) to `{label_name}`",
        )

    return ToolDef(
        name="add_menu",
        description=(
            "Append a `menu:` block to the end of an existing label's body. "
            "Each choice is `{text, body, condition?, raw?}`: `text` is the "
            "prompt (auto-escaped), `body` is the lines run on selection "
            "(defaults to `pass`), `condition` is an optional Python expression "
            "that gates the choice. Indentation is generated automatically."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- update_menu_choice -------------------------------------------------


_CHOICE_LINE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<text>\".*?\"|'.*?')\s*(?:if\s+(?P<cond>.+?))?\s*:\s*$"
)


def _update_menu_choice(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "POSIX path to the .rpy file containing the choice (relative to project root).",
            },
            "line": {
                "type": "integer",
                "minimum": 1,
                "description": "1-based line number of the `\"text\":` choice line to rewrite.",
            },
            "text": {
                "type": "string",
                "description": "New prompt text. Auto-escaped like `add_say` text unless `raw` is true.",
            },
            "raw": {
                "type": "boolean",
                "default": False,
                "description": "If true, skip metacharacter escaping on `text`.",
            },
        },
        "required": ["file", "line", "text"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        rel: str = arguments["file"]
        line_no: int = int(arguments["line"])
        new_text: str = arguments["text"]
        raw: bool = bool(arguments.get("raw", False))

        if msg := reject_multiline(new_text):
            return err(f"text: {msg}")

        target_path = config.project_root / rel
        if not target_path.is_file():
            return err(f"file does not exist: {rel}")
        text = target_path.read_text(encoding="utf-8")
        file_lines = text.splitlines()
        if line_no < 1 or line_no > len(file_lines):
            return err(f"line {line_no} out of range for {rel}")

        original = file_lines[line_no - 1]
        m = _CHOICE_LINE_RE.match(original)
        if not m:
            return err(
                f"line {line_no} in {rel} is not a menu choice "
                f"(`\"text\":` or `\"text\" if cond:`): `{original.strip()}`"
            )

        escaped = new_text if raw else escape_dialogue(new_text)
        quoted = quote(escaped)
        cond = m.group("cond")
        new_line = f"{m.group('indent')}{quoted}"
        if cond:
            new_line += f" if {cond}"
        new_line += ":"

        if new_line == original:
            return ok(
                {
                    "summary": f"choice at {rel}:{line_no} already reads `{quoted}`",
                    "no_op": True,
                    "file": rel,
                    "diff": "",
                    "warnings": [],
                    "rpyc_cleaned": [],
                }
            )

        file_lines[line_no - 1] = new_line
        new_content = "\n".join(file_lines)
        if text.endswith("\n"):
            new_content += "\n"

        return write_response(
            config,
            index,
            rel,
            new_content,
            summary=f"updated choice at {rel}:{line_no}",
        )

    return ToolDef(
        name="update_menu_choice",
        description=(
            "Rewrite a single menu choice's prompt text at a specific (file, "
            "line). Preserves the choice's `if <condition>` clause and "
            "indentation. Use this when the Choice View edits a pill in place. "
            "Refuses if the line isn't a menu choice."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- add_condition_branch -----------------------------------------------


def _add_condition_branch(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Existing label whose body receives the if/elif/else block."},
            "branches": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "condition": {
                            "type": "string",
                            "description": (
                                "Python expression for the branch. Omit on the "
                                "last branch to make it the `else` clause."
                            ),
                        },
                        "body": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Lines run when the condition holds. Defaults to `[\"pass\"]`.",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
        "required": ["label", "branches"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        label_name: str = arguments["label"]
        branches: list[dict[str, Any]] = arguments["branches"]

        snap = index.snapshot()
        label = find_single_label(snap.labels, label_name)
        if isinstance(label, str):
            return err(label)

        body_lines: list[str] = []
        for idx, branch in enumerate(branches):
            condition = branch.get("condition")
            body = branch.get("body") or ["pass"]
            if idx == 0:
                if not condition:
                    return err("first branch must have a `condition`")
                body_lines.append(f"if {condition}:")
            elif condition is None:
                body_lines.append("else:")
            else:
                body_lines.append(f"elif {condition}:")
            body_lines.extend(f"{BODY_INDENT}{ln}" for ln in body)

        return insert_into_label_body(
            config, index, label, body_lines,
            summary=f"added if/elif/else block ({len(branches)} branch(es)) to `{label_name}`",
        )

    return ToolDef(
        name="add_condition_branch",
        description=(
            "Append an `if/elif/else` block to a label's body. Each branch is "
            "`{condition?, body}`. The first branch must have a `condition`; "
            "an omitted condition on the last branch becomes `else`."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- set_variable_default -----------------------------------------------


def _set_variable_default(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Variable name (Python identifier; dotted names not supported here)."},
            "value": {
                "type": "string",
                "description": (
                    "Raw Python literal/expression for the default value (e.g. `False`, `0`, `\"\"`, `[]`)."
                ),
            },
            "file": {
                "type": "string",
                "description": (
                    "Target .rpy file when creating a new declaration. Defaults to `game/script.rpy`. "
                    "Ignored when updating an existing declaration."
                ),
            },
        },
        "required": ["name", "value"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        name: str = arguments["name"]
        value: str = arguments["value"]
        rel_file: str = arguments.get("file") or DEFAULT_SCRIPT

        if not name.isidentifier():
            return err(f"`{name}` is not a valid Python identifier")
        if msg := reject_reserved_identifier(name):
            return err(msg)

        snap = index.snapshot()
        existing = next((v for v in snap.defaults if v.name == name), None)
        if existing is not None:
            target_file = existing.range.file
            target = config.project_root / target_file
            text = target.read_text(encoding="utf-8")
            lines = text.splitlines()
            lines[existing.range.start_line - 1] = f"default {name} = {value}"
            new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
            return write_response(
                config, index, target_file, new_text,
                summary=f"updated `default {name}` (was `{existing.raw_value}`)",
            )

        target = config.project_root / rel_file
        original = target.read_text(encoding="utf-8") if target.is_file() else ""
        insertion = find_default_insertion(original)
        new_text = splice_line(original, insertion, f"default {name} = {value}")
        return write_response(
            config, index, rel_file, new_text,
            summary=f"added `default {name} = {value}` to `{rel_file}`",
        )

    return ToolDef(
        name="set_variable_default",
        description=(
            "Add or update a `default name = value` declaration. If the variable "
            "already exists anywhere in the project, the tool rewrites its line "
            "in place (the `file` argument is ignored). If new, the declaration "
            "is inserted after the last existing `default`/`define` in `file` "
            "(default: `game/script.rpy`). Use this for branching flags and "
            "anything referenced by save/load — `default` participates in "
            "rollback, `define` does not."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- rename_label --------------------------------------------------------


_REF_PATTERNS = (
    (r"\blabel\s+{name}\b", "label"),
    (r"\bjump\s+{name}\b", "jump"),
    (r"\bcall\s+{name}\b", "call"),
    (r"""\bJump\(\s*["']{name}["']\s*\)""", "Jump"),
    (r"""\bCall\(\s*["']{name}["']\s*\)""", "Call"),
)


def _rename_label(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "old": {"type": "string", "description": "Existing label name."},
            "new": {"type": "string", "description": "New label name (must be a valid identifier)."},
        },
        "required": ["old", "new"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        old: str = arguments["old"]
        new: str = arguments["new"]

        if not new.isidentifier():
            return err(f"`{new}` is not a valid Python identifier")
        if msg := reject_reserved_identifier(new):
            return err(msg)

        snap = index.snapshot()
        if not any(l.name == old for l in snap.labels):
            return err(f"no such label: `{old}`")
        if any(l.name == new for l in snap.labels):
            return err(f"label `{new}` already exists")

        compiled = [
            (re.compile(pat.replace("{name}", re.escape(old))), kind) for pat, kind in _REF_PATTERNS
        ]
        replacements = {
            "label": f"label {new}",
            "jump": f"jump {new}",
            "call": f"call {new}",
            "Jump": f'Jump("{new}")',
            "Call": f'Call("{new}")',
        }

        diffs: list[dict[str, Any]] = []
        warnings: list[str] = []
        rpyc_cleaned: list[str] = []
        files_changed: list[str] = []

        for rel in snap.files:
            target = config.project_root / rel
            text = target.read_text(encoding="utf-8")
            new_text = text
            for pat, kind in compiled:
                new_text = pat.sub(replacements[kind], new_text)
            if new_text == text:
                continue
            try:
                result = apply_write(config, index, rel, new_text)
            except WriteRejected as exc:
                return err(f"rename rejected while rewriting `{rel}`: {exc}")
            if result.no_op:
                continue
            files_changed.append(rel)
            diffs.append({"file": rel, "diff": result.diff})
            warnings.extend(result.warnings)
            rpyc_cleaned.extend(result.rpyc_cleaned)

        if not files_changed:
            return err(f"renamed `{old}` -> `{new}` but no references were found; nothing was written")

        return ok(
            {
                "summary": f"renamed label `{old}` -> `{new}` across {len(files_changed)} file(s)",
                "files_changed": files_changed,
                "diffs": diffs,
                "warnings": warnings,
                "rpyc_cleaned": rpyc_cleaned,
            }
        )

    return ToolDef(
        name="rename_label",
        description=(
            "Rename a label everywhere it appears: the `label name:` "
            "declaration plus every `jump name`, `call name`, `Jump(\"name\")`, "
            "and `Call(\"name\")` reference across all .rpy files in the "
            "project. Refuses if the new name already exists or is a reserved "
            "keyword. Returns one diff per modified file."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- add_audio_play ------------------------------------------------------


def _add_audio_play(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Existing label whose body receives the play statement."},
            "channel": {"type": "string", "description": "Audio channel: `music`, `sound`, `voice`, `audio`, or any custom channel."},
            "asset": {"type": "string", "description": "Asset path relative to `game/` (e.g. `audio/spring_theme.ogg`)."},
            "loop": {"type": "boolean", "default": False, "description": "Add the `loop` clause."},
            "fadein": {"type": "number", "minimum": 0, "description": "Optional `fadein <seconds>` clause."},
            "fadeout": {"type": "number", "minimum": 0, "description": "Optional `fadeout <seconds>` clause."},
            "validate_asset": {
                "type": "boolean",
                "default": True,
                "description": "Refuse the write if the asset file does not exist on disk.",
            },
        },
        "required": ["label", "channel", "asset"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        label_name: str = arguments["label"]
        channel: str = arguments["channel"]
        asset: str = arguments["asset"]
        loop: bool = bool(arguments.get("loop", False))
        fadein = arguments.get("fadein")
        fadeout = arguments.get("fadeout")
        validate_asset: bool = bool(arguments.get("validate_asset", True))

        if not channel.isidentifier():
            return err(f"`{channel}` is not a valid channel identifier")

        snap = index.snapshot()
        label = find_single_label(snap.labels, label_name)
        if isinstance(label, str):
            return err(label)

        if validate_asset and not (config.game_dir / asset).is_file():
            return err(
                f"asset file does not exist: `game/{asset}`; pass `validate_asset: false` to allow placeholder paths"
            )

        clauses = [f'play {channel} "{asset}"']
        if fadein is not None:
            clauses.append(f"fadein {num_str(fadein)}")
        if fadeout is not None:
            clauses.append(f"fadeout {num_str(fadeout)}")
        if loop:
            clauses.append("loop")
        return insert_into_label_body(
            config, index, label, [" ".join(clauses)],
            summary=f"added `play {channel}` of `{asset}` to `{label_name}`",
        )

    return ToolDef(
        name="add_audio_play",
        description=(
            "Append a `play <channel> \"<asset>\"` statement to the end of an "
            "existing label's body. Optional `loop`, `fadein <seconds>`, "
            "`fadeout <seconds>` clauses are emitted in canonical order. The "
            "asset must exist under `game/` unless `validate_asset: false`."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- add_image_alias -----------------------------------------------------


_IMAGE_NAME_RE = re.compile(r"^[A-Za-z_]\w*( [A-Za-z_]\w*)*$")


def _add_image_alias(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Image name as Ren'Py sees it: one or more space-separated "
                    "identifiers (e.g. `bg park`, `eileen happy smile`). The "
                    "first token is the tag; the rest are attributes."
                ),
            },
            "asset": {"type": "string", "description": "Asset path relative to `game/` (e.g. `images/park.png`)."},
            "file": {"type": "string", "description": "Target .rpy file. Defaults to `game/script.rpy`."},
            "validate_asset": {
                "type": "boolean",
                "default": True,
                "description": "Refuse the write if the asset file does not exist on disk.",
            },
            "role": {
                "type": "string",
                "enum": ["background", "sprite", "cg"],
                "description": (
                    "Optional override for MEDIA.md compliance checks. By "
                    "default the role is inferred from the image name: tag "
                    "`bg` -> background, `cg` -> CG, anything else -> sprite. "
                    "Pass this explicitly when the inference is wrong "
                    "(e.g. `room_overlay` should be `background`)."
                ),
            },
            "skip_media_check": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Skip MEDIA.md dimension/alpha checks. Useful for assets "
                    "that intentionally deviate (UI overlays, intro splashes). "
                    "Warnings are non-blocking; this flag only suppresses them."
                ),
            },
        },
        "required": ["name", "asset"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        name: str = arguments["name"]
        asset: str = arguments["asset"]
        rel_file: str = arguments.get("file") or DEFAULT_SCRIPT
        validate_asset: bool = bool(arguments.get("validate_asset", True))
        role: str | None = arguments.get("role")
        skip_media_check: bool = bool(arguments.get("skip_media_check", False))

        if not _IMAGE_NAME_RE.match(name):
            return err(f"`{name}` is not a valid image name (must be space-separated identifiers)")
        if validate_asset and not (config.game_dir / asset).is_file():
            return err(
                f"asset file does not exist: `game/{asset}`; pass `validate_asset: false` to allow placeholder paths"
            )

        # Compute MEDIA.md compliance warnings BEFORE writing so we can
        # merge them into the response. Non-blocking by design — agents
        # shouldn't be forced to regenerate art mid-pipeline, but they
        # should know the asset will look wrong at runtime.
        media_warnings: list[str] = []
        if not skip_media_check and (config.game_dir / asset).is_file():
            media_warnings = compliance_warnings_for_alias(
                image_name=name,
                asset_rel=asset,
                project_root=config.project_root,
                role=role,
            )

        new_line = f'image {name} = "{asset}"'
        target = config.project_root / rel_file
        original = target.read_text(encoding="utf-8") if target.is_file() else ""
        insertion = find_top_level_decl_insertion(original)
        new_text = splice_line(original, insertion, new_line)
        response = write_response(
            config, index, rel_file, new_text, summary=f"added `image {name}` -> `{asset}`"
        )
        if not media_warnings:
            return response
        # Re-decode the JSON payload to fold media warnings in alongside
        # the writer's own warnings (tab normalization, etc).
        import json as _json

        payload = _json.loads(response[0].text)
        existing_warnings = list(payload.get("warnings") or [])
        payload["warnings"] = existing_warnings + media_warnings
        payload["media_warnings"] = media_warnings
        return [types.TextContent(type="text", text=_json.dumps(payload, indent=2, ensure_ascii=False))]

    return ToolDef(
        name="add_image_alias",
        description=(
            "Add an `image <name> = \"<asset>\"` declaration. The image name "
            "follows Ren'Py tag/attribute conventions (space-separated "
            "identifiers). Inserted near other top-level declarations in the "
            "target file. Asset must exist under `game/` unless "
            "`validate_asset: false`. The asset is also probed against "
            "MEDIA.md's invariants — wrong dimensions for a background, "
            "missing alpha on a sprite, etc — and any deviations come back "
            "in `media_warnings` (non-blocking; the write still lands). "
            "Pass `role` to override inference, `skip_media_check: true` to "
            "silence the check entirely."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- add_character / update_character -----------------------------------


def _add_character(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "var": {"type": "string", "description": "Variable name the Character is bound to (used as say-tag in dialogue)."},
            "display_name": {"type": "string", "description": "On-screen name shown above dialogue. Auto-escaped."},
            "color": {"type": "string", "description": "Optional name color (e.g. `#0099cc`). Wrapped in quotes for you."},
            "image_tag": {
                "type": "string",
                "description": (
                    "Optional image tag (single identifier) to enable "
                    "attribute-say syntax (`e happy \"...\"` -> show `e happy`)."
                ),
            },
            "extra_kwargs": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": (
                    "Optional extra keyword arguments. Values are emitted "
                    "verbatim — quote strings and pass valid Python expressions."
                ),
            },
            "file": {"type": "string", "description": "Target .rpy file. Defaults to `game/script.rpy`."},
        },
        "required": ["var", "display_name"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        var: str = arguments["var"]
        display_name: str = arguments["display_name"]
        color: str | None = arguments.get("color")
        image_tag: str | None = arguments.get("image_tag")
        extras: dict[str, str] = arguments.get("extra_kwargs") or {}
        rel_file: str = arguments.get("file") or DEFAULT_SCRIPT

        if not var.isidentifier():
            return err(f"`{var}` is not a valid Python identifier")
        if msg := reject_reserved_identifier(var):
            return err(msg)
        if image_tag is not None and not image_tag.isidentifier():
            return err(f"image tag `{image_tag}` must be a single identifier")
        if msg := reject_multiline(display_name):
            return err(f"display_name: {msg}")

        snap = index.snapshot()
        if any(c.var_name == var for c in snap.characters):
            return err(f"character `{var}` already exists")

        kwargs: list[str] = []
        if color is not None:
            kwargs.append(f'color="{color}"')
        if image_tag is not None:
            kwargs.append(f'image="{image_tag}"')
        for key, value in extras.items():
            if not key.isidentifier():
                return err(f"`{key}` is not a valid keyword argument name")
            kwargs.append(f"{key}={value}")
        kwargs_str = (", " + ", ".join(kwargs)) if kwargs else ""
        line = f'define {var} = Character("{escape_dialogue(display_name)}"{kwargs_str})'

        target = config.project_root / rel_file
        original = target.read_text(encoding="utf-8") if target.is_file() else ""
        insertion = find_top_level_decl_insertion(original)
        new_text = splice_line(original, insertion, line)
        return write_response(config, index, rel_file, new_text, summary=f"defined character `{var}`")

    return ToolDef(
        name="add_character",
        description=(
            "Define a new Character: `define <var> = Character(\"<display>\", "
            "color=..., image=..., ...)`. Refuses if the variable name is taken "
            "or reserved. Pass extra Character kwargs through `extra_kwargs` "
            "(values emitted verbatim — quote strings yourself)."
        ),
        input_schema=schema,
        handler=handler,
    )


_CHARACTER_DISPLAY_QUOTED_RE = re.compile(r"""("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""")
_CHARACTER_COLOR_RE = re.compile(r"""color\s*=\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""")


def _update_character(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "var": {"type": "string", "description": "Variable name of the Character to update."},
            "display_name": {"type": "string", "description": "New display name. Auto-escaped."},
            "color": {"type": "string", "description": "New name color (e.g. `#ff8800`)."},
        },
        "required": ["var"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        var: str = arguments["var"]
        new_display = arguments.get("display_name")
        new_color = arguments.get("color")
        if new_display is None and new_color is None:
            return err("provide at least one of `display_name` or `color`")
        if new_display is not None and (msg := reject_multiline(new_display)):
            return err(f"display_name: {msg}")

        snap = index.snapshot()
        match = next((c for c in snap.characters if c.var_name == var), None)
        if match is None:
            return err(f"no character named `{var}`")

        rel = match.range.file
        target = config.project_root / rel
        text = target.read_text(encoding="utf-8")
        lines = text.splitlines()
        idx = match.range.start_line - 1
        line = lines[idx]

        if new_display is not None:
            new_quoted = f'"{escape_dialogue(new_display)}"'
            line, count = _CHARACTER_DISPLAY_QUOTED_RE.subn(new_quoted, line, count=1)
            if count == 0:
                return err(
                    f"could not locate the display-name string in line {match.range.start_line}; "
                    "use Tier 4 `apply_unified_diff` for non-trivial Character edits"
                )
        if new_color is not None:
            replacement = f'color="{new_color}"'
            new_line, count = _CHARACTER_COLOR_RE.subn(replacement, line, count=1)
            if count == 0:
                if ")" not in line:
                    return err(f"line {match.range.start_line} has no closing `)`; cannot inject color")
                close_idx = line.rfind(")")
                inside = line[:close_idx].rstrip()
                sep = ", " if not inside.endswith("(") else ""
                line = f"{inside}{sep}{replacement})"
            else:
                line = new_line

        lines[idx] = line
        new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
        return write_response(config, index, rel, new_text, summary=f"updated character `{var}`")

    return ToolDef(
        name="update_character",
        description=(
            "Modify an existing Character's display name and/or color in place. "
            "Other Character kwargs are preserved verbatim. Provide at least "
            "one of `display_name` or `color`. For deeper edits use Tier 4 "
            "`apply_unified_diff`."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- add_layered_image ---------------------------------------------------


def _add_layered_image(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Tag name for the layered image (single identifier)."},
            "groups": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "attributes": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "asset": {"type": "string"},
                                },
                                "required": ["name", "asset"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["name", "attributes"],
                    "additionalProperties": False,
                },
            },
            "file": {"type": "string", "description": "Target .rpy file. Defaults to `game/script.rpy`."},
        },
        "required": ["name", "groups"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        name: str = arguments["name"]
        groups: list[dict[str, Any]] = arguments["groups"]
        rel_file: str = arguments.get("file") or DEFAULT_SCRIPT

        if not name.isidentifier():
            return err(f"`{name}` must be a single identifier")

        snap = index.snapshot()
        if any(li.name == name for li in snap.layered_images):
            return err(f"layered image `{name}` already exists")

        block_lines: list[str] = [f"layeredimage {name}:"]
        for grp in groups:
            grp_name = grp["name"]
            if not grp_name.isidentifier():
                return err(f"group name `{grp_name}` must be an identifier")
            block_lines.append(f"{BODY_INDENT}group {grp_name}:")
            for attr in grp["attributes"]:
                attr_name = attr["name"]
                if not attr_name.isidentifier():
                    return err(f"attribute name `{attr_name}` must be an identifier")
                block_lines.append(f'{BODY_INDENT * 2}attribute {attr_name} "{attr["asset"]}"')

        target = config.project_root / rel_file
        original = target.read_text(encoding="utf-8") if target.is_file() else ""
        new_text = append_block(original, block_lines)
        return write_response(config, index, rel_file, new_text, summary=f"added layeredimage `{name}`")

    return ToolDef(
        name="add_layered_image",
        description=(
            "Add a `layeredimage <name>:` block with one or more groups, each "
            "containing inline `attribute <name> \"<asset>\"` lines. Use for "
            "composable character sprites (body/expression/clothing layers). "
            "For block-form attributes or `if`/`always` clauses, use Tier 4."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- add_transform / add_screen ------------------------------------------


def _add_transform(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    return _make_block_decl(
        config,
        index,
        keyword="transform",
        header_suffix="():",
        default_file=DEFAULT_SCRIPT,
        default_body=["pass"],
        existing_check=lambda snap, name: any(t.name == name for t in snap.transforms),
        description=(
            "Add a `transform <name>():` block with ATL body. Body lines are "
            "indented at 4 spaces automatically. Refuses on name collision or "
            "reserved-keyword name."
        ),
    )


def _add_screen(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    return _make_block_decl(
        config,
        index,
        keyword="screen",
        header_suffix="():",
        default_file="game/screens.rpy",
        default_body=["null"],
        existing_check=lambda snap, name: any(s.name == name for s in snap.screens),
        description=(
            "Add a `screen <name>():` block. Body lines are indented at 4 "
            "spaces automatically. Default target file is `game/screens.rpy` "
            "(created if missing). Variables read inside a screen MUST be "
            "declared with `default`, not `define` — use `set_variable_default` "
            "for any flag the screen depends on."
        ),
    )


def _make_block_decl(
    config: ServerConfig,
    index: ProjectIndex,
    *,
    keyword: str,
    header_suffix: str,
    default_file: str,
    default_body: list[str],
    existing_check,
    description: str,
) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": f"{keyword.capitalize()} name (Python identifier)."},
            "body": {
                "type": "array",
                "items": {"type": "string"},
                "description": f"Body lines without indentation. Defaults to {default_body!r}.",
            },
            "file": {"type": "string", "description": f"Target .rpy file. Defaults to `{default_file}`."},
        },
        "required": ["name"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        name: str = arguments["name"]
        body: list[str] = arguments.get("body") or list(default_body)
        rel_file: str = arguments.get("file") or default_file

        if not name.isidentifier():
            return err(f"`{name}` must be a Python identifier")
        if msg := reject_reserved_identifier(name):
            return err(msg)
        if existing_check(index.snapshot(), name):
            return err(f"{keyword} `{name}` already exists")

        block_lines = [f"{keyword} {name}{header_suffix}", *(f"{BODY_INDENT}{ln}" for ln in body)]
        target = config.project_root / rel_file
        original = target.read_text(encoding="utf-8") if target.is_file() else ""
        new_text = append_block(original, block_lines)
        return write_response(
            config, index, rel_file, new_text, summary=f"added {keyword} `{name}`"
        )

    return ToolDef(
        name=f"add_{keyword}",
        description=description,
        input_schema=schema,
        handler=handler,
    )


# ---------- update_options_field -----------------------------------------------


def _update_options_field(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "field": {
                "type": "string",
                "description": (
                    "Dotted field name as it appears after `define`, e.g. "
                    "`config.name`, `config.version`, `build.name`."
                ),
            },
            "value": {
                "type": "string",
                "description": "Raw Python literal (quote strings yourself: `\"My Game\"`).",
            },
            "file": {"type": "string", "description": "Target .rpy file. Defaults to `game/options.rpy`."},
        },
        "required": ["field", "value"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        field: str = arguments["field"]
        value: str = arguments["value"]
        rel_file: str = arguments.get("file") or "game/options.rpy"

        if not all(part.isidentifier() for part in field.split(".")):
            return err(f"`{field}` must be a dotted identifier")

        snap = index.snapshot()
        existing = next((d for d in snap.defines if d.name == field), None)
        if existing is not None:
            target_file = existing.range.file
            target = config.project_root / target_file
            text = target.read_text(encoding="utf-8")
            lines = text.splitlines()
            lines[existing.range.start_line - 1] = f"define {field} = {value}"
            new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
            return write_response(
                config, index, target_file, new_text,
                summary=f"updated `define {field}` (was `{existing.raw_value}`)",
            )

        target = config.project_root / rel_file
        original = target.read_text(encoding="utf-8") if target.is_file() else ""
        insertion = find_default_insertion(original)
        new_text = splice_line(original, insertion, f"define {field} = {value}")
        return write_response(
            config, index, rel_file, new_text,
            summary=f"added `define {field} = {value}` to `{rel_file}`",
        )

    return ToolDef(
        name="update_options_field",
        description=(
            "Set a `define <field> = <value>` line — typically in "
            "`game/options.rpy` (project title, version, build name, "
            "config flags). Updates the existing declaration in place when "
            "found; otherwise inserts in the target file. Pass `value` exactly "
            "as it should appear after the `=` (quote strings yourself)."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- add_menu_branch ----------------------------------------------------


def _add_menu_branch(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "label": {
                "type": "string",
                "description": "Label whose first top-level `menu:` block receives the new branch.",
            },
            "text": {
                "type": "string",
                "description": "Choice prompt. Auto-escaped like `add_say` text unless `raw` is true.",
            },
            "body": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Lines executed when this branch is selected. Defaults to `[\"pass\"]`. "
                    "Indentation is generated automatically."
                ),
            },
            "condition": {
                "type": "string",
                "description": "Optional Python expression gating the choice (`\"text\" if <condition>:`).",
            },
            "raw": {
                "type": "boolean",
                "default": False,
                "description": "If true, skip metacharacter escaping on `text`.",
            },
        },
        "required": ["label", "text"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        label_name: str = arguments["label"]
        text: str = arguments["text"]
        body: list[str] = arguments.get("body") or ["pass"]
        condition: str | None = arguments.get("condition")
        raw: bool = bool(arguments.get("raw", False))

        if msg := reject_multiline(text):
            return err(f"choice text: {msg}")

        snap = index.snapshot()
        label = find_single_label(snap.labels, label_name)
        if isinstance(label, str):
            return err(label)

        # Walk the label's body to find the FIRST top-level `menu:` block.
        # Nested menus (inside `if` branches or other menu choices) are
        # intentionally skipped — they don't render as Story Map nodes
        # and finer control there should use `apply_unified_diff`.
        tree = parse_label_from_disk(config, label)
        menu_node = next(
            (n for n in tree["body"] if n["kind"] == "menu"), None
        )
        if menu_node is None:
            return err(
                f"label `{label_name}` has no top-level `menu:` block; "
                "use `add_menu` to create one before adding branches"
            )

        rel = label.range.file
        text_content = (config.project_root / rel).read_text(encoding="utf-8")
        file_lines = text_content.splitlines()
        menu_idx = menu_node["line"] - 1  # 0-based
        menu_indent = len(file_lines[menu_idx]) - len(file_lines[menu_idx].lstrip())

        # Find the line after the menu block ends. The block ends when we
        # hit a non-blank, non-comment line whose indent is <= the menu's
        # indent, OR when we run off the end of the label.
        end_idx = label.range.end_line  # exclusive
        insert_at = end_idx
        for j in range(menu_idx + 1, end_idx):
            line = file_lines[j]
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= menu_indent:
                insert_at = j
                break

        # Build the new branch lines. Choice header sits one BODY_INDENT
        # deeper than the `menu:` keyword; choice body sits two deeper.
        choice_indent = " " * (menu_indent + 4)
        body_indent = " " * (menu_indent + 8)
        prompt = text if raw else escape_dialogue(text)
        quoted = quote(prompt)
        header = f"{quoted} if {condition}:" if condition else f"{quoted}:"
        new_lines = [f"{choice_indent}{header}"]
        for body_line in body:
            new_lines.append(f"{body_indent}{body_line}")

        spliced = file_lines[:insert_at] + new_lines + file_lines[insert_at:]
        new_text = "\n".join(spliced)
        if text_content.endswith("\n"):
            new_text += "\n"

        return write_response(
            config,
            index,
            rel,
            new_text,
            summary=f"appended choice `{text}` to menu in `{label_name}`",
        )

    return ToolDef(
        name="add_menu_branch",
        description=(
            "Append a new branch to the FIRST top-level `menu:` block of a "
            "label. Provide `text` (prompt, auto-escaped), optional `body` "
            "(defaults to `[\"pass\"]`), optional `condition` (Python "
            "expression gating the choice). Indentation is generated "
            "automatically. Refuses if the label has no top-level menu — "
            "call `add_menu` first to create one."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- redirect_jump ------------------------------------------------------


_JUMP_LINE_RE = re.compile(r"^(\s*)jump\s+(\w+)\s*$")


def _redirect_jump(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "POSIX path to the .rpy file containing the jump (relative to project root).",
            },
            "line": {
                "type": "integer",
                "minimum": 1,
                "description": "1-based line number of the `jump <target>` to rewrite.",
            },
            "new_target": {
                "type": "string",
                "description": "Replacement target label name. Must exist in the project.",
            },
        },
        "required": ["file", "line", "new_target"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        rel: str = arguments["file"]
        line_no: int = int(arguments["line"])
        new_target: str = arguments["new_target"]

        if not new_target.isidentifier():
            return err(f"new_target `{new_target}` is not a valid Python identifier")

        snap = index.snapshot()
        if not any(l.name == new_target for l in snap.labels):
            return err(f"no such label: {new_target}")

        target_path = config.project_root / rel
        if not target_path.is_file():
            return err(f"file does not exist: {rel}")
        text = target_path.read_text(encoding="utf-8")
        file_lines = text.splitlines()
        if line_no < 1 or line_no > len(file_lines):
            return err(f"line {line_no} out of range for {rel}")

        original = file_lines[line_no - 1]
        m = _JUMP_LINE_RE.match(original)
        if not m:
            return err(
                f"line {line_no} in {rel} is not a `jump <target>` statement: "
                f"`{original.strip()}`"
            )
        indent, old_target = m.group(1), m.group(2)
        if old_target == new_target:
            # Idempotent — return a no-op response with the same shape as
            # write_response so the caller doesn't have to special-case it.
            return ok(
                {
                    "summary": f"jump at {rel}:{line_no} already targets `{new_target}`",
                    "no_op": True,
                    "file": rel,
                    "diff": "",
                    "warnings": [],
                    "rpyc_cleaned": [],
                }
            )

        file_lines[line_no - 1] = f"{indent}jump {new_target}"
        new_text = "\n".join(file_lines)
        if text.endswith("\n"):
            new_text += "\n"

        return write_response(
            config,
            index,
            rel,
            new_text,
            summary=f"redirected jump at {rel}:{line_no} from `{old_target}` to `{new_target}`",
        )

    return ToolDef(
        name="redirect_jump",
        description=(
            "Rewrite a single `jump <target>` statement at a specific (file, "
            "line) to point at a new label. Use this when the Story Map drags "
            "an edge to a different node, or when refactoring without "
            "renaming. Refuses if the line isn't a `jump`, the new target "
            "isn't a valid identifier, or the new target doesn't exist as a "
            "label. No-op when the new target equals the old."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- delete_label -------------------------------------------------------


def _delete_label(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "label": {
                "type": "string",
                "description": "Name of the label to delete.",
            },
        },
        "required": ["label"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        label_name: str = arguments["label"]
        snap = index.snapshot()
        label = find_single_label(snap.labels, label_name)
        if isinstance(label, str):
            return err(label)

        # Find every incoming jump/call from OTHER labels. Any references
        # block the delete — agents must rewire or remove them first so the
        # project doesn't end up with dangling jumps.
        references: list[dict[str, Any]] = []
        for other in snap.labels:
            if other.name == label_name:
                continue
            other_tree = parse_label_from_disk(config, other)
            for stmt in iter_statements(other_tree["body"]):
                if stmt["kind"] in ("jump", "call") and stmt["target"] == label_name:
                    references.append(
                        {
                            "file": other.range.file,
                            "line": stmt["line"],
                            "label": other.name,
                            "kind": stmt["kind"],
                        }
                    )
        if references:
            return err(
                f"label `{label_name}` is still referenced from "
                f"{len(references)} site(s); rewire or remove them first",
                references=references,
            )

        # Splice out the label's lines (start_line..end_line, 1-based inclusive).
        rel = label.range.file
        text = (config.project_root / rel).read_text(encoding="utf-8")
        file_lines = text.splitlines()
        new_lines = (
            file_lines[: label.range.start_line - 1] + file_lines[label.range.end_line :]
        )
        new_text = "\n".join(new_lines)
        if text.endswith("\n") and not new_text.endswith("\n"):
            new_text += "\n"

        try:
            result = apply_write(config, index, rel, new_text)
        except WriteRejected as exc:
            return err(str(exc))

        warnings = list(result.warnings)
        if label_name == "start":
            warnings.append(
                "deleted `label start:` — the project will not run until a "
                "new start label is defined"
            )

        return ok(
            {
                "summary": f"deleted label `{label_name}` from `{rel}`",
                "no_op": result.no_op,
                "file": result.file,
                "diff": result.diff,
                "warnings": warnings,
                "rpyc_cleaned": result.rpyc_cleaned,
            }
        )

    return ToolDef(
        name="delete_label",
        description=(
            "Remove an entire label block (header + body) from its `.rpy` "
            "file. Refuses while the label is still reached by any "
            "`jump`/`call` from another label — the error response carries "
            "the list of references so the caller can rewire or remove them "
            "first. Soft-warns when deleting `label start:` because the "
            "project will not run until a new start is defined."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- event-stream tools (Phase 4) ---------------------------------------
#
# These tools all append a single line to a label's body via
# `insert_into_label_body`, which handles indent + terminator-respect.
# Each one owns one Ren'Py construct that the Scene Inspector renders as
# its own event card.


def _add_pause(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Label whose body receives the pause."},
            "duration": {
                "type": "number",
                "minimum": 0,
                "description": "Pause duration in seconds. 0 pauses for input.",
            },
        },
        "required": ["label", "duration"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        label_name: str = arguments["label"]
        duration = float(arguments["duration"])
        if duration < 0:
            return err("duration must be >= 0")
        snap = index.snapshot()
        label = find_single_label(snap.labels, label_name)
        if isinstance(label, str):
            return err(label)
        line = f"pause {num_str(duration)}"
        return insert_into_label_body(
            config,
            index,
            label,
            [line],
            summary=f"appended `{line}` to `{label_name}`",
        )

    return ToolDef(
        name="add_pause",
        description=(
            "Append a `pause <seconds>` statement to a label's body. Use to "
            "give a beat between dialogue lines or hold a moment after a "
            "transition. `duration: 0` waits for player input. The line is "
            "indented and inserted before any trailing `jump`/`return`."
        ),
        input_schema=schema,
        handler=handler,
    )


def _add_setvar(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Label whose body receives the assignment."},
            "name": {
                "type": "string",
                "description": "Target variable name (Python identifier; dotted attrs not supported).",
            },
            "value": {
                "description": (
                    "Value to assign. Strings are quoted and escaped; "
                    "bool/int/float/null are passed through verbatim."
                ),
            },
        },
        "required": ["label", "name", "value"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        label_name: str = arguments["label"]
        name: str = arguments["name"]
        value = arguments["value"]
        if not isinstance(name, str) or not name.isidentifier():
            return err(f"`{name}` is not a valid Python identifier")
        if msg := reject_reserved_identifier(name):
            return err(msg)
        try:
            rendered = _format_value_literal(value)
        except ValueError as exc:
            return err(str(exc))
        snap = index.snapshot()
        label = find_single_label(snap.labels, label_name)
        if isinstance(label, str):
            return err(label)
        line = f"$ {name} = {rendered}"
        return insert_into_label_body(
            config,
            index,
            label,
            [line],
            summary=f"appended `{line}` to `{label_name}`",
        )

    return ToolDef(
        name="add_setvar",
        description=(
            "Append `$ <name> = <value>` (an in-flow assignment) to a label's "
            "body. Distinct from `set_variable_default`, which writes a "
            "top-level `default <name> = <value>` declaration. Strings are "
            "auto-quoted; bool/int/float/null are passed through. Use for "
            "branching flags like `$ trust_mei += 1` after a dialogue line."
        ),
        input_schema=schema,
        handler=handler,
    )


def _add_show(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Label whose body receives the show."},
            "tag": {
                "type": "string",
                "description": "Image tag (typically a character name, e.g. `eileen`).",
            },
            "expression": {
                "type": "string",
                "description": "Optional expression / outfit (e.g. `happy`).",
            },
            "position": {
                "type": "string",
                "description": "Optional `at <position>` value (e.g. `left`, `center`).",
            },
            "transition": {
                "type": "string",
                "description": "Optional `with <transition>` value (e.g. `dissolve`).",
            },
        },
        "required": ["label", "tag"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        label_name: str = arguments["label"]
        tag: str = arguments["tag"]
        expression: str | None = arguments.get("expression")
        position: str | None = arguments.get("position")
        transition: str | None = arguments.get("transition")
        # Tag and expression must be Python-identifier-shaped to keep the
        # show statement parseable; positions/transitions are looser
        # (Ren'Py accepts callable expressions there).
        if not tag.isidentifier():
            return err(f"`{tag}` is not a valid image tag")
        if expression and not all(part.isidentifier() for part in expression.split()):
            return err(f"expression `{expression}` must be space-separated identifiers")
        snap = index.snapshot()
        label = find_single_label(snap.labels, label_name)
        if isinstance(label, str):
            return err(label)
        parts = ["show", tag]
        if expression:
            parts.append(expression)
        if position:
            parts.append(f"at {position}")
        if transition:
            parts.append(f"with {transition}")
        line = " ".join(parts)
        return insert_into_label_body(
            config,
            index,
            label,
            [line],
            summary=f"appended `{line}` to `{label_name}`",
        )

    return ToolDef(
        name="add_show",
        description=(
            "Append a `show <tag> [<expression>] [at <position>] [with "
            "<transition>]` statement to a label's body. Covers both the "
            "'move character' and 'change expression' actions in the Scene "
            "Inspector. Position and transition strings are passed through "
            "verbatim so callable transitions (`Dissolve(0.5)`) work."
        ),
        input_schema=schema,
        handler=handler,
    )


def _add_with_effect(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Label whose body receives the with-effect."},
            "expression": {
                "type": "string",
                "description": (
                    "Transition expression. Built-in atoms include `hpunch`, "
                    "`vpunch`, `dissolve`, `fade`; callable forms like "
                    "`Dissolve(0.5)` work too."
                ),
            },
        },
        "required": ["label", "expression"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        label_name: str = arguments["label"]
        expression: str = arguments["expression"]
        if not expression.strip():
            return err("expression must be non-empty")
        if msg := reject_multiline(expression):
            return err(f"expression: {msg}")
        snap = index.snapshot()
        label = find_single_label(snap.labels, label_name)
        if isinstance(label, str):
            return err(label)
        line = f"with {expression.strip()}"
        return insert_into_label_body(
            config,
            index,
            label,
            [line],
            summary=f"appended `{line}` to `{label_name}`",
        )

    return ToolDef(
        name="add_with_effect",
        description=(
            "Append a `with <expression>` line — a screen-shake, fade, or "
            "named transition. Pair with a preceding `show`/`scene`/`hide` "
            "for the transition to actually apply. Built-in atoms (`hpunch`, "
            "`dissolve`) and callable forms (`Dissolve(0.5)`) both work."
        ),
        input_schema=schema,
        handler=handler,
    )


_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _add_flash(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Label whose body receives the flash."},
            "color": {
                "type": "string",
                "description": "CSS-style hex color, e.g. `#ffffff` or `#fff`.",
            },
            "duration": {
                "type": "number",
                "default": 0.25,
                "minimum": 0,
                "description": "Total fade-out + fade-in time (seconds). Defaults to 0.25.",
            },
        },
        "required": ["label", "color"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        label_name: str = arguments["label"]
        color: str = arguments["color"]
        duration = float(arguments.get("duration", 0.25))
        if duration < 0:
            return err("duration must be >= 0")
        if not _HEX_COLOR_RE.match(color):
            return err(f"color `{color}` must be a hex string like `#ffffff` or `#fff`")
        snap = index.snapshot()
        label = find_single_label(snap.labels, label_name)
        if isinstance(label, str):
            return err(label)
        # Half the budget fades to color, half fades back. Hold time stays 0
        # so the flash reads as a momentary pulse, not a screen wash.
        half = num_str(duration / 2)
        line = f'with Fade({half}, 0.0, {half}, color="{color}")'
        return insert_into_label_body(
            config,
            index,
            label,
            [line],
            summary=f"appended {line} to `{label_name}`",
        )

    return ToolDef(
        name="add_flash",
        description=(
            "Append a momentary color flash via Ren'Py's `Fade` transition. "
            "Emits `with Fade(<dur/2>, 0.0, <dur/2>, color=\"<hex>\")` so the "
            "screen pulses to the color and back. Color must be a CSS hex "
            "(`#ffffff` or `#fff`)."
        ),
        input_schema=schema,
        handler=handler,
    )


def _format_value_literal(value: Any) -> str:
    """Render a JSON value as a Ren'Py expression (mirrors warp_to overrides)."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return num_str(float(value))
    if isinstance(value, str):
        return quote(value)
    raise ValueError(
        f"unsupported value type: {type(value).__name__}; "
        "must be string, int, float, bool, or null"
    )


__all__ = ["register", "WriteResult"]
