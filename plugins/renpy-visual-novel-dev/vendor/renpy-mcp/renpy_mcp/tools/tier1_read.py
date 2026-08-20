"""Tier 1 — read-only project introspection.

Tool descriptions matter more than tool code: the harness uses them to pick
which tool to call. Keep them imperative, concrete, and short. Every tool
returns a single TextContent containing pretty-printed JSON.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import mcp.types as types

from .. import sdk as renpy_sdk
from ..config import ServerConfig
from ..project.asset_refs import collect_missing_image_refs
from ..project.canvas import CanvasError, read_positions
from ..project.diagnostics import DiagnosticsError, filter_diagnostics, read_ignored
from ..project.label_tree import (
    infer_label_kind,
    iter_statements,
    parse_label_body,
    parse_label_from_disk,
)
from ..project.lint_parse import parse_lint_output
from ..project.media import MEDIA_INVARIANTS
from ..project import scaffold_status
from ..project import recent as recent_buffer
from ..project.translations import (
    coverage_summary,
    list_languages,
    parse_language,
)
from ..project.scanner import (
    CharacterInfo,
    LabelInfo,
    ProjectIndex,
    ProjectSnapshot,
    ScreenInfo,
    SourceRange,
)
from .registry import ToolDef, ToolRegistry

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
_AUDIO_EXTS = (".ogg", ".opus", ".mp3", ".wav")


def register(registry: ToolRegistry, config: ServerConfig, index: ProjectIndex) -> None:
    registry.add(_get_project_overview(config, index))
    registry.add(_list_labels(index))
    registry.add(_read_label(config, index))
    registry.add(_read_label_tree(config, index))
    registry.add(_list_characters(index))
    registry.add(_read_character(index))
    registry.add(_list_variables(index))
    registry.add(_list_screens(index))
    registry.add(_read_screen(config, index))
    registry.add(_list_images(config, index))
    registry.add(_list_audio(config, index))
    registry.add(_find_references(config))
    registry.add(_read_raw_file(config))
    registry.add(_get_lint_report(config))
    registry.add(_read_canvas_positions(config))
    registry.add(_find_invalid_jumps(config, index))
    registry.add(_find_undefined_characters(config, index))
    registry.add(_find_unused_characters(config, index))
    registry.add(_find_missing_assets(config, index))
    registry.add(_find_undefined_screens(config, index))
    registry.add(_find_unreachable_labels(config, index))
    registry.add(_read_ignored_diagnostics(config))
    registry.add(_refresh_project(index))
    registry.add(_get_choice_graph(config, index))
    registry.add(_get_translation_coverage(config))
    registry.add(_find_stale_translations(config))
    registry.add(_get_recent_edits())
    registry.add(_get_media_invariants())
    registry.add(_get_scaffold_status(config, index))


# ---------- get_project_overview ------------------------------------------------


def _get_project_overview(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.snapshot()
        overview = {
            "project_root": str(config.project_root),
            "files": list(snap.files),
            "counts": {
                "labels": len(snap.labels),
                "characters": len(snap.characters),
                "defaults": len(snap.defaults),
                "defines": len(snap.defines),
                "images": len(snap.images),
                "layered_images": len(snap.layered_images),
                "screens": len(snap.screens),
                "transforms": len(snap.transforms),
                "audio_plays": len(snap.audio_plays),
            },
            "labels": [l.name for l in snap.labels],
            "characters": [
                {"var": c.var_name, "display_name": c.display_name} for c in snap.characters
            ],
            "warnings": _overview_warnings(snap),
        }
        return _ok(overview)

    return ToolDef(
        name="get_project_overview",
        description=(
            "Return a high-level summary of the Ren'Py project: the list of .rpy "
            "files under game/, counts of every top-level construct (labels, "
            "characters, defaults, defines, images, screens, transforms, audio "
            "plays), the label name list, and the character roster. Call this "
            "first when starting work on a project; it is cheap and gives enough "
            "context to pick the right follow-up tool."
        ),
        input_schema=schema,
        handler=handler,
    )


def _overview_warnings(snap: ProjectSnapshot) -> list[str]:
    warnings: list[str] = []
    if snap.duplicate_labels:
        warnings.append(
            "duplicate label names (must be globally unique in Ren'Py): "
            + ", ".join(snap.duplicate_labels)
        )
    if not any(l.name == "start" for l in snap.labels):
        warnings.append("no `label start:` found — the project will not run as-is")
    return warnings


# ---------- list_labels / read_label --------------------------------------------


def _list_labels(index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": (
                    "Optional. Restrict results to labels declared in this .rpy file "
                    "(path relative to project root, e.g. 'game/script.rpy')."
                ),
            },
        },
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.snapshot()
        labels = snap.labels
        wanted = arguments.get("file")
        if wanted:
            labels = tuple(l for l in labels if l.range.file == wanted)
        return _ok({"labels": [_label_dict(l) for l in labels], "count": len(labels)})

    return ToolDef(
        name="list_labels",
        description=(
            "List every Ren'Py label in the project (or in one .rpy file when "
            "`file` is given). Each entry includes the label name, the file and "
            "line range it spans, and a heuristic say-statement count. Use this "
            "to discover scenes, find the right label to read, or audit "
            "branching coverage."
        ),
        input_schema=schema,
        handler=handler,
    )


def _read_label(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The label name as written after `label ` (no colon).",
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        name = arguments["name"]
        snap = index.snapshot()
        matches = [l for l in snap.labels if l.name == name]
        if not matches:
            return _err(f"no such label: {name}")
        if len(matches) > 1:
            return _err(
                f"label `{name}` is declared in multiple places — fix the duplicates first",
                locations=[_label_dict(l) for l in matches],
            )
        label = matches[0]
        return _ok(
            {
                "label": _label_dict(label),
                "source": _slice_source(config.project_root, label.range),
            }
        )

    return ToolDef(
        name="read_label",
        description=(
            "Return the full Ren'Py source of one label, including its header "
            "line, body, and source range (file + line numbers). Use this after "
            "`list_labels` when you need to see what a scene actually does — "
            "dialogue, jumps, menus, music, conditions."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- read_label_tree -----------------------------------------------------


def _read_label_tree(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The label name as written after `label ` (no colon).",
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        name = arguments["name"]
        snap = index.snapshot()
        matches = [l for l in snap.labels if l.name == name]
        if not matches:
            return _err(f"no such label: {name}")
        if len(matches) > 1:
            return _err(
                f"label `{name}` is declared in multiple places — fix the duplicates first",
                locations=[_label_dict(l) for l in matches],
            )
        label = matches[0]
        text = (config.project_root / label.range.file).read_text(encoding="utf-8", errors="replace")
        all_lines = text.splitlines()
        # Body lines are everything between header (start_line) and end_line
        # inclusive, dropping the header itself. start_line/end_line are 1-based.
        body_lines = all_lines[label.range.start_line : label.range.end_line]
        body_text = "\n".join(body_lines)
        body_start = label.range.start_line + 1  # 1-based file line of first body line
        tree = parse_label_body(body_text, body_start)
        kind = infer_label_kind(name, tree["body"], tree["shorthand"])
        return _ok(
            {
                "label": _label_dict(label),
                "kind": kind,
                "body": tree["body"],
                "shorthand": tree["shorthand"],
                "unparsed": tree["unparsed"],
            }
        )

    return ToolDef(
        name="read_label_tree",
        description=(
            "Return ONE label as a typed, ordered tree of recognized statements "
            "(say, scene, show, hide, play, stop, pause, jump, call, return, "
            "with, set, menu, if). Pairs with `read_label` (which returns raw "
            "source). The `body` array preserves source order so the GUI "
            "Inspector can render an editable stream; `shorthand` summarises "
            "background, music, outgoing jump/call targets, and whether the "
            "label ends in `return`. Lines the parser cannot interpret end up "
            "in `unparsed` so callers know what they shouldn't silently "
            "rewrite. The `kind` field (start|scene|choice|ending) is a "
            "structure-derived hint for the Story Map graph; it is not "
            "authoritative."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- list_characters / read_character ------------------------------------


def _list_characters(index: ProjectIndex) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.snapshot()
        return _ok(
            {
                "characters": [_character_dict(c) for c in snap.characters],
                "count": len(snap.characters),
            }
        )

    return ToolDef(
        name="list_characters",
        description=(
            "List every Character defined via `define x = Character(...)`. Each "
            "entry has the variable name (used as the say-tag in dialogue lines), "
            "the display name if quoted positionally, the raw constructor "
            "arguments, and the source location. Use this to learn the cast and "
            "the say-tag conventions before adding dialogue."
        ),
        input_schema=schema,
        handler=handler,
    )


def _read_character(index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "var": {
                "type": "string",
                "description": "The variable name (e.g. 'e', 'm') the Character is bound to.",
            },
        },
        "required": ["var"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        var = arguments["var"]
        snap = index.snapshot()
        matches = [c for c in snap.characters if c.var_name == var]
        if not matches:
            return _err(f"no character named `{var}`")
        return _ok({"character": _character_dict(matches[0])})

    return ToolDef(
        name="read_character",
        description=(
            "Return the full Character definition for one variable: display "
            "name, raw constructor arguments (color, image tag, callback, etc.), "
            "and source location. Use after `list_characters` when you need to "
            "see exactly how a character was configured."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- list_variables ------------------------------------------------------


def _list_variables(index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["default", "define", "all"],
                "default": "all",
                "description": (
                    "Which kind to return. `default` participates in save/load "
                    "and rollback; `define` is a constant the engine may inline. "
                    "Variables read inside a screen MUST be `default`, not `define`."
                ),
            },
        },
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        kind = arguments.get("kind", "all")
        snap = index.snapshot()
        result: list[dict[str, Any]] = []
        if kind in ("default", "all"):
            result.extend(_variable_dict(v) for v in snap.defaults)
        if kind in ("define", "all"):
            result.extend(_variable_dict(v) for v in snap.defines)
        return _ok({"variables": result, "count": len(result)})

    return ToolDef(
        name="list_variables",
        description=(
            "List `default` and/or `define` declarations in the project. Filter "
            "with `kind: default|define|all` (default: all). Use to discover "
            "branching flags, persistent state, GUI tokens, and config values."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- list_screens / read_screen ------------------------------------------


def _list_screens(index: ProjectIndex) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.snapshot()
        return _ok(
            {
                "screens": [_screen_dict(s) for s in snap.screens],
                "count": len(snap.screens),
            }
        )

    return ToolDef(
        name="list_screens",
        description=(
            "List every `screen name():` declaration. Returns name plus source "
            "location for each. Use this before adding HUD, menu, or overlay "
            "elements to see what already exists."
        ),
        input_schema=schema,
        handler=handler,
    )


def _read_screen(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "The screen name."},
        },
        "required": ["name"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        name = arguments["name"]
        snap = index.snapshot()
        matches = [s for s in snap.screens if s.name == name]
        if not matches:
            return _err(f"no such screen: {name}")
        screen = matches[0]
        return _ok(
            {
                "screen": _screen_dict(screen),
                "source": _slice_source(config.project_root, screen.range),
            }
        )

    return ToolDef(
        name="read_screen",
        description=(
            "Return the full Ren'Py source of one screen, including its header, "
            "body, and source range. Use after `list_screens` when you need to "
            "see what a custom screen actually displays."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- list_images ---------------------------------------------------------


def _list_images(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.snapshot()
        results: list[dict[str, Any]] = []

        # Explicit `image x = "..."` aliases.
        for img in snap.images:
            results.append(
                {
                    "name": img.name,
                    "kind": "alias",
                    "value": img.raw_value,
                    "file": img.range.file,
                    "line": img.range.start_line,
                }
            )

        # `layeredimage name:` declarations.
        for li in snap.layered_images:
            results.append(
                {
                    "name": li.name,
                    "kind": "layered",
                    "file": li.range.file,
                    "line": li.range.start_line,
                }
            )

        # Auto-named files in game/images/. Filename underscores become spaces;
        # the directory is not part of the name.
        images_dir = config.game_dir / "images"
        if images_dir.is_dir():
            for path in sorted(images_dir.rglob("*")):
                if path.suffix.lower() not in _IMAGE_EXTS:
                    continue
                auto_name = path.stem.replace("_", " ")
                results.append(
                    {
                        "name": auto_name,
                        "kind": "auto",
                        "asset_path": path.relative_to(config.project_root).as_posix(),
                    }
                )

        return _ok({"images": results, "count": len(results)})

    return ToolDef(
        name="list_images",
        description=(
            "List every image known to Ren'Py: explicit `image foo = ...` "
            "aliases, `layeredimage` declarations, and auto-named asset files in "
            "`game/images/` (filename underscores become spaces, e.g. "
            "`eileen_happy.png` -> image name `eileen happy`). Each entry has a "
            "`kind` (alias|layered|auto) so you can tell them apart."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- list_audio ----------------------------------------------------------


def _list_audio(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.snapshot()
        files: list[dict[str, Any]] = []
        audio_dir = config.game_dir / "audio"
        if audio_dir.is_dir():
            for path in sorted(audio_dir.rglob("*")):
                if path.suffix.lower() not in _AUDIO_EXTS:
                    continue
                files.append(
                    {
                        "asset_path": path.relative_to(config.project_root).as_posix(),
                        "size_bytes": path.stat().st_size,
                    }
                )

        plays = [
            {
                "channel": p.channel,
                "asset": p.asset,
                "file": p.range.file,
                "line": p.range.start_line,
            }
            for p in snap.audio_plays
        ]
        return _ok({"files": files, "plays": plays})

    return ToolDef(
        name="list_audio",
        description=(
            "List audio assets under `game/audio/` (.ogg/.opus/.mp3/.wav) and "
            "every `play <channel> \"asset\"` statement found in scripts. Use "
            "this to discover what music/SFX are available and where each is "
            "currently triggered."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- find_references -----------------------------------------------------


def _find_references(config: ServerConfig) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "needle": {
                "type": "string",
                "description": (
                    "The literal symbol to search for (label name, character "
                    "var, image name, asset path)."
                ),
            },
            "word_boundary": {
                "type": "boolean",
                "default": True,
                "description": (
                    "If true (default), match only when `needle` is bounded by "
                    "non-word characters. Disable for substring search."
                ),
            },
            "max_results": {
                "type": "integer",
                "default": 50,
                "minimum": 1,
                "maximum": 500,
            },
        },
        "required": ["needle"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        needle: str = arguments["needle"]
        if not needle:
            return _err("needle must be non-empty")
        word_boundary = arguments.get("word_boundary", True)
        max_results = int(arguments.get("max_results", 50))

        if word_boundary:
            pattern = re.compile(rf"\b{re.escape(needle)}\b")
        else:
            pattern = re.compile(re.escape(needle))

        matches: list[dict[str, Any]] = []
        for rpy in sorted(config.game_dir.rglob("*.rpy")):
            rel = rpy.relative_to(config.project_root).as_posix()
            text = rpy.read_text(encoding="utf-8", errors="replace")
            for idx, line in enumerate(text.splitlines()):
                if pattern.search(line):
                    matches.append({"file": rel, "line": idx + 1, "context": line.rstrip()})
                    if len(matches) >= max_results:
                        return _ok(
                            {
                                "matches": matches,
                                "count": len(matches),
                                "truncated": True,
                            }
                        )
        return _ok({"matches": matches, "count": len(matches), "truncated": False})

    return ToolDef(
        name="find_references",
        description=(
            "Search every .rpy file under `game/` for occurrences of a literal "
            "symbol (label name, character var, image name, asset path). Returns "
            "file/line/context for each match. Word-boundary by default so "
            "searching `e` does not match `eileen`. Cap with `max_results` "
            "(default 50, max 500)."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- read_raw_file -------------------------------------------------------


def _read_raw_file(config: ServerConfig) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "File path relative to project root (e.g. 'game/options.rpy'). "
                    "Must resolve inside the project; absolute paths are rejected."
                ),
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        rel = arguments["path"]
        try:
            target = (config.project_root / rel).resolve()
            target.relative_to(config.project_root.resolve())
        except (ValueError, OSError) as exc:
            return _err(f"path must resolve inside project_root: {exc}")
        if not target.is_file():
            return _err(f"file does not exist: {rel}")
        text = target.read_text(encoding="utf-8", errors="replace")
        return _ok(
            {
                "path": rel,
                "lines": text.count("\n") + (0 if text.endswith("\n") or not text else 1),
                "content": text,
            }
        )

    return ToolDef(
        name="read_raw_file",
        description=(
            "Read any file inside the project root, returning its full text. Use "
            "for files the typed read tools do not cover: `game/options.rpy`, "
            "`game/gui.rpy`, translations, custom Python modules. Path must be "
            "relative to project root and stay inside it."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- get_lint_report -----------------------------------------------------


def _get_lint_report(config: ServerConfig) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "include_raw": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Include the raw lint stdout/stderr alongside the parsed "
                    "findings. Default true — some agents prefer to see the "
                    "original text. Set false to shrink the response when "
                    "iterating fast."
                ),
            },
        },
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        include_raw: bool = bool(arguments.get("include_raw", True))
        try:
            result = await renpy_sdk.run_lint(config.sdk_root, config.project_root)
        except Exception as exc:
            return _err(f"failed to invoke renpy.sh lint: {exc}")

        parsed = parse_lint_output(result.stdout)
        # `clean` is the most actionable bit: agents can early-exit
        # their fix loop when this flips True. It's stricter than
        # `returncode == 0` because Ren'Py exits 0 even with warnings.
        summary = parsed["summary"] or {"errors": 0, "warnings": 0, "info": 0, "obsolete": 0}
        clean = summary.get("errors", 0) == 0 and summary.get("warnings", 0) == 0

        payload: dict[str, Any] = {
            "returncode": result.returncode,
            "clean": clean,
            "findings": parsed["findings"],
            "findings_count": len(parsed["findings"]),
            "advisories": parsed["advisories"],
            "summary": summary,
            "summary_line": parsed["summary_line"],
        }
        if include_raw:
            payload["stdout"] = result.stdout
            payload["stderr"] = result.stderr
            payload["statistics"] = parsed["statistics"]
        return _ok(payload)

    return ToolDef(
        name="get_lint_report",
        description=(
            "Run Ren'Py's built-in `lint` command and return both the parsed "
            "findings (`{rule, severity, file, line, message}` — same shape as "
            "the `find_*` diagnostics) and the raw stdout/stderr. The top-level "
            "`clean` field flips True when there are zero errors AND zero "
            "warnings — agents use it to early-exit a fix loop. Severity is "
            "inferred from message wording (lint itself does not tag findings). "
            "Slow (a couple of seconds for small projects); call after writes "
            "or when investigating runtime issues, not as a routine probe. Pass "
            "`include_raw: false` to skip the raw stdout/stderr."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- read_canvas_positions ----------------------------------------------


def _read_canvas_positions(config: ServerConfig) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        try:
            state = read_positions(config)
        except CanvasError as exc:
            return _err(str(exc))
        return _ok(
            {
                "version": state.version,
                "labels": state.labels,
                "count": len(state.labels),
            }
        )

    return ToolDef(
        name="read_canvas_positions",
        description=(
            "Return saved Story Map positions for every label, as authored in "
            "the GUI. Backed by `.renpy-mcp/canvas.json`. Returns an empty "
            "`labels` map when the sidecar does not yet exist. The sidecar is "
            "GUI metadata — it is not consumed by Ren'Py and is not required "
            "for any tool to function. Pair with `set_canvas_positions` "
            "(Tier 2) to persist drag changes."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- diagnostics (Phase 1) ----------------------------------------------
#
# Diagnostic tools share one response shape so the agent loop is uniform:
#
#   {
#     "rule": "<rule_name>",
#     "diagnostics": [
#       {"file", "line", "message", "severity", "rule", "label"?},
#       ...
#     ],
#     "count": <int>,                 # diagnostics returned (post-suppression)
#     "suppressed_count": <int>,      # diagnostics muted by the sidecar
#   }
#
# Severity is "error" | "warning" | "info". The agent's iteration loop is:
# write → re-snapshot → call diagnostics → self-correct. Every diagnostic
# is cheap and pure-read; none of these replace `get_lint_report`, which
# remains the authoritative call. Suppression comes from
# `.renpy-mcp/ignored_diagnostics.json` and is applied uniformly via
# `_diag_payload` so individual handlers stay focused on the rule logic.


def _diag_payload(
    config: ServerConfig,
    rule: str,
    diagnostics: list[dict[str, Any]],
) -> list[types.TextContent]:
    try:
        ignored = read_ignored(config).ignored
    except DiagnosticsError as exc:
        # Malformed sidecar shouldn't crash a diagnostic call; surface it as
        # a meta-warning so the agent can fix or wipe the sidecar, but still
        # return the unfiltered diagnostics so they're not invisible.
        return _ok(
            {
                "rule": rule,
                "diagnostics": diagnostics,
                "count": len(diagnostics),
                "suppressed_count": 0,
                "sidecar_warning": str(exc),
            }
        )
    kept, suppressed = filter_diagnostics(diagnostics, ignored)
    return _ok(
        {
            "rule": rule,
            "diagnostics": kept,
            "count": len(kept),
            "suppressed_count": suppressed,
        }
    )


def _walk_label_tree(config: ServerConfig, label: LabelInfo) -> dict[str, Any]:
    """Convenience alias matching the older private name. New code should
    call `parse_label_from_disk` directly."""
    return parse_label_from_disk(config, label)


def _find_invalid_jumps(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.snapshot()
        known = {l.name for l in snap.labels}
        diagnostics: list[dict[str, Any]] = []
        for label in snap.labels:
            tree = _walk_label_tree(config, label)
            for stmt in iter_statements(tree["body"]):
                if stmt["kind"] not in ("jump", "call"):
                    continue
                target = stmt["target"]
                if target in known:
                    continue
                diagnostics.append(
                    {
                        "rule": "invalid_jump",
                        "severity": "error",
                        "file": label.range.file,
                        "line": stmt["line"],
                        "label": label.name,
                        "message": f"`{stmt['kind']} {target}` — no label named `{target}` exists",
                    }
                )
        return _diag_payload(config, "invalid_jump", diagnostics)

    return ToolDef(
        name="find_invalid_jumps",
        description=(
            "Walk every label and flag every `jump` or `call` whose target "
            "label does not exist in the project. Cheap pure read, complementary "
            "to `get_lint_report`. Returns the standard diagnostics shape "
            "`{rule, diagnostics: [{file, line, message, severity, rule, label}], "
            "count}`. Severity is always `error` because Ren'Py crashes on these "
            "at runtime."
        ),
        input_schema=schema,
        handler=handler,
    )


def _find_undefined_characters(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.snapshot()
        defined = {c.var_name for c in snap.characters}
        diagnostics: list[dict[str, Any]] = []
        for label in snap.labels:
            tree = _walk_label_tree(config, label)
            for stmt in iter_statements(tree["body"]):
                if stmt["kind"] != "say":
                    continue
                who = stmt.get("character")
                if who is None or who in defined:
                    continue
                diagnostics.append(
                    {
                        "rule": "undefined_character",
                        "severity": "error",
                        "file": label.range.file,
                        "line": stmt["line"],
                        "label": label.name,
                        "message": (
                            f"`{who} \"...\"` — no character named `{who}` is "
                            "defined; add `define {who} = Character(...)` first"
                        ).format(who=who),
                    }
                )
        return _diag_payload(config, "undefined_character", diagnostics)

    return ToolDef(
        name="find_undefined_characters",
        description=(
            "Walk every label and flag every say-statement whose speaker tag "
            "is not bound by any `define x = Character(...)`. Narration "
            "(unquoted-name say) is ignored. Severity `error` — Ren'Py's "
            "engine treats undefined character variables as runtime "
            "NameErrors. Returns the standard diagnostics shape."
        ),
        input_schema=schema,
        handler=handler,
    )


def _find_unused_characters(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.snapshot()
        speakers: set[str] = set()
        for label in snap.labels:
            tree = _walk_label_tree(config, label)
            for stmt in iter_statements(tree["body"]):
                if stmt["kind"] == "say" and stmt.get("character"):
                    speakers.add(stmt["character"])
        diagnostics: list[dict[str, Any]] = []
        for char in snap.characters:
            if char.var_name in speakers:
                continue
            diagnostics.append(
                {
                    "rule": "unused_character",
                    "severity": "warning",
                    "file": char.range.file,
                    "line": char.range.start_line,
                    "label": None,
                    "message": (
                        f"character `{char.var_name}` is defined but never speaks; "
                        "either add dialogue or remove the definition"
                    ),
                }
            )
        return _diag_payload(config, "unused_character", diagnostics)

    return ToolDef(
        name="find_unused_characters",
        description=(
            "Flag every `define x = Character(...)` whose say-tag never appears "
            "in any label's dialogue. Severity `warning` — unused characters are "
            "harmless at runtime but usually indicate a half-finished cast or a "
            "rename that left the old definition behind. Returns the standard "
            "diagnostics shape; each entry points at the character's `define` "
            "line so the agent can either delete the definition or wire up "
            "missing dialogue."
        ),
        input_schema=schema,
        handler=handler,
    )


def _find_missing_assets(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.snapshot()
        diagnostics: list[dict[str, Any]] = []

        # Image refs come from the shared asset-resolution helper so this
        # diagnostic and `set_drafting_mode` agree on what's missing.
        for ref in collect_missing_image_refs(config, index):
            diagnostics.append(
                {
                    "rule": "missing_asset",
                    "severity": "error",
                    "file": ref["file"],
                    "line": ref["line"],
                    "label": ref["label"],
                    "message": (
                        f"image `{ref['name']}` is not defined as an alias, "
                        "layered image, or auto-named file under `game/images/`"
                    ),
                }
            )

        # Audio refs (and audio refs only) stay inline — drafting mode
        # doesn't generate audio fallbacks, so there's no shared helper.
        for label in snap.labels:
            tree = _walk_label_tree(config, label)
            for stmt in iter_statements(tree["body"]):
                if stmt["kind"] == "play":
                    asset = stmt["asset"]
                    if not asset:
                        continue
                    candidate = config.project_root / "game" / asset
                    if candidate.is_file():
                        continue
                    # Some projects store the path with a leading `audio/` —
                    # also accept assets given as just the relative path.
                    if (config.project_root / asset).is_file():
                        continue
                    diagnostics.append(
                        {
                            "rule": "missing_asset",
                            "severity": "error",
                            "file": label.range.file,
                            "line": stmt["line"],
                            "label": label.name,
                            "message": (
                                f"`play {stmt['channel']} \"{asset}\"` — file "
                                f"not found under `game/{asset}`"
                            ),
                        }
                    )
        return _diag_payload(config, "missing_asset", diagnostics)

    return ToolDef(
        name="find_missing_assets",
        description=(
            "Walk every label and flag every `scene`/`show`/`play` reference "
            "whose target asset can't be resolved. For images: not defined as "
            "an alias (`image bg park = ...`), not a `layeredimage`, and no "
            "auto-named file under `game/images/` (auto-naming converts "
            "filename underscores to spaces). For audio: the quoted path "
            "doesn't resolve under `game/`. Severity `error` because Ren'Py "
            "raises at runtime when the asset is reached. `show screen X` "
            "references are routed to `find_undefined_screens` instead."
        ),
        input_schema=schema,
        handler=handler,
    )


def _find_undefined_screens(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.snapshot()
        defined = {s.name for s in snap.screens}
        diagnostics: list[dict[str, Any]] = []

        for label in snap.labels:
            tree = _walk_label_tree(config, label)
            for stmt in iter_statements(tree["body"]):
                screen_name: str | None = None
                if stmt["kind"] == "show" and stmt["expression"].startswith("screen "):
                    screen_name = _first_word(stmt["expression"][len("screen ") :])
                elif stmt["kind"] == "call" and stmt["target"] == "screen":
                    rest = stmt.get("rest") or ""
                    screen_name = _first_word(rest) if rest else None
                if not screen_name or screen_name in defined:
                    continue
                diagnostics.append(
                    {
                        "rule": "undefined_screen",
                        "severity": "error",
                        "file": label.range.file,
                        "line": stmt["line"],
                        "label": label.name,
                        "message": (
                            f"screen `{screen_name}` is referenced but never "
                            "declared with `screen ...:`"
                        ),
                    }
                )
        return _diag_payload(config, "undefined_screen", diagnostics)

    return ToolDef(
        name="find_undefined_screens",
        description=(
            "Walk every label and flag every `show screen X` or `call screen "
            "X` whose screen has no `screen X():` declaration anywhere in the "
            "project. Severity `error` — Ren'Py raises at runtime on missing "
            "screens. Returns the standard diagnostics shape."
        ),
        input_schema=schema,
        handler=handler,
    )


def _find_unreachable_labels(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.snapshot()
        # Build forward edge map: label -> set of jump/call targets it reaches.
        # Anything reachable from `start` (or any `init_*` style entry, plus
        # explicit roots if they appear) is considered live.
        adjacency: dict[str, set[str]] = {}
        for label in snap.labels:
            tree = _walk_label_tree(config, label)
            adjacency[label.name] = set(tree["shorthand"]["outgoing_targets"])

        roots: set[str] = set()
        if any(l.name == "start" for l in snap.labels):
            roots.add("start")
        # Treat every `init`-prefixed label as a root too — users sometimes
        # author setup paths there. Conservative; reduces false positives.
        for label in snap.labels:
            if label.name.startswith("init"):
                roots.add(label.name)

        reachable: set[str] = set()
        stack: list[str] = list(roots)
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            for nxt in adjacency.get(current, ()):
                if nxt not in reachable:
                    stack.append(nxt)

        diagnostics: list[dict[str, Any]] = []
        for label in snap.labels:
            if label.name in reachable:
                continue
            if not roots:
                # No `start` and no `init*` label — every label is "unreachable"
                # which is just noise. Skip the diagnostic in that degenerate
                # case; `get_project_overview` already warns about no `start`.
                continue
            diagnostics.append(
                {
                    "rule": "unreachable_label",
                    "severity": "warning",
                    "file": label.range.file,
                    "line": label.range.start_line,
                    "label": label.name,
                    "message": (
                        f"label `{label.name}` is not reached from `start` via "
                        "any `jump`/`call`; either wire it in, mark it as an "
                        "intentional entry-point with an `init`-prefixed name, "
                        "or suppress this rule for the label"
                    ),
                }
            )
        return _diag_payload(config, "unreachable_label", diagnostics)

    return ToolDef(
        name="find_unreachable_labels",
        description=(
            "Flag every label not reachable from `start` (or from any "
            "`init`-prefixed label) by following `jump`/`call` edges, "
            "including those nested inside menus and if-branches. Severity "
            "`warning` — unreachable labels are dead code, not crashes. "
            "Useful before a release to spot orphaned drafts. Returns the "
            "standard diagnostics shape."
        ),
        input_schema=schema,
        handler=handler,
    )


def _read_ignored_diagnostics(config: ServerConfig) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        try:
            state = read_ignored(config)
        except DiagnosticsError as exc:
            return _err(str(exc))
        return _ok(
            {
                "version": state.version,
                "ignored": state.ignored,
                "count": len(state.ignored),
            }
        )

    return ToolDef(
        name="read_ignored_diagnostics",
        description=(
            "Return the suppression list applied to every `find_*` diagnostic "
            "tool. Backed by `.renpy-mcp/ignored_diagnostics.json`. Each "
            "entry is `{rule, file?, line?, label?}`: a diagnostic is "
            "suppressed when every field present in an entry equals the "
            "diagnostic's value. So `{rule: \"unused_character\"}` mutes that "
            "rule project-wide; `{rule, file, line}` mutes one occurrence. "
            "Pair with `set_ignored_diagnostics` (Tier 2) to update."
        ),
        input_schema=schema,
        handler=handler,
    )


def _get_choice_graph(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    """Walk every label, surface the menus and their branches as a flat
    choice graph. Powers the Choice View — the player-facing derived
    filter the ROADMAP committed to alongside Story Map.

    Each choice record describes ONE top-level `menu:` in a label and
    its branches. Per-branch `target` is the FIRST top-level `jump`/
    `call` in the branch's body — nested menus or `if`-conditional
    targets aren't unfolded; this matches the way authors think about a
    choice ("if I pick option X, where do I land next").
    """

    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.snapshot()
        choices: list[dict[str, Any]] = []
        for label in snap.labels:
            tree = parse_label_from_disk(config, label)
            for menu in (n for n in tree["body"] if n["kind"] == "menu"):
                branches = []
                for choice in menu["choices"]:
                    target_stmt = next(
                        (s for s in choice["body"] if s["kind"] in ("jump", "call")),
                        None,
                    )
                    branches.append(
                        {
                            "text": choice["text"],
                            "condition": choice["condition"],
                            "line": choice["line"],
                            "target": target_stmt["target"] if target_stmt else None,
                            "target_kind": target_stmt["kind"] if target_stmt else None,
                            "target_line": target_stmt["line"] if target_stmt else None,
                        }
                    )
                choices.append(
                    {
                        "label": label.name,
                        "file": label.range.file,
                        "line": menu["line"],
                        "menu_label": menu["menu_label"],
                        "branches": branches,
                    }
                )
        return _ok({"choices": choices, "count": len(choices)})

    return ToolDef(
        name="get_choice_graph",
        description=(
            "Return every top-level `menu:` in the project as a flat list of "
            "choice records. Each record has `{label, file, line, "
            "menu_label, branches}`; each branch carries `{text, condition, "
            "target, target_kind, target_line}`. The target is the FIRST "
            "top-level `jump`/`call` in the branch's body — nested menus or "
            "`if`-conditional targets aren't unfolded. Used by the Choice "
            "View to render the player-facing walkthrough."
        ),
        input_schema=schema,
        handler=handler,
    )


def _get_translation_coverage(config: ServerConfig) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        rows = coverage_summary(config)
        return _ok({"languages": rows, "count": len(rows)})

    return ToolDef(
        name="get_translation_coverage",
        description=(
            "Return per-language translation coverage from `game/tl/<lang>/`. "
            "Each row is `{language, total, translated, stale, percent}` "
            "where stale entries are those with empty translations or "
            "translations identical to the source. Returns an empty list "
            "when no `tl/` directory exists yet — call "
            "`generate_translation_scaffolding` to bootstrap one."
        ),
        input_schema=schema,
        handler=handler,
    )


def _find_stale_translations(config: ServerConfig) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "description": (
                    "Language directory name under `game/tl/` (e.g. `spanish`). "
                    "Omit to scan every language."
                ),
            },
        },
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        language: str | None = arguments.get("language")
        languages = [language] if language else list_languages(config)
        stale: list[dict[str, Any]] = []
        for lang in languages:
            for entry in parse_language(config, lang):
                if not entry.is_stale:
                    continue
                stale.append(
                    {
                        "language": lang,
                        "kind": entry.kind,
                        "block_id": entry.block_id,
                        "source": entry.source,
                        "target": entry.target,
                        "file": entry.file,
                        "line": entry.line,
                    }
                )
        return _ok({"stale": stale, "count": len(stale)})

    return ToolDef(
        name="find_stale_translations",
        description=(
            "Return translation entries that are still empty or identical to "
            "the source string. Pass `language` to filter to one directory; "
            "omit to scan every language under `game/tl/`. Each entry "
            "carries `{language, kind, block_id, source, target, file, "
            "line}` — kind is `say` (per-line dialogue translation) or "
            "`string` (string-table). Use after `generate_translation_"
            "scaffolding` to find the strings still needing human work."
        ),
        input_schema=schema,
        handler=handler,
    )


def _refresh_project(index: ProjectIndex) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        snap = index.refresh()
        return _ok(
            {
                "summary": "project index refreshed",
                "counts": {
                    "files": len(snap.files),
                    "labels": len(snap.labels),
                    "characters": len(snap.characters),
                    "defaults": len(snap.defaults),
                    "defines": len(snap.defines),
                    "images": len(snap.images),
                    "screens": len(snap.screens),
                },
            }
        )

    return ToolDef(
        name="refresh_project",
        description=(
            "Force a fresh scan of the project from disk. Use after an "
            "external write (another harness, a watcher event, manual edit) "
            "so subsequent read tools reflect the on-disk state. The server "
            "auto-refreshes after every internal write through `apply_write`; "
            "this tool exists for the out-of-band case."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- get_recent_edits ----------------------------------------------------


def _get_recent_edits() -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Maximum entries to return, newest-first. Omit for the "
                    "full ring buffer (capped at 50)."
                ),
            },
        },
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        limit = arguments.get("limit")
        entries = recent_buffer.snapshot(limit=limit if isinstance(limit, int) else None)
        return _ok(
            {
                "count": len(entries),
                "entries": [e.to_dict() for e in entries],
            }
        )

    return ToolDef(
        name="get_recent_edits",
        description=(
            "Return this server's most recent successful writes (newest-first) "
            "with timestamp, file path, summary, and unified diff. Useful for "
            "agent self-correction after a multi-step edit. Per-process buffer "
            "of the last 50 writes; a separate `renpy-mcp` instance (e.g. the "
            "GUI's own subprocess) has its own buffer."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- get_scaffold_status ------------------------------------------------


def _get_scaffold_status(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    """Report what's authored vs. still SDK-template placeholder."""
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        return _ok(scaffold_status.evaluate(config, index))

    return ToolDef(
        name="get_scaffold_status",
        description=(
            "Heuristic readout of how scaffolded the project still is: is "
            "`label start:` wired with a `jump`, are SDK template phrases "
            "(\"You've created a new Ren'Py game\") still present anywhere, "
            "are there route stubs whose body is only a TODO comment, is "
            "`config.name` still the template default, are the "
            "distribution-breaking template leftovers fixed. Returns a "
            "`fresh: bool` flag plus the standard findings shape with a "
            "`fix_hint` per finding telling the agent which tool to call. "
            "Cheap pure read; safe to run between writes."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- get_media_invariants -----------------------------------------------


def _get_media_invariants() -> ToolDef:
    """Return MEDIA.md's "four invariants" as a structured JSON shape.

    Cheaper for an agent to consume than re-reading the prose every turn.
    The dict mirrors `add_image_alias`'s compliance checks: anything that
    the warnings flag is encoded here. Read this BEFORE generating images,
    not after.
    """
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        return _ok(MEDIA_INVARIANTS)

    return ToolDef(
        name="get_media_invariants",
        description=(
            "Return the structured form of MEDIA.md's compatibility rules: "
            "expected format / size / alpha for backgrounds, sprites, CGs, "
            "UI; expected format / duration for music, voice, SFX, ambience; "
            "filename naming rules; directory layout. Call this BEFORE asking "
            "your image-generation tool for assets, so you can pin the right "
            "dimensions and ensure sprites come out with alpha."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- helpers -------------------------------------------------------------


def _first_word(text: str) -> str:
    """Return the first whitespace-separated token, or "" for empty input."""
    text = text.strip()
    if not text:
        return ""
    return text.split()[0]


def _label_dict(label: LabelInfo) -> dict[str, Any]:
    return {
        "name": label.name,
        "file": label.range.file,
        "start_line": label.range.start_line,
        "end_line": label.range.end_line,
        "say_count": label.say_count,
    }


def _character_dict(c: CharacterInfo) -> dict[str, Any]:
    return {
        "var": c.var_name,
        "display_name": c.display_name,
        "raw_args": c.raw_args,
        "file": c.range.file,
        "line": c.range.start_line,
    }


def _variable_dict(v: Any) -> dict[str, Any]:
    return {
        "name": v.name,
        "kind": v.kind,
        "value": v.raw_value,
        "file": v.range.file,
        "line": v.range.start_line,
    }


def _screen_dict(s: ScreenInfo) -> dict[str, Any]:
    return {
        "name": s.name,
        "file": s.range.file,
        "start_line": s.range.start_line,
        "end_line": s.range.end_line,
    }


def _slice_source(project_root: Path, rng: SourceRange) -> str:
    text = (project_root / rng.file).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    return "\n".join(lines[rng.start_line - 1 : rng.end_line])


def _ok(payload: Any) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False))]


def _err(message: str, **extra: Any) -> list[types.TextContent]:
    body: dict[str, Any] = {"error": message}
    body.update(extra)
    return [types.TextContent(type="text", text=json.dumps(body, indent=2, ensure_ascii=False))]
