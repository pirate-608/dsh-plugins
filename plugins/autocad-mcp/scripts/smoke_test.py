"""Exercise the bundled MCP server through stdio using the headless backend."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def text_payload(result) -> dict:
    for item in result.content:
        text = getattr(item, "text", None)
        if text:
            return json.loads(text)
    raise RuntimeError("MCP result did not contain JSON text")


async def run(output: Path) -> None:
    plugin_root = Path(__file__).resolve().parent.parent
    project = plugin_root / "vendor" / "autocad-mcp"
    print("smoke: prepare", flush=True)
    env = dict(os.environ)
    env.update({"AUTOCAD_MCP_BACKEND": "ezdxf", "AUTOCAD_MCP_ONLY_TEXT": "true"})
    server_python = project / ".venv" / "Scripts" / "python.exe"
    params = StdioServerParameters(
        command=str(server_python),
        args=["-m", "autocad_mcp"],
        cwd=str(project),
        env=env,
    )

    print("smoke: start stdio", flush=True)
    async with stdio_client(params) as (read, write):
        print("smoke: stdio connected", flush=True)
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("smoke: initialized", flush=True)
            tools = await session.list_tools()
            print("smoke: tools listed", flush=True)
            names = {tool.name for tool in tools.tools}
            expected = {"drawing", "entity", "layer", "block", "annotation", "pid", "view", "system"}
            if names != expected:
                raise RuntimeError(f"Unexpected tool set: {sorted(names)}")

            status = text_payload(await session.call_tool("system", {"operation": "status"}))
            print("smoke: status returned", flush=True)
            backend = status.get("payload", {}).get("backend")
            if backend != "ezdxf":
                raise RuntimeError(f"Expected ezdxf backend, got {backend!r}")

            await session.call_tool("drawing", {"operation": "create", "data": {"name": "smoke"}})
            await session.call_tool("layer", {"operation": "create", "data": {"name": "TEST", "color": 3}})
            await session.call_tool("entity", {
                "operation": "create_rectangle", "x1": 0, "y1": 0,
                "x2": 100, "y2": 60, "layer": "TEST"
            })
            await session.call_tool("entity", {
                "operation": "create_circle", "layer": "TEST",
                "data": {"cx": 50, "cy": 30, "radius": 10}
            })
            await session.call_tool("drawing", {
                "operation": "save_as_dxf", "data": {"path": str(output)}
            })
            info = text_payload(await session.call_tool("drawing", {"operation": "info"}))
            print("smoke: drawing saved", flush=True)

    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(f"DXF output was not created: {output}")

    print(json.dumps({
        "ok": True,
        "backend": backend,
        "tools": sorted(names),
        "drawing": info,
        "output": str(output),
        "bytes": output.stat().st_size,
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(asyncio.wait_for(run(args.output.resolve()), timeout=45))


if __name__ == "__main__":
    main()
