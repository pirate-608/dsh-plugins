"""Guarded write pipeline for .rpy files.

Every Tier 2/3 mutation routes through `apply_write`. The function:

1. Rejects writes outside `project_root` and to reserved filenames.
2. Normalizes tab indentation to 4 spaces.
3. Pre-checks label uniqueness against the existing project snapshot.
4. Reads the original content (if any) and bails out cleanly if the new
   content is byte-identical (no-op).
5. Writes atomically (temp + rename inside the same directory).
6. Removes any sibling `.rpyc`/`.rpyc.bak` shadow so the engine recompiles
   from source on next run.
7. Generates a unified diff against the pre-write content.
8. Refreshes the in-memory index so subsequent reads see the change.
"""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..config import ServerConfig
from ..guardrails import indent as indent_guard
from ..guardrails import labels as label_guard
from ..guardrails import reserved as reserved_guard
from . import recent as recent_buffer
from .scanner import ProjectIndex


class WriteRejected(Exception):
    """Raised when the writer refuses to apply a mutation."""


@dataclass
class WriteResult:
    file: str
    diff: str
    warnings: list[str] = field(default_factory=list)
    rpyc_cleaned: list[str] = field(default_factory=list)
    no_op: bool = False


def apply_write(
    config: ServerConfig,
    index: ProjectIndex,
    rel_path: str,
    new_content: str,
    *,
    summary: str | None = None,
) -> WriteResult:
    target = _resolve_inside(config.project_root, rel_path)

    if rejection := reserved_guard.reject_reserved_filename(rel_path):
        raise WriteRejected(rejection)

    # 4-space indent normalization. Stays a warning, not an error.
    normalized, indent_warnings = indent_guard.normalize_tabs(new_content)

    # Label uniqueness — block the write if it would introduce a cross-file collision.
    snapshot = index.snapshot()
    collisions = label_guard.find_collisions(snapshot, rel_path, normalized)
    if collisions:
        raise WriteRejected(
            f"label name(s) already exist elsewhere in the project: {', '.join(collisions)}"
        )

    original = target.read_text(encoding="utf-8") if target.is_file() else ""
    if original == normalized:
        return WriteResult(file=rel_path, diff="", warnings=indent_warnings, no_op=True)

    # Atomic write: temp file in the same directory, then rename.
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".renpy-mcp-tmp")
    tmp.write_text(normalized, encoding="utf-8")
    os.replace(tmp, target)

    rpyc_cleaned = _clean_rpyc_shadows(target)

    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            normalized.splitlines(keepends=True),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            n=3,
        )
    )

    index.refresh()

    recent_buffer.record(
        file=rel_path,
        summary=summary or f"wrote {rel_path}",
        diff=diff,
        warnings=indent_warnings,
    )

    return WriteResult(
        file=rel_path,
        diff=diff,
        warnings=indent_warnings,
        rpyc_cleaned=rpyc_cleaned,
    )


def delete_file(config: ServerConfig, index: ProjectIndex, rel_path: str) -> WriteResult:
    """Delete a .rpy file (and its .rpyc shadow). Used by rename_label-style ops."""
    target = _resolve_inside(config.project_root, rel_path)
    if rejection := reserved_guard.reject_reserved_filename(rel_path):
        raise WriteRejected(rejection)
    if not target.is_file():
        raise WriteRejected(f"cannot delete; file does not exist: {rel_path}")

    original = target.read_text(encoding="utf-8")
    target.unlink()
    rpyc_cleaned = _clean_rpyc_shadows(target)
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            [],
            fromfile=f"a/{rel_path}",
            tofile="/dev/null",
            n=3,
        )
    )
    index.refresh()
    return WriteResult(file=rel_path, diff=diff, rpyc_cleaned=rpyc_cleaned)


def _resolve_inside(project_root: Path, rel_path: str) -> Path:
    target = (project_root / rel_path).resolve()
    try:
        target.relative_to(project_root.resolve())
    except ValueError as exc:
        raise WriteRejected(f"path escapes project_root: {rel_path}") from exc
    return target


def _clean_rpyc_shadows(rpy_path: Path) -> list[str]:
    """Remove the .rpyc and .rpyc.bak siblings of a .rpy file."""
    cleaned: list[str] = []
    for ext in (".rpyc", ".rpyc.bak"):
        candidate = rpy_path.with_suffix(ext)
        if candidate.is_file():
            candidate.unlink()
            cleaned.append(candidate.name)
    return cleaned
