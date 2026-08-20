"""Tolerant scanner over a Ren'Py project's `game/` tree.

We deliberately do not implement a full Ren'Py parser. Tools only need to
locate top-level constructs (labels, characters, defines, images) and slice
their source ranges. Anything deeper than that gets answered by reading the
raw lines back out of the file.

Indentation rule for slicing blocks: a label/transform/screen/image block
ends when we hit the next non-blank line whose indent is <= the header's
indent. Blank lines and comment-only lines are tolerated inside the block.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from ..config import ServerConfig

# Header line patterns. We only care about column-zero declarations because
# nested labels/screens are vanishingly rare and not worth the complexity.
_LABEL_RE = re.compile(r"^label\s+([A-Za-z_]\w*)\s*(?:\([^)]*\))?\s*:")
_CHARACTER_RE = re.compile(
    r"^define\s+([A-Za-z_]\w*)\s*=\s*Character\s*\(\s*(?P<args>.*?)\)\s*$"
)
_DEFAULT_RE = re.compile(r"^default\s+([A-Za-z_][\w.]*)\s*=\s*(.+?)\s*$")
_DEFINE_RE = re.compile(r"^define\s+([A-Za-z_][\w.]*)\s*=\s*(.+?)\s*$")
_IMAGE_RE = re.compile(r"^image\s+(?P<name>[\w ]+?)\s*=\s*(?P<value>.+?)\s*$")
_LAYEREDIMAGE_RE = re.compile(r"^layeredimage\s+([A-Za-z_]\w*)\s*:")
_TRANSFORM_RE = re.compile(r"^transform\s+([A-Za-z_]\w*)\s*(?:\([^)]*\))?\s*:")
_SCREEN_RE = re.compile(r"^screen\s+([A-Za-z_]\w*)\s*(?:\([^)]*\))?\s*:")
_PLAY_RE = re.compile(r"^\s*play\s+(\w+)\s+(\".+?\"|'.+?')")
# A say-statement reference inside a label, used only to produce a line-count
# heuristic in the overview. Catches both `e "text"` and `"Name" "text"`.
_SAY_RE = re.compile(r"^\s*(?:[A-Za-z_]\w*\s+)?\".*?\"\s*$")
# Character-string extraction: pulls the first quoted positional arg, if any.
_CHARACTER_DISPLAY_RE = re.compile(r"^\s*(\".*?\"|'.*?')")


@dataclass(frozen=True)
class SourceRange:
    file: str  # path relative to project_root, POSIX-style
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive


@dataclass(frozen=True)
class LabelInfo:
    name: str
    range: SourceRange
    say_count: int


@dataclass(frozen=True)
class CharacterInfo:
    var_name: str
    display_name: str | None
    range: SourceRange
    raw_args: str


@dataclass(frozen=True)
class VariableInfo:
    name: str
    kind: str  # "default" or "define"
    raw_value: str
    range: SourceRange


@dataclass(frozen=True)
class ImageInfo:
    name: str  # full image name as written, e.g. "bg park"
    raw_value: str  # right-hand side of the assignment
    range: SourceRange


@dataclass(frozen=True)
class AudioPlayInfo:
    channel: str
    asset: str
    range: SourceRange


@dataclass(frozen=True)
class ScreenInfo:
    name: str
    range: SourceRange


@dataclass(frozen=True)
class TransformInfo:
    name: str
    range: SourceRange


@dataclass(frozen=True)
class LayeredImageInfo:
    name: str
    range: SourceRange


@dataclass(frozen=True)
class ProjectSnapshot:
    files: tuple[str, ...]
    labels: tuple[LabelInfo, ...]
    characters: tuple[CharacterInfo, ...]
    defaults: tuple[VariableInfo, ...]
    defines: tuple[VariableInfo, ...]
    images: tuple[ImageInfo, ...]
    layered_images: tuple[LayeredImageInfo, ...]
    screens: tuple[ScreenInfo, ...]
    transforms: tuple[TransformInfo, ...]
    audio_plays: tuple[AudioPlayInfo, ...]
    duplicate_labels: tuple[str, ...] = field(default=())


class ProjectIndex:
    """Lazily scans the project on first access; refresh() invalidates the cache."""

    def __init__(self, config: ServerConfig) -> None:
        self._config = config
        self._snapshot: ProjectSnapshot | None = None
        self._lock = threading.Lock()

    def snapshot(self) -> ProjectSnapshot:
        with self._lock:
            if self._snapshot is None:
                self._snapshot = _scan(self._config.project_root, self._config.game_dir)
            return self._snapshot

    def refresh(self) -> ProjectSnapshot:
        with self._lock:
            self._snapshot = _scan(self._config.project_root, self._config.game_dir)
            return self._snapshot


def _scan(project_root: Path, game_dir: Path) -> ProjectSnapshot:
    files: list[str] = []
    labels: list[LabelInfo] = []
    characters: list[CharacterInfo] = []
    defaults: list[VariableInfo] = []
    defines: list[VariableInfo] = []
    images: list[ImageInfo] = []
    layered_images: list[LayeredImageInfo] = []
    screens: list[ScreenInfo] = []
    transforms: list[TransformInfo] = []
    audio_plays: list[AudioPlayInfo] = []

    for rpy in sorted(game_dir.rglob("*.rpy")):
        rel = rpy.relative_to(project_root).as_posix()
        files.append(rel)
        text = rpy.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        _scan_file(
            rel,
            lines,
            labels=labels,
            characters=characters,
            defaults=defaults,
            defines=defines,
            images=images,
            layered_images=layered_images,
            screens=screens,
            transforms=transforms,
        )
        _scan_audio_plays(rel, lines, audio_plays)

    seen: dict[str, int] = {}
    for label in labels:
        seen[label.name] = seen.get(label.name, 0) + 1
    duplicates = tuple(sorted(name for name, count in seen.items() if count > 1))

    return ProjectSnapshot(
        files=tuple(files),
        labels=tuple(labels),
        characters=tuple(characters),
        defaults=tuple(defaults),
        defines=tuple(defines),
        images=tuple(images),
        layered_images=tuple(layered_images),
        screens=tuple(screens),
        transforms=tuple(transforms),
        audio_plays=tuple(audio_plays),
        duplicate_labels=duplicates,
    )


def _scan_audio_plays(rel: str, lines: list[str], audio_plays: list[AudioPlayInfo]) -> None:
    for idx, line in enumerate(lines):
        m = _PLAY_RE.match(line)
        if m:
            audio_plays.append(
                AudioPlayInfo(
                    channel=m.group(1),
                    asset=m.group(2).strip("'\""),
                    range=SourceRange(file=rel, start_line=idx + 1, end_line=idx + 1),
                )
            )


def _scan_file(
    rel: str,
    lines: list[str],
    *,
    labels: list[LabelInfo],
    characters: list[CharacterInfo],
    defaults: list[VariableInfo],
    defines: list[VariableInfo],
    images: list[ImageInfo],
    layered_images: list[LayeredImageInfo],
    screens: list[ScreenInfo],
    transforms: list[TransformInfo],
) -> None:
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Block constructs at column 0.
        if indent == 0 and stripped:
            m = _LABEL_RE.match(stripped)
            if m:
                end = _block_end(lines, i)
                say_count = sum(1 for j in range(i + 1, end + 1) if _SAY_RE.match(lines[j]))
                labels.append(
                    LabelInfo(
                        name=m.group(1),
                        range=SourceRange(file=rel, start_line=i + 1, end_line=end + 1),
                        say_count=say_count,
                    )
                )
                i = end + 1
                continue

            m = _LAYEREDIMAGE_RE.match(stripped)
            if m:
                end = _block_end(lines, i)
                layered_images.append(
                    LayeredImageInfo(
                        name=m.group(1),
                        range=SourceRange(file=rel, start_line=i + 1, end_line=end + 1),
                    )
                )
                i = end + 1
                continue

            m = _TRANSFORM_RE.match(stripped)
            if m:
                end = _block_end(lines, i)
                transforms.append(
                    TransformInfo(
                        name=m.group(1),
                        range=SourceRange(file=rel, start_line=i + 1, end_line=end + 1),
                    )
                )
                i = end + 1
                continue

            m = _SCREEN_RE.match(stripped)
            if m:
                end = _block_end(lines, i)
                screens.append(
                    ScreenInfo(
                        name=m.group(1),
                        range=SourceRange(file=rel, start_line=i + 1, end_line=end + 1),
                    )
                )
                i = end + 1
                continue

            # Character must be tested before generic define.
            m = _CHARACTER_RE.match(stripped)
            if m:
                args = m.group("args")
                disp_match = _CHARACTER_DISPLAY_RE.match(args)
                display = disp_match.group(1).strip("'\"") if disp_match else None
                characters.append(
                    CharacterInfo(
                        var_name=m.group(1),
                        display_name=display,
                        range=SourceRange(file=rel, start_line=i + 1, end_line=i + 1),
                        raw_args=args.strip(),
                    )
                )
                i += 1
                continue

            m = _DEFAULT_RE.match(stripped)
            if m:
                defaults.append(
                    VariableInfo(
                        name=m.group(1),
                        kind="default",
                        raw_value=m.group(2),
                        range=SourceRange(file=rel, start_line=i + 1, end_line=i + 1),
                    )
                )
                i += 1
                continue

            m = _IMAGE_RE.match(stripped)
            if m:
                images.append(
                    ImageInfo(
                        name=m.group("name").strip(),
                        raw_value=m.group("value").strip(),
                        range=SourceRange(file=rel, start_line=i + 1, end_line=i + 1),
                    )
                )
                i += 1
                continue

            m = _DEFINE_RE.match(stripped)
            if m:
                defines.append(
                    VariableInfo(
                        name=m.group(1),
                        kind="define",
                        raw_value=m.group(2),
                        range=SourceRange(file=rel, start_line=i + 1, end_line=i + 1),
                    )
                )
                i += 1
                continue

        i += 1


def _block_end(lines: list[str], header_idx: int) -> int:
    """Return the last line index belonging to the block whose header is at `header_idx`."""
    header_indent = len(lines[header_idx]) - len(lines[header_idx].lstrip())
    last = header_idx
    for j in range(header_idx + 1, len(lines)):
        line = lines[j]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= header_indent:
            return last
        last = j
    return len(lines) - 1
