"""Label-uniqueness validation.

Ren'Py treats every .rpy file as one giant script, so label names must be
unique across the whole `game/` tree. This guard runs BEFORE writing: given
the proposed new content for one file plus the existing project snapshot,
it returns the list of names that would collide.
"""

from __future__ import annotations

import re

from ..project.scanner import ProjectSnapshot

_LABEL_RE = re.compile(r"^label\s+([A-Za-z_]\w*)\s*(?:\([^)]*\))?\s*:", re.MULTILINE)


def label_names_in(text: str) -> list[str]:
    """Return every top-level label name declared in `text`, in order."""
    return _LABEL_RE.findall(text)


def find_collisions(
    snapshot: ProjectSnapshot, target_file: str, new_content: str
) -> list[str]:
    """Return label names in `new_content` that already exist in OTHER files.

    Same-file labels are not collisions: they will be re-scanned post-write.
    """
    proposed = set(label_names_in(new_content))
    if not proposed:
        return []
    existing_elsewhere = {
        l.name for l in snapshot.labels if l.range.file != target_file
    }
    return sorted(proposed & existing_elsewhere)
