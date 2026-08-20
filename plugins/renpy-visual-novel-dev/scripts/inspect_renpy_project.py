#!/usr/bin/env python3
"""Print a compact structural audit for a Ren'Py project."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SCRIPT_EXTENSIONS = {".rpy", ".rpym"}
GENERATED_PARTS = {"cache", "saves"}
ASSET_EXTENSIONS = {
    ".avif",
    ".flac",
    ".jpg",
    ".jpeg",
    ".mp3",
    ".ogg",
    ".opus",
    ".png",
    ".svg",
    ".ttf",
    ".otf",
    ".wav",
    ".webm",
    ".webp",
}


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def is_generated(path: Path, game_dir: Path) -> bool:
    try:
        rel = path.relative_to(game_dir)
    except ValueError:
        return False
    return bool(rel.parts and rel.parts[0] in GENERATED_PARTS)


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", default=".", help="Ren'Py project root")
    args = parser.parse_args()

    root = Path(args.project).resolve()
    game_dir = root / "game"

    print(f"Project: {root}")
    if not game_dir.is_dir():
        print("Status: no game/ directory found")
        return 1

    scripts = []
    compiled = []
    assets = []
    generated = []

    for path in iter_files(game_dir):
        if is_generated(path, game_dir):
            generated.append(path)
            continue
        suffix = path.suffix.lower()
        if suffix in SCRIPT_EXTENSIONS:
            scripts.append(path)
        elif suffix in {".rpyc", ".rpymc"}:
            compiled.append(path)
        elif suffix in ASSET_EXTENSIONS:
            assets.append(path)

    labels: list[tuple[str, str]] = []
    characters: list[tuple[str, str]] = []
    menus: list[str] = []
    tab_lines: list[str] = []
    cjk_lines: list[str] = []
    configured_fonts: set[str] = set()

    label_re = re.compile(r"^\s*label\s+([A-Za-z_][A-Za-z0-9_]*)\s*:", re.MULTILINE)
    char_re = re.compile(r"^\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*Character\((.*?)\)", re.MULTILINE)
    menu_re = re.compile(r"^\s*menu\s*:", re.MULTILINE)
    cjk_re = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
    font_re = re.compile(
        r"(?:gui\.(?:text|name_text|interface_text|button_text)_font|style\.[A-Za-z0-9_]+\.font)"
        r"\s*=\s*['\"]([^'\"]+)['\"]"
    )

    for script in scripts:
        text = read_text(script)
        rel = script.relative_to(root)
        for match in label_re.finditer(text):
            labels.append((str(rel), match.group(1)))
        for match in char_re.finditer(text):
            characters.append((str(rel), f"{match.group(1)} = Character({match.group(2)})"))
        if menu_re.search(text):
            menus.append(str(rel))
        configured_fonts.update(font_re.findall(text))
        for number, line in enumerate(text.splitlines(), start=1):
            if "\t" in line:
                tab_lines.append(f"{rel}:{number}")
            if cjk_re.search(line):
                cjk_lines.append(f"{rel}:{number}")

    print(f"Scripts: {len(scripts)} .rpy/.rpym files")
    print(f"Compiled scripts: {len(compiled)} .rpyc/.rpymc files")
    print(f"Assets: {len(assets)} recognized media/font files")
    print(f"Generated files skipped: {len(generated)} in game/cache or game/saves")
    bundled_fonts = [path for path in assets if path.suffix.lower() in {".ttf", ".otf"}]
    print(f"CJK text locations: {len(cjk_lines)}")
    print(f"Bundled fonts: {len(bundled_fonts)}; configured font references: {len(configured_fonts)}")

    if labels:
        print("\nLabels:")
        for file_name, label in labels[:40]:
            print(f"  {label} ({file_name})")
        if len(labels) > 40:
            print(f"  ... {len(labels) - 40} more")

    if characters:
        print("\nCharacters:")
        for file_name, character in characters[:40]:
            print(f"  {character} ({file_name})")
        if len(characters) > 40:
            print(f"  ... {len(characters) - 40} more")

    if menus:
        print("\nFiles containing menu blocks:")
        for file_name in menus:
            print(f"  {file_name}")

    if tab_lines:
        print("\nPotential indentation issue: tabs found")
        for item in tab_lines[:40]:
            print(f"  {item}")
        if len(tab_lines) > 40:
            print(f"  ... {len(tab_lines) - 40} more")

    if cjk_lines and not bundled_fonts and not configured_fonts:
        print("\nPotential localization issue: CJK text found but no bundled or configured font was detected")
        for item in cjk_lines[:10]:
            print(f"  {item}")
        print("  Configure a licensed CJK-capable font; this audit never downloads fonts automatically.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
