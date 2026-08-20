"""Process-local ring buffer of recent successful writes.

`apply_write` calls `record(...)` after a successful (non-no-op) write so
agents can self-query "what did I just do." The buffer is intentionally
process-local: each renpy-mcp instance only sees its own writes, which
matches the file-system-as-integration-point invariant (DESIGN.md §1).

The GUI maintains a separate, richer buffer that distinguishes its own
writes from external ones; it lives at gui/backend/.../recent.py.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

MAX_ENTRIES = 50


@dataclass(frozen=True)
class RecentEdit:
    timestamp: float  # seconds since epoch (UTC)
    file: str
    summary: str
    diff: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "file": self.file,
            "summary": self.summary,
            "diff": self.diff,
            "warnings": list(self.warnings),
        }


_lock = threading.Lock()
_entries: deque[RecentEdit] = deque(maxlen=MAX_ENTRIES)


def record(file: str, *, summary: str, diff: str, warnings: list[str] | None = None) -> None:
    """Append an entry to the buffer. Thread-safe; no-op writes should not call this."""
    entry = RecentEdit(
        timestamp=time.time(),
        file=file,
        summary=summary,
        diff=diff,
        warnings=tuple(warnings or ()),
    )
    with _lock:
        _entries.append(entry)


def snapshot(limit: int | None = None) -> list[RecentEdit]:
    """Return the buffer newest-first. Pass `limit` to cap the size."""
    with _lock:
        items = list(_entries)
    items.reverse()
    if limit is not None and limit >= 0:
        items = items[:limit]
    return items


def clear() -> None:
    """Reset the buffer. Tests use this to isolate cases."""
    with _lock:
        _entries.clear()
