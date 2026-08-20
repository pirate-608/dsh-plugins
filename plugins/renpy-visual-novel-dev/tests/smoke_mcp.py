"""Initialize both Ren'Py MCP servers over stdio and verify their tool surfaces."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = PLUGIN_ROOT / "vendor" / "renpy-mcp"


async def _list_tools(params: StdioServerParameters) -> list[str]:
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return sorted(tool.name for tool in result.tools)


async def _smoke_bundled(project: Path, sdk: Path) -> list[str]:
    env = dict(os.environ)
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(VENDOR_ROOT), current_pythonpath) if item
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "renpy_mcp", "--project", str(project), "--sdk", str(sdk), "--tiers", "1,2,3"],
        cwd=str(VENDOR_ROOT),
        env=env,
    )
    names = await _list_tools(params)
    required = {"get_project_overview", "get_media_invariants", "add_image_alias", "get_lint_report"}
    missing = required - set(names)
    if missing:
        raise RuntimeError(f"bundled renpy MCP is missing tools: {sorted(missing)}")
    if len(names) != 78:
        raise RuntimeError(f"bundled Tier 1-3 tool count changed: expected 78, got {len(names)}")
    if "run_python" in names or "run_shell" in names:
        raise RuntimeError("Tier 4 escape tools were unexpectedly enabled")
    return names


async def _smoke_renforge(project: Path) -> list[str]:
    params = StdioServerParameters(
        command="uvx",
        args=["renforge@0.7.0", "serve"],
        cwd=str(project),
        env=dict(os.environ),
    )
    names = await _list_tools(params)
    required = {
        "renforge_info",
        "renforge_launch",
        "renforge_launch_status",
        "renforge_screenshot",
        "renforge_scene_tree",
        "renforge_measure",
        "renforge_stop",
    }
    missing = required - set(names)
    if missing:
        raise RuntimeError(f"RenForge 0.7.0 is missing expected tools: {sorted(missing)}")
    return names


async def run(include_renforge: bool) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        project = root / "sample"
        game = project / "game"
        game.mkdir(parents=True)
        (game / "script.rpy").write_text('label start:\n    "Smoke test"\n    return\n', encoding="utf-8")
        sdk = root / "sdk"
        sdk.mkdir()
        (sdk / ("renpy.exe" if os.name == "nt" else "renpy.sh")).write_text("", encoding="utf-8")

        bundled = await _smoke_bundled(project, sdk)
        result: dict[str, object] = {
            "bundled": {"ok": True, "tool_count": len(bundled)},
            "renforge": {"ok": False, "skipped": True},
        }
        if include_renforge:
            renforge = await _smoke_renforge(project)
            result["renforge"] = {"ok": True, "tool_count": len(renforge), "version": "0.7.0"}
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-renforge", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(asyncio.wait_for(run(args.include_renforge), timeout=180))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
