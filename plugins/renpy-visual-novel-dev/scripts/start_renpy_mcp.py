#!/usr/bin/env python3
"""Start the bundled Ren'Py MCP server for one explicit project root."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _is_project(path: Path) -> bool:
    return path.is_dir() and (path / "game").is_dir()


def _walk_to_project(path: Path) -> Path | None:
    path = path.expanduser().resolve()
    for candidate in (path, *path.parents):
        if _is_project(candidate):
            return candidate
    return None


def _discover_project() -> Path | None:
    raw = os.environ.get("RENPY_PROJECT", "").strip()
    if not raw:
        return None
    return _walk_to_project(Path(raw))


def _sdk_launcher_exists(path: Path) -> bool:
    launcher = "renpy.exe" if os.name == "nt" else "renpy.sh"
    return path.is_dir() and (path / launcher).is_file()


def _sdk_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.glob("sdk-*") if _sdk_launcher_exists(path)),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _discover_sdk(project: Path) -> Path | None:
    explicit = os.environ.get("RENPY_SDK", "").strip()
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if _sdk_launcher_exists(candidate):
            return candidate
    cache_roots = (
        project / ".tools" / "renpy-mcp" / "sdk-cache",
        Path.home() / ".cache" / "renpy-mcp",
        Path.home() / "AppData" / "Local" / "renpy-mcp",
    )
    for root in cache_roots:
        candidates = _sdk_dirs(root)
        if candidates:
            return candidates[0].resolve()
    for root in (Path.home() / "renpy", Path.home() / "Documents" / "RenPy"):
        if root.is_dir():
            candidates = [path for path in root.glob("renpy-*-sdk") if _sdk_launcher_exists(path)]
            if candidates:
                return sorted(candidates, key=lambda path: path.stat().st_mtime)[-1].resolve()
    return None


def main() -> int:
    project = _discover_project()
    if project is None:
        print("renpy-mcp: no active Ren'Py project; set RENPY_PROJECT.", file=sys.stderr)
        return 2
    sdk = _discover_sdk(project)
    if sdk is None:
        print("renpy-mcp: no Ren'Py SDK; set RENPY_SDK or install the project SDK cache.", file=sys.stderr)
        return 2
    plugin_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(plugin_root / "vendor" / "renpy-mcp"))
    from renpy_mcp.__main__ import main as renpy_mcp_main
    sys.argv = [
        "renpy-mcp", "--project", str(project), "--sdk", str(sdk),
        "--tiers", os.environ.get("RENPY_MCP_TIERS", "1,2,3"),
    ]
    return renpy_mcp_main()


if __name__ == "__main__":
    raise SystemExit(main())
