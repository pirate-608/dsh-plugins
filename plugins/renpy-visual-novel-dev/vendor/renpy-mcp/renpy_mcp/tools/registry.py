"""Single dispatch point for all tools across tiers.

The MCP low-level Server only allows one @list_tools and one @call_tool handler
per server, so each tier module pushes its tools into the shared registry and
the server wires the registry to the SDK once in server.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import mcp.types as types

ToolHandler = Callable[[dict[str, Any]], Awaitable[list[types.TextContent]]]

log = logging.getLogger("renpy_mcp.tools")


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def add(self, tool: ToolDef) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool name: {tool.name}")
        self._tools[tool.name] = tool

    def list(self) -> list[types.Tool]:
        return [
            types.Tool(
                name=t.name,
                description=t.description,
                inputSchema=t.input_schema,
            )
            for t in self._tools.values()
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        if name not in self._tools:
            log.warning("unknown tool requested: %s", name)
            raise ValueError(f"unknown tool: {name}")
        log.info("tool call: %s args=%s", name, arguments)
        return await self._tools[name].handler(arguments or {})
