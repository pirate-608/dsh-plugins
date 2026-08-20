"""Reserved-name and reserved-filename checks.

Ren'Py reserves filenames starting with `00` for engine-bundled scripts;
creator files conventionally start with `01` to load early. Our writer
refuses to create or rewrite a `00`-prefixed file outright.

We also reject identifiers that collide with built-in Python or Ren'Py
keywords (a partial list — Ren'Py's own lint catches the rest).
"""

from __future__ import annotations

from pathlib import PurePosixPath

# Not exhaustive. The intent is to fail fast on the names LLMs actually
# pick by mistake; Ren'Py lint catches the long tail.
_RESERVED_IDENTS = frozenset(
    {
        "True", "False", "None", "if", "elif", "else", "for", "while",
        "def", "class", "return", "yield", "import", "from", "as", "with",
        "label", "menu", "scene", "show", "hide", "play", "stop", "queue",
        "voice", "jump", "call", "pause", "with", "init", "screen",
        "transform", "image", "default", "define", "python", "renpy",
        "config", "store", "build", "gui", "preferences", "persistent",
    }
)


def reject_reserved_filename(rel_path: str) -> str | None:
    """Return an error message if `rel_path`'s filename is engine-reserved."""
    name = PurePosixPath(rel_path).name
    if name.startswith("00") and name.endswith(".rpy"):
        return (
            f"refusing to write `{rel_path}`: filenames starting with `00` are "
            "reserved for Ren'Py engine scripts; use `01_` or higher for "
            "early-loading creator files"
        )
    return None


def reject_reserved_identifier(ident: str) -> str | None:
    """Return an error message if `ident` is a reserved keyword."""
    if ident in _RESERVED_IDENTS:
        return f"`{ident}` is a reserved Python/Ren'Py keyword and cannot be used as a name"
    return None
