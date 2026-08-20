#!/usr/bin/env python3
"""Check local LaTeX readiness for DSH LaTeX workflows."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


COMMON_MIKTEX_DIRS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64",
    Path(os.environ.get("PROGRAMFILES", "")) / "MiKTeX" / "miktex" / "bin" / "x64",
    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "MiKTeX" / "miktex" / "bin",
]

FULL_FEATURE_MARKERS = {
    "latexmkrc",
    ".latexmkrc",
    "makefile",
    "tectonic.toml",
    "Tectonic.toml",
}

FULL_FEATURE_PATTERNS = [
    "\\addbibresource",
    "\\bibliography",
    "\\printindex",
    "\\makeglossaries",
    "\\usepackage{minted}",
    "\\documentclass{beamer}",
]


def command_path(command: str, extra_paths: list[Path] | None = None) -> str | None:
    search_path = os.environ.get("PATH", "")
    if extra_paths:
        prefix = os.pathsep.join(str(path) for path in extra_paths if path.is_dir())
        search_path = prefix + os.pathsep + search_path if prefix else search_path
    return shutil.which(command, path=search_path)


def detect_miktex_dir() -> str | None:
    pdflatex = command_path("pdflatex")
    if pdflatex and "miktex" in pdflatex.lower():
        return str(Path(pdflatex).resolve().parent)
    for candidate in COMMON_MIKTEX_DIRS:
        if (candidate / "pdflatex.exe").is_file() or (candidate / "latexmk.exe").is_file():
            return str(candidate)
    return None


def find_tex_roots(project: Path) -> list[str]:
    roots: list[str] = []
    for tex_file in sorted(project.rglob("*.tex")):
        try:
            text = tex_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "\\documentclass" in text:
            roots.append(str(tex_file.relative_to(project)))
    return roots


def project_needs_full_toolchain(project: Path) -> bool:
    lower_names = {path.name.lower() for path in project.iterdir()} if project.is_dir() else set()
    if any(marker.lower() in lower_names for marker in FULL_FEATURE_MARKERS):
        return True
    for tex_file in project.rglob("*.tex"):
        try:
            text = tex_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(pattern in text for pattern in FULL_FEATURE_PATTERNS):
            return True
    return False


def main() -> int:
    project = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    miktex_dir_raw = detect_miktex_dir()
    miktex_paths = [Path(miktex_dir_raw)] if miktex_dir_raw else []
    tools = {
        "tectonic": command_path("tectonic"),
        "latexmk": command_path("latexmk", miktex_paths),
        "pdflatex": command_path("pdflatex", miktex_paths),
        "xelatex": command_path("xelatex", miktex_paths),
        "lualatex": command_path("lualatex", miktex_paths),
        "bibtex": command_path("bibtex", miktex_paths),
        "biber": command_path("biber", miktex_paths),
        "makeindex": command_path("makeindex", miktex_paths),
        "makeglossaries": command_path("makeglossaries", miktex_paths),
    }
    tex_roots = find_tex_roots(project) if project.is_dir() else []
    needs_full = project_needs_full_toolchain(project) if project.is_dir() else False
    miktex_ready = bool(miktex_dir_raw and (tools["latexmk"] or tools["pdflatex"] or tools["xelatex"] or tools["lualatex"]))
    tectonic_ready = bool(tools["tectonic"])
    if not needs_full and tectonic_ready:
        status = "ready-with-tectonic"
    elif miktex_ready:
        status = "ready-with-miktex"
    elif needs_full:
        status = "needs-miktex-path"
    else:
        status = "missing-latex-toolchain"

    checked_paths = [str(path) for path in COMMON_MIKTEX_DIRS if str(path)]
    payload = {
        "project": str(project),
        "status": status,
        "tex_roots": tex_roots,
        "needs_full_toolchain": needs_full,
        "tectonic": tools["tectonic"],
        "miktex_dir": miktex_dir_raw,
        "tools": tools,
        "checked_miktex_paths": checked_paths,
    }
    print(json.dumps(payload, indent=2))
    return 0 if status in {"ready-with-tectonic", "ready-with-miktex"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
