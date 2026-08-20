"""Asset-reference resolution shared between diagnostics and lifecycle tools.

`find_missing_assets` and `set_drafting_mode` both need to know which
image references in `.rpy` files don't resolve to anything Ren'Py can
load. Routing both through a single helper keeps "what's missing" and
"what gets faked" identical — agents see the same list in the
diagnostic and the drafting-mode summary.

Audio references stay inline in `find_missing_assets` for now —
drafting mode only injects image fallbacks (a silent audio fallback is
both ambiguous and rarely useful while iterating).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..config import ServerConfig
from .label_tree import iter_statements, parse_label_from_disk
from .scanner import ProjectIndex

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
_IMAGE_SUFFIX_RE = re.compile(r"\s+(?:at|with|behind|onlayer|zorder|as)\b.*$")


def collect_missing_image_refs(
    config: ServerConfig,
    index: ProjectIndex,
) -> list[dict[str, Any]]:
    """Return one record per UNRESOLVED image reference in any label.

    Each record has `name` (the parsed image name), `file` (relative path
    of the label that references it), `line` (1-based file line), and
    `label` (the label name). The same image name referenced from
    multiple sites yields multiple records — callers that want a
    deduplicated set should collapse on `name` themselves.

    `show screen X` references are excluded — those belong to
    `find_undefined_screens`, not the asset surface.
    """
    snap = index.snapshot()
    aliases = {img.name for img in snap.images}
    layered = {li.name for li in snap.layered_images}
    auto = _scan_auto_image_names(config)

    out: list[dict[str, Any]] = []
    for label in snap.labels:
        tree = parse_label_from_disk(config, label)
        for stmt in iter_statements(tree["body"]):
            if stmt["kind"] not in ("scene", "show", "hide"):
                continue
            name = _extract_image_base(stmt["expression"])
            if not name:
                continue
            if name.startswith("screen "):
                continue
            if (
                name in aliases
                or name in layered
                or name in auto
                or _first_word(name) in layered
            ):
                continue
            out.append(
                {
                    "name": name,
                    "file": label.range.file,
                    "line": stmt["line"],
                    "label": label.name,
                }
            )
    return out


def _scan_auto_image_names(config: ServerConfig) -> set[str]:
    """Auto-named image files become image identifiers with underscores → spaces."""
    names: set[str] = set()
    images_dir = config.game_dir / "images"
    if not images_dir.is_dir():
        return names
    for path in images_dir.rglob("*"):
        if path.suffix.lower() in _IMAGE_EXTS:
            names.add(path.stem.replace("_", " "))
    return names


def _extract_image_base(expression: str) -> str:
    """Strip ` at left`, ` with dissolve`, etc. from a scene/show expression."""
    return _IMAGE_SUFFIX_RE.sub("", expression).strip()


def _first_word(text: str) -> str:
    text = text.strip()
    return text.split()[0] if text else ""
