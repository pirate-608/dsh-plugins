from __future__ import annotations

from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from . import __version__
from .config import ServerConfig
from .project.scanner import ProjectIndex
from .tools import lifecycle, tier1_read, tier2_write, tier3_intents, tier4_escape
from .tools.registry import ToolRegistry


def build_server(config: ServerConfig) -> tuple[Server, ToolRegistry]:
    """Construct the MCP server and a registry holding every active tool.

    The index is built lazily on first use and shared across tools; write tools
    (when added) will invalidate it after every successful mutation.
    """
    server = Server("renpy-mcp")
    registry = ToolRegistry()
    index = ProjectIndex(config)

    if 1 in config.tiers:
        tier1_read.register(registry, config, index)
        lifecycle.register(registry, config, index)
    if 2 in config.tiers:
        tier2_write.register(registry, config, index)
    if 3 in config.tiers:
        tier3_intents.register(registry, config, index)
    if 4 in config.tiers:
        tier4_escape.register(registry, config, index)

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return registry.list()

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        return await registry.call(name, arguments)

    return server, registry


async def run_stdio(config: ServerConfig) -> None:
    server, _ = build_server(config)
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="renpy-mcp",
                server_version=__version__,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
