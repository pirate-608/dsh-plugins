"""Canvas-positions sidecar I/O for the Story Map.

Stores per-label `{x, y}` records in `<project_root>/.renpy-mcp/canvas.json`
so the GUI's editable Story Map can persist authored layouts. The sidecar
is GUI metadata, not Ren'Py syntax — it is not referenced from any `.rpy`
file, the engine never reads it, and `ProjectIndex` does not index it.

That is why the matching `set_canvas_positions` tool does NOT route
through `project.writer.apply_write`. apply_write's guarantees (label
uniqueness, indent normalization, `.rpyc` cleanup, unified-diff
generation, index refresh) are all about `.rpy` content and would be
either irrelevant or counterproductive here. This module mirrors the
pieces we still want — path containment, atomic write, no-op detection
— and is the second sanctioned exception alongside `new_project`
(see DESIGN.md §3 / §1a).

Schema:
    {
      "version": 1,
      "labels": {
        "<label_name>": { "x": <number>, "y": <number> }
      }
    }
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import ServerConfig

SIDECAR_DIR = ".renpy-mcp"
SIDECAR_FILENAME = "canvas.json"
SIDECAR_VERSION = 1


class CanvasError(Exception):
    """Raised when the sidecar is malformed or a position payload is invalid."""


@dataclass(frozen=True)
class CanvasPositions:
    version: int
    labels: dict[str, dict[str, float]]

    def to_payload(self) -> dict[str, Any]:
        return {"version": self.version, "labels": self.labels}


def sidecar_path(config: ServerConfig) -> Path:
    return config.project_root / SIDECAR_DIR / SIDECAR_FILENAME


def read_positions(config: ServerConfig) -> CanvasPositions:
    """Load the sidecar; return an empty record when the file does not exist."""
    path = sidecar_path(config)
    if not path.is_file():
        return CanvasPositions(version=SIDECAR_VERSION, labels={})
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise CanvasError(f"malformed canvas sidecar at {SIDECAR_DIR}/{SIDECAR_FILENAME}: {exc}") from exc

    if not isinstance(data, dict):
        raise CanvasError("canvas sidecar root must be an object")
    version = data.get("version", 1)
    labels = data.get("labels", {})
    if not isinstance(labels, dict):
        raise CanvasError("canvas sidecar `labels` must be an object")

    cleaned: dict[str, dict[str, float]] = {}
    for name, pos in labels.items():
        cleaned[name] = _coerce_position(name, pos)
    return CanvasPositions(version=int(version), labels=cleaned)


def set_positions(
    config: ServerConfig,
    incoming: dict[str, dict[str, Any]],
    *,
    replace: bool = False,
) -> CanvasPositions:
    """Merge `incoming` into the sidecar (or replace wholesale).

    Each value in `incoming` must coerce to `{x: number, y: number}` —
    extra keys are dropped. With `replace=False` (default) the merge
    leaves untouched labels in place; with `replace=True` the file is
    rewritten to exactly `incoming`.

    Returns the new state. Writes atomically; bails out without touching
    disk when the resulting payload matches what is already on disk.
    """
    validated: dict[str, dict[str, float]] = {
        name: _coerce_position(name, pos) for name, pos in incoming.items()
    }

    current = read_positions(config)
    if replace:
        merged = validated
    else:
        merged = {**current.labels, **validated}

    target = sidecar_path(config)
    _verify_inside_project(config, target)

    new_state = CanvasPositions(version=SIDECAR_VERSION, labels=merged)
    new_bytes = (json.dumps(new_state.to_payload(), indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    if target.is_file() and target.read_bytes() == new_bytes:
        return new_state  # no-op

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".renpy-mcp-tmp")
    tmp.write_bytes(new_bytes)
    os.replace(tmp, target)
    return new_state


def _coerce_position(name: str, pos: Any) -> dict[str, float]:
    if not isinstance(pos, dict):
        raise CanvasError(f"position for `{name}` must be an object with x and y")
    try:
        x = float(pos["x"])
        y = float(pos["y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CanvasError(f"position for `{name}` must have numeric x and y: {exc}") from exc
    return {"x": x, "y": y}


def _verify_inside_project(config: ServerConfig, target: Path) -> None:
    try:
        target.resolve().relative_to(config.project_root.resolve())
    except ValueError as exc:
        raise CanvasError(f"sidecar path escapes project_root: {target}") from exc
