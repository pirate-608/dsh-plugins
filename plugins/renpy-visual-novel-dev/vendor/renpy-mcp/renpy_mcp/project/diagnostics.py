"""Diagnostic suppression sidecar + shared filter helper.

Diagnostic-as-tools (Phase 1) gives the agent loop cheap pure reads that
flag known mistakes (`find_invalid_jumps`, `find_missing_assets`, …). In
practice some flagged sites are intentional — a stub label awaiting
later implementation, a character defined for an unfinished route, etc.
The suppression sidecar lets the author or harness mute specific entries
without fighting the diagnostics on every cycle.

Storage: `<project_root>/.renpy-mcp/ignored_diagnostics.json` — second
editor-metadata sidecar alongside `canvas.json` (DESIGN.md §3 lists the
sanctioned non-`apply_write` write paths).

Schema:
    {
      "version": 1,
      "ignored": [
        {"rule": "<rule>", "file": "<rel>"?, "line": <int>?, "label": "<name>"?},
        ...
      ]
    }

Match semantics: an entry suppresses a diagnostic when every field
present in the entry equals the corresponding field on the diagnostic.
So `{"rule": "unused_character"}` mutes every unused-character finding;
`{"rule": "X", "file": "Y"}` mutes that rule only in that file; etc.
The most-specific shape `{rule, file, line}` mutes one occurrence.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import ServerConfig

SIDECAR_DIR = ".renpy-mcp"
SIDECAR_FILENAME = "ignored_diagnostics.json"
SIDECAR_VERSION = 1

# Fields a suppression entry is allowed to constrain. Anything else is
# rejected at write time so a typo never silently no-ops.
ENTRY_FIELDS = ("rule", "file", "line", "label")


class DiagnosticsError(Exception):
    """Raised when the sidecar is malformed or an entry is invalid."""


@dataclass(frozen=True)
class IgnoredDiagnostics:
    version: int
    ignored: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        return {"version": self.version, "ignored": self.ignored}


def sidecar_path(config: ServerConfig) -> Path:
    return config.project_root / SIDECAR_DIR / SIDECAR_FILENAME


def read_ignored(config: ServerConfig) -> IgnoredDiagnostics:
    """Load the sidecar; return an empty record when the file does not exist."""
    path = sidecar_path(config)
    if not path.is_file():
        return IgnoredDiagnostics(version=SIDECAR_VERSION, ignored=[])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiagnosticsError(
            f"malformed sidecar at {SIDECAR_DIR}/{SIDECAR_FILENAME}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise DiagnosticsError("sidecar root must be an object")
    version = data.get("version", 1)
    raw = data.get("ignored", [])
    if not isinstance(raw, list):
        raise DiagnosticsError("sidecar `ignored` must be an array")

    cleaned = [_validate_entry(e) for e in raw]
    return IgnoredDiagnostics(version=int(version), ignored=cleaned)


def set_ignored(
    config: ServerConfig,
    incoming: list[dict[str, Any]],
    *,
    replace: bool = False,
) -> IgnoredDiagnostics:
    """Append `incoming` (de-duplicated) to the sidecar, or replace wholesale.

    Each entry must have at minimum a `rule`; `file`, `line`, `label` are
    optional narrowing fields. Any other field is rejected. With
    `replace=False` (default) the new entries are appended to the
    existing list with exact-equal duplicates dropped; with
    `replace=True` the file is rewritten to exactly `incoming`.
    """
    if not isinstance(incoming, list):
        raise DiagnosticsError("entries must be a list")
    validated = [_validate_entry(e) for e in incoming]

    current = read_ignored(config)
    if replace:
        merged = validated
    else:
        merged = list(current.ignored)
        for entry in validated:
            if entry not in merged:
                merged.append(entry)

    target = sidecar_path(config)
    _verify_inside_project(config, target)

    new_state = IgnoredDiagnostics(version=SIDECAR_VERSION, ignored=merged)
    new_bytes = (
        json.dumps(new_state.to_payload(), indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")

    if target.is_file() and target.read_bytes() == new_bytes:
        return new_state  # no-op

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".renpy-mcp-tmp")
    tmp.write_bytes(new_bytes)
    os.replace(tmp, target)
    return new_state


def filter_diagnostics(
    diagnostics: list[dict[str, Any]],
    ignored: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Apply suppression filtering. Returns (kept, suppressed_count)."""
    if not ignored:
        return list(diagnostics), 0
    kept: list[dict[str, Any]] = []
    suppressed = 0
    for diag in diagnostics:
        if any(_pattern_matches(p, diag) for p in ignored):
            suppressed += 1
        else:
            kept.append(diag)
    return kept, suppressed


# ---------- internals -----------------------------------------------------------


def _pattern_matches(pattern: dict[str, Any], diag: dict[str, Any]) -> bool:
    for key, expected in pattern.items():
        if diag.get(key) != expected:
            return False
    return True


def _validate_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise DiagnosticsError("each ignored entry must be an object")
    if "rule" not in entry or not isinstance(entry["rule"], str) or not entry["rule"]:
        raise DiagnosticsError("each ignored entry must have a non-empty `rule` string")
    extra = set(entry) - set(ENTRY_FIELDS)
    if extra:
        raise DiagnosticsError(
            f"unsupported keys in ignored entry: {sorted(extra)}; "
            f"allowed keys: {list(ENTRY_FIELDS)}"
        )
    cleaned: dict[str, Any] = {"rule": entry["rule"]}
    if "file" in entry:
        if not isinstance(entry["file"], str):
            raise DiagnosticsError("`file` must be a string when present")
        cleaned["file"] = entry["file"]
    if "line" in entry:
        if not isinstance(entry["line"], int) or isinstance(entry["line"], bool):
            raise DiagnosticsError("`line` must be an integer when present")
        cleaned["line"] = entry["line"]
    if "label" in entry:
        if not isinstance(entry["label"], str):
            raise DiagnosticsError("`label` must be a string when present")
        cleaned["label"] = entry["label"]
    return cleaned


def _verify_inside_project(config: ServerConfig, target: Path) -> None:
    try:
        target.resolve().relative_to(config.project_root.resolve())
    except ValueError as exc:
        raise DiagnosticsError(f"sidecar path escapes project_root: {target}") from exc
