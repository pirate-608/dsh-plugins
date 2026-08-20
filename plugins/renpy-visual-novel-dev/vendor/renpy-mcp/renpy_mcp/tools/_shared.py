"""Shared helpers for tool implementations across all tiers.

Anything used by more than one tier module lives here. Keep this module
free of tool-registration logic — it should be importable from every
tier without circular dependencies.
"""

from __future__ import annotations

import json
import re
from typing import Any

import mcp.types as types

from ..config import ServerConfig
from ..project.scanner import LabelInfo, ProjectIndex
from ..project.writer import WriteRejected, apply_write

BODY_INDENT = "    "


# ---------- response builders ---------------------------------------------------


def ok(payload: Any) -> list[types.TextContent]:
    """Wrap a JSON-serializable payload as the tool's TextContent response."""
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False))]


def err(message: str, **extra: Any) -> list[types.TextContent]:
    body: dict[str, Any] = {"error": message}
    body.update(extra)
    return [types.TextContent(type="text", text=json.dumps(body, indent=2, ensure_ascii=False))]


# ---------- text formatting -----------------------------------------------------


def quote(text: str) -> str:
    """Wrap `text` in double quotes, escaping `\\` and `\"` for Ren'Py."""
    safe = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{safe}"'


def num_str(value: float) -> str:
    """Format a number without a trailing `.0` for whole values."""
    if isinstance(value, int) or value == int(value):
        return str(int(value))
    return f"{value:g}"


# ---------- file-content edit primitives ---------------------------------------


def append_block(original: str, block_lines: list[str]) -> str:
    """Append a new top-level block (label/screen/transform) to file content."""
    block = "\n".join(block_lines)
    if not original:
        return block + "\n"
    if not original.endswith("\n"):
        return f"{original}\n\n{block}\n"
    return f"{original}\n{block}\n"


def splice_line(content: str, insert_at: int, new_line: str) -> str:
    """Insert `new_line` at the given 0-based line index."""
    lines = content.splitlines() if content else []
    lines.insert(insert_at, new_line)
    out = "\n".join(lines)
    if content.endswith("\n") or not content:
        out += "\n"
    return out


_DEFAULT_DEFINE_RE = re.compile(r"^(?:default|define)\s+")
_TOP_LEVEL_DECL_RE = re.compile(r"^(?:default|define|image|layeredimage|transform|screen)\s+")
_BLOCK_OPEN_TAIL_RE = re.compile(r":\s*(#.*)?$")


def find_default_insertion(content: str) -> int:
    """Return the 0-based line index after the last `default`/`define` line."""
    return _last_match_line_plus_one(content, _DEFAULT_DEFINE_RE)


def find_top_level_decl_insertion(content: str) -> int:
    """Return the 0-based line index after the last top-level declaration.

    Handles both one-liners (`default x = 1`, `image bg park = "..."`) and
    block-opening forms (`layeredimage x:`, `transform x():`, `screen x():`,
    `image complex:`). For block forms, advances past every indented body
    line so the returned index lands at top level — never inside a block.
    """
    if not content:
        return 0
    lines = content.splitlines()
    last_end = -1
    i = 0
    while i < len(lines):
        line = lines[i]
        if _TOP_LEVEL_DECL_RE.match(line):
            if _BLOCK_OPEN_TAIL_RE.search(line):
                j = i + 1
                while j < len(lines) and (lines[j] == "" or lines[j][:1] in (" ", "\t")):
                    j += 1
                last_end = j
                i = j
                continue
            last_end = i + 1
        i += 1
    return last_end if last_end >= 0 else 0


def _last_match_line_plus_one(content: str, pattern: re.Pattern[str]) -> int:
    if not content:
        return 0
    last = -1
    for idx, line in enumerate(content.splitlines()):
        if pattern.match(line):
            last = idx
    return last + 1 if last >= 0 else 0


# ---------- label lookup + body insertion --------------------------------------


def find_single_label(labels: tuple[LabelInfo, ...], name: str) -> LabelInfo | str:
    """Return the LabelInfo for `name`, or an error message string."""
    matches = [l for l in labels if l.name == name]
    if not matches:
        return f"no such label: `{name}`"
    if len(matches) > 1:
        return f"label `{name}` is declared in multiple places — fix the duplicates first"
    return matches[0]


_BODY_TERMINATOR_RE = re.compile(rf"^{BODY_INDENT}(?:jump\s+\w+|return)\s*$")


def label_terminator_line(label: LabelInfo, file_lines: list[str]) -> int | None:
    """Return the 0-based index of the label's trailing terminator, or None.

    A terminator is `jump <id>` or `return` at exactly the label body's
    indent level (4 spaces). Statements nested deeper (e.g. inside an if
    branch) do not count — they aren't the *label's* terminator, and
    inserting before them would land in the wrong block.
    """
    if label.range.end_line < 1:
        return None
    last_idx = label.range.end_line - 1
    if _BODY_TERMINATOR_RE.match(file_lines[last_idx]):
        return last_idx
    return None


def insert_into_label_body(
    config: ServerConfig,
    index: ProjectIndex,
    label: LabelInfo,
    body_lines: list[str],
    *,
    summary: str,
) -> list[types.TextContent]:
    """Append `body_lines` (auto-indented one level) to `label`'s body.

    If the label ends with a body-level `jump <x>` or `return`, the new
    lines are inserted BEFORE that terminator so they remain reachable.
    """
    rel = label.range.file
    text = (config.project_root / rel).read_text(encoding="utf-8")
    file_lines = text.splitlines()
    indented = [f"{BODY_INDENT}{ln}" for ln in body_lines]

    terminator_idx = label_terminator_line(label, file_lines)
    insert_at = terminator_idx if terminator_idx is not None else label.range.end_line

    new_lines = file_lines[:insert_at] + indented + file_lines[insert_at:]
    new_text = "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")
    return write_response(config, index, rel, new_text, summary=summary)


def write_response(
    config: ServerConfig,
    index: ProjectIndex,
    rel_file: str,
    new_text: str,
    *,
    summary: str,
) -> list[types.TextContent]:
    """Run the new content through `apply_write` and shape the tool response."""
    try:
        result = apply_write(config, index, rel_file, new_text, summary=summary)
    except WriteRejected as exc:
        return err(str(exc))
    return ok(
        {
            "summary": summary,
            "no_op": result.no_op,
            "file": result.file,
            "diff": result.diff,
            "warnings": result.warnings,
            "rpyc_cleaned": result.rpyc_cleaned,
        }
    )
