"""Tolerant scanner for Ren'Py translation files under `game/tl/<lang>/`.

Ren'Py emits translations in two shapes that the parser handles
uniformly:

1. **Per-line dialogue translations.** Ren'Py inserts a `translate
   <lang> <hash_id>:` block whose body contains the translated say
   statement, with the source line preserved as a comment one row
   above::

        translate spanish hello_world_5a8d:
            # e "Hello world"
            e "Hola mundo"

   A translation is "stale" when the say-statement string equals the
   commented source string or is empty.

2. **String-table translations.** Used for screen text and menu
   choices::

        translate spanish strings:
            old "Welcome"
            new "Bienvenido"

   A translation is "stale" when `new` equals `old` or is empty.

Both forms are parsed line-by-line with cheap regex matching, in
keeping with the rest of the project's pragmatic-scanner approach.
Anything that doesn't match is silently skipped — translation files
with hand-edited extras (comments, custom logic) shouldn't cause the
coverage report to fail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import ServerConfig

TL_SUBDIR = "tl"

_TRANSLATE_BLOCK_RE = re.compile(
    r"^translate\s+(?P<lang>\w+)\s+(?P<id>[A-Za-z_]\w*)\s*:\s*$"
)
_STRINGS_BLOCK_RE = re.compile(r"^translate\s+(?P<lang>\w+)\s+strings\s*:\s*$")
_OLD_NEW_RE = re.compile(r"^\s*(old|new)\s+(?P<value>\".*?\"|'.*?')\s*$")
_SAY_NAMED_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s+(?P<text>\".*?\"|'.*?')\s*$")
_SAY_NARR_RE = re.compile(r"^\s*(?P<text>\".*?\"|'.*?')\s*$")
_SOURCE_COMMENT_RE = re.compile(r"^\s*#\s*(?:[A-Za-z_]\w*\s+)?(?P<text>\".*?\"|'.*?')\s*$")


@dataclass(frozen=True)
class TranslationEntry:
    kind: str  # "say" or "string"
    block_id: str  # the hash for "say"; literal "strings" for string-table
    source: str | None  # original text (None when the parser couldn't recover it)
    target: str  # translated text (empty string when untranslated)
    file: str  # POSIX path relative to project_root
    line: int  # 1-based

    @property
    def is_stale(self) -> bool:
        if not self.target:
            return True
        return self.source is not None and self.target == self.source


def list_languages(config: ServerConfig) -> list[str]:
    """Return every language directory present under `game/tl/`."""
    base = config.game_dir / TL_SUBDIR
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith("."))


def parse_language(config: ServerConfig, language: str) -> list[TranslationEntry]:
    """Walk every `.rpy` under `game/tl/<language>/` and return entries.

    Unknown languages return an empty list rather than raising; the GUI
    surfaces "no entries" instead of erroring out.
    """
    base = config.game_dir / TL_SUBDIR / language
    if not base.is_dir():
        return []
    entries: list[TranslationEntry] = []
    for path in sorted(base.rglob("*.rpy")):
        rel = path.relative_to(config.project_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        entries.extend(_parse_file(text, rel))
    return entries


def coverage_summary(config: ServerConfig) -> list[dict[str, Any]]:
    """Return per-language `{language, total, translated, stale, percent}` rows."""
    rows: list[dict[str, Any]] = []
    for lang in list_languages(config):
        entries = parse_language(config, lang)
        total = len(entries)
        stale = sum(1 for e in entries if e.is_stale)
        translated = total - stale
        percent = round(100 * translated / total, 1) if total else 0.0
        rows.append(
            {
                "language": lang,
                "total": total,
                "translated": translated,
                "stale": stale,
                "percent": percent,
            }
        )
    return rows


def _parse_file(text: str, rel: str) -> list[TranslationEntry]:
    lines = text.splitlines()
    out: list[TranslationEntry] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        m_strings = _STRINGS_BLOCK_RE.match(line)
        if m_strings:
            i = _consume_strings_block(lines, i + 1, rel, out)
            continue

        m_block = _TRANSLATE_BLOCK_RE.match(line)
        if m_block:
            i = _consume_say_block(lines, i + 1, m_block.group("id"), rel, out)
            continue

        i += 1
    return out


def _consume_say_block(
    lines: list[str],
    start: int,
    block_id: str,
    rel: str,
    out: list[TranslationEntry],
) -> int:
    """Consume the body of a `translate <lang> <id>:` block.

    The block is delimited by a body indented one level. We look for the
    first say-statement line; if a `# <source>` comment immediately
    precedes it, that's the source text. Returns the next index after
    the body.
    """
    n = len(lines)
    source: str | None = None
    target_line: int | None = None
    target_text: str | None = None

    for j in range(start, n):
        raw = lines[j]
        stripped = raw.strip()
        if not stripped:
            continue
        # Block ends when indent drops to 0 — we're back to top-level.
        indent = len(raw) - len(raw.lstrip())
        if indent == 0:
            break
        if stripped.startswith("#"):
            m = _SOURCE_COMMENT_RE.match(raw)
            if m:
                source = _strip_quotes(m.group("text"))
            continue
        # First non-comment body line is the translated say.
        m_named = _SAY_NAMED_RE.match(raw)
        m_narr = _SAY_NARR_RE.match(raw)
        if m_named:
            target_line = j + 1
            target_text = _strip_quotes(m_named.group("text"))
            break
        if m_narr:
            target_line = j + 1
            target_text = _strip_quotes(m_narr.group("text"))
            break

    # If we found a target line, record the entry. If no recognizable
    # say-statement was found inside the block, skip silently — the
    # block likely contains hand-edited Python or unusual constructs we
    # don't parse.
    next_i = start
    if target_line is not None and target_text is not None:
        out.append(
            TranslationEntry(
                kind="say",
                block_id=block_id,
                source=source,
                target=target_text,
                file=rel,
                line=target_line,
            )
        )
        next_i = target_line  # advance past the body line we consumed

    # Advance to the line after the block. We consumed up to the first
    # zero-indent non-empty line OR the say line.
    j = max(start, next_i)
    while j < len(lines):
        raw = lines[j]
        if raw.strip() and len(raw) - len(raw.lstrip()) == 0:
            break
        j += 1
    return j


def _consume_strings_block(
    lines: list[str],
    start: int,
    rel: str,
    out: list[TranslationEntry],
) -> int:
    """Consume the body of a `translate <lang> strings:` block.

    Pairs of `old "..."` / `new "..."` form one entry each. Pairs with
    a missing `new` (mismatched count) are skipped.
    """
    n = len(lines)
    pending_old: tuple[str, int] | None = None
    j = start
    while j < n:
        raw = lines[j]
        stripped = raw.strip()
        if not stripped:
            j += 1
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent == 0:
            break  # block ended
        m = _OLD_NEW_RE.match(raw)
        if m:
            kind = m.group(1)
            value = _strip_quotes(m.group("value"))
            if kind == "old":
                pending_old = (value, j + 1)
            elif kind == "new" and pending_old is not None:
                source, source_line = pending_old
                out.append(
                    TranslationEntry(
                        kind="string",
                        block_id="strings",
                        source=source,
                        target=value,
                        file=rel,
                        line=source_line,
                    )
                )
                pending_old = None
        j += 1
    return j


def _strip_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] in ('"', "'") and text[-1] == text[0]:
        return text[1:-1]
    return text
