"""Tier 4 — escape hatches for edits the higher tiers can't express.

These tools bypass the structured intents; they still route every mutation
through `apply_write`, so the writer's guardrails (path containment,
label uniqueness, indent normalization, .rpyc cleanup, atomic write, diff
response) still apply. Use them when a targeted Tier 2/3 tool doesn't fit.

Opt-in: Tier 4 is OFF by default. Launch the server with `--tiers 1,2,3,4`
(or any superset that includes 4) to enable these tools.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

import mcp.types as types

from ..config import ServerConfig
from ..project.scanner import ProjectIndex
from ..project.writer import WriteRejected, apply_write
from ._shared import BODY_INDENT, err, ok
from .registry import ToolDef, ToolRegistry


def register(registry: ToolRegistry, config: ServerConfig, index: ProjectIndex) -> None:
    registry.add(_apply_unified_diff(config, index))
    registry.add(_exec_python_in_init(config, index))


# ---------- apply_unified_diff -------------------------------------------------


@dataclass
class _Hunk:
    old_block: list[str]
    new_block: list[str]


@dataclass
class _FilePatch:
    rel_path: str
    is_creation: bool  # `--- /dev/null`
    hunks: list[_Hunk]


_HUNK_HEADER_RE = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@")


def _parse_diff(diff: str) -> list[_FilePatch]:
    """Parse a unified diff into a list of per-file patches.

    Strict: rejects anything it doesn't recognize. The writer already
    defends against path escape and reserved filenames, so the parser's
    job is just to turn the diff into structured hunks.
    """
    lines = diff.splitlines()
    i = 0
    patches: list[_FilePatch] = []

    while i < len(lines):
        # Skip `diff --git ...` and `index ...` headers that often lead a hunk;
        # they're informational and `apply_write` doesn't need them.
        if lines[i].startswith(("diff ", "index ")):
            i += 1
            continue
        if not lines[i].startswith("--- "):
            if lines[i].strip() == "":
                i += 1
                continue
            raise ValueError(f"expected `--- ` header, got: {lines[i]!r}")

        from_line = lines[i]
        i += 1
        if i >= len(lines) or not lines[i].startswith("+++ "):
            raise ValueError("expected `+++ ` header after `--- `")
        to_line = lines[i]
        i += 1

        is_creation = from_line == "--- /dev/null"
        if to_line == "+++ /dev/null":
            raise ValueError(
                "file deletions are not supported via apply_unified_diff; "
                "remove the file with a dedicated tool instead"
            )

        rel_path = _strip_path_prefix(to_line[4:].strip())
        if not rel_path:
            raise ValueError("`+++ ` header missing a path")

        hunks: list[_Hunk] = []
        while i < len(lines) and _HUNK_HEADER_RE.match(lines[i]):
            i += 1  # skip hunk header
            old_block: list[str] = []
            new_block: list[str] = []
            while i < len(lines) and not lines[i].startswith(("--- ", "diff ")):
                if _HUNK_HEADER_RE.match(lines[i]):
                    break
                body_line = lines[i]
                if body_line == "" or body_line.startswith(" "):
                    content = body_line[1:] if body_line else ""
                    old_block.append(content)
                    new_block.append(content)
                elif body_line.startswith("-"):
                    old_block.append(body_line[1:])
                elif body_line.startswith("+"):
                    new_block.append(body_line[1:])
                elif body_line.startswith("\\"):
                    pass  # "\ No newline at end of file" marker
                else:
                    raise ValueError(
                        f"unexpected hunk body line (must start with ' ', '+', '-', or '\\'): {body_line!r}"
                    )
                i += 1
            hunks.append(_Hunk(old_block=old_block, new_block=new_block))

        if not hunks:
            raise ValueError(f"no hunks found for file {rel_path}")
        patches.append(_FilePatch(rel_path=rel_path, is_creation=is_creation, hunks=hunks))

    if not patches:
        raise ValueError("diff is empty")
    return patches


def _strip_path_prefix(path: str) -> str:
    # git-style `a/`, `b/` prefixes are the common case; strip them so the
    # path lines up with `apply_write`'s relative-to-project-root expectation.
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


def _apply_hunks(original: str, hunks: list[_Hunk]) -> str:
    """Apply every hunk to `original` in order, using strict context match.

    Each hunk's old_block must appear exactly once in the slice of content
    after the previous hunk. Ambiguous matches are rejected rather than
    picking one blindly.
    """
    out = original.splitlines()
    # If the original doesn't end with a newline, splitlines drops the
    # trailing newline-lessness implicitly; we reconstruct at the end.
    trailing_newline = original.endswith("\n") or original == ""

    search_from = 0
    for hi, hunk in enumerate(hunks, 1):
        if not hunk.old_block:
            # Pure append (creation-style hunk). Place at end of current content.
            out.extend(hunk.new_block)
            search_from = len(out)
            continue
        match_at = _find_unique(out, hunk.old_block, start=search_from)
        out = out[:match_at] + hunk.new_block + out[match_at + len(hunk.old_block):]
        search_from = match_at + len(hunk.new_block)

    text = "\n".join(out)
    if trailing_newline and text and not text.endswith("\n"):
        text += "\n"
    return text


def _find_unique(haystack: list[str], needle: list[str], *, start: int) -> int:
    """Return the single index in `haystack[start:]` where `needle` matches.

    Raises a ValueError if the match is missing or ambiguous so the tool
    can surface a readable rejection rather than silently picking one.
    """
    if not needle:
        raise ValueError("empty needle")
    matches: list[int] = []
    for i in range(start, len(haystack) - len(needle) + 1):
        if haystack[i : i + len(needle)] == needle:
            matches.append(i)
            if len(matches) > 1:
                break
    if not matches:
        raise ValueError("hunk context does not match current file content")
    if len(matches) > 1:
        raise ValueError(
            "hunk context matches multiple locations; tighten the context "
            "and retry (ambiguous hunks are refused rather than guessed)"
        )
    return matches[0]


def _apply_unified_diff(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "diff": {
                "type": "string",
                "description": (
                    "A standard unified diff. `--- /dev/null` is allowed for "
                    "new-file creation; `+++ /dev/null` (deletion) is refused. "
                    "Paths are relative to the project root; `a/`/`b/` prefixes "
                    "are stripped."
                ),
            },
        },
        "required": ["diff"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        diff_text = arguments.get("diff", "")
        if not isinstance(diff_text, str) or not diff_text.strip():
            return err("`diff` must be a non-empty string")

        try:
            patches = _parse_diff(diff_text)
        except ValueError as exc:
            return err(f"failed to parse diff: {exc}")

        results: list[dict[str, Any]] = []
        for patch in patches:
            target = config.project_root / patch.rel_path
            if patch.is_creation:
                original = ""
                if target.is_file():
                    return err(
                        f"diff requests creation but file already exists: {patch.rel_path}"
                    )
            else:
                if not target.is_file():
                    return err(
                        f"diff targets missing file {patch.rel_path}; use `--- /dev/null` for creation"
                    )
                original = target.read_text(encoding="utf-8")

            try:
                new_content = _apply_hunks(original, patch.hunks)
            except ValueError as exc:
                return err(f"{patch.rel_path}: {exc}")

            try:
                result = apply_write(config, index, patch.rel_path, new_content)
            except WriteRejected as exc:
                return err(f"{patch.rel_path}: {exc}")

            results.append(
                {
                    "file": result.file,
                    "no_op": result.no_op,
                    "diff": result.diff,
                    "warnings": result.warnings,
                    "rpyc_cleaned": result.rpyc_cleaned,
                }
            )

        return ok(
            {
                "summary": f"applied diff to {len(results)} file(s)",
                "results": results,
            }
        )

    return ToolDef(
        name="apply_unified_diff",
        description=(
            "Tier 4 escape hatch: apply a unified diff against one or more "
            ".rpy files under the project root. Context matching is strict — "
            "ambiguous or missing hunks are refused rather than guessed. "
            "File creation via `--- /dev/null` is supported; deletion is not. "
            "Every affected file still routes through `apply_write` so "
            "label uniqueness, indent normalization, .rpyc cleanup, and the "
            "atomic write pipeline all apply."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- exec_python_in_init -------------------------------------------------


def _exec_python_in_init(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "Python source to emit inside an `init python:` block. "
                    "Must parse with Python 3's ast.parse; one or more "
                    "statements are allowed."
                ),
            },
            "file": {
                "type": "string",
                "description": (
                    "Target .rpy file (relative to project root). Defaults to "
                    "`game/script.rpy`."
                ),
            },
            "priority": {
                "type": "integer",
                "description": (
                    "Optional init priority. Emits `init <N> python:` when set; "
                    "otherwise emits a bare `init python:`. Negative values run "
                    "earlier than positives. Typical range: -999 to 999."
                ),
            },
        },
        "required": ["code"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        code = arguments.get("code", "")
        if not isinstance(code, str) or not code.strip():
            return err("`code` must be a non-empty string")

        try:
            ast.parse(code)
        except SyntaxError as exc:
            return err(f"code failed to parse as Python: {exc.msg} (line {exc.lineno})")

        rel_file = arguments.get("file") or "game/script.rpy"
        if not isinstance(rel_file, str) or not rel_file.endswith(".rpy"):
            return err("`file` must be a .rpy path under the project root")

        priority = arguments.get("priority")
        if priority is not None and not isinstance(priority, int):
            return err("`priority` must be an integer")

        header = "init python:" if priority is None else f"init {priority} python:"
        block_lines = [header]
        for raw in code.splitlines():
            # Preserve blank lines inside the block but don't indent them.
            if raw.strip() == "":
                block_lines.append("")
            else:
                block_lines.append(f"{BODY_INDENT}{raw}")

        target = config.project_root / rel_file
        original = target.read_text(encoding="utf-8") if target.is_file() else ""
        block = "\n".join(block_lines)
        if not original:
            new_content = block + "\n"
        elif original.endswith("\n"):
            new_content = f"{original}\n{block}\n"
        else:
            new_content = f"{original}\n\n{block}\n"

        try:
            result = apply_write(config, index, rel_file, new_content)
        except WriteRejected as exc:
            return err(str(exc))

        return ok(
            {
                "summary": (
                    f"appended `init python:` block to {rel_file} "
                    f"({len(code.splitlines())} line(s) of Python)"
                ),
                "no_op": result.no_op,
                "file": result.file,
                "diff": result.diff,
                "warnings": result.warnings,
                "rpyc_cleaned": result.rpyc_cleaned,
            }
        )

    return ToolDef(
        name="exec_python_in_init",
        description=(
            "Tier 4 escape hatch: append an `init python:` block containing "
            "caller-supplied Python source to a .rpy file. The source is "
            "validated with Python's ast.parse before the write runs. Runs "
            "at engine init time, not during play; use this for one-off "
            "setup that no structured tool covers (custom Character classes, "
            "store constants, early registrations)."
        ),
        input_schema=schema,
        handler=handler,
    )


__all__ = ["register"]
