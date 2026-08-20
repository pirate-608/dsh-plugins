from __future__ import annotations

import asyncio
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    env = dict(os.environ)
    env.update(
        {
            "ZOTERO_LOCAL": "true",
            "ZOTERO_MCP_TOOLSETS": "libraries,search-admin,pdf-geometry,discovery",
            "ZOTERO_EMBEDDING_MODEL": "ollama",
            "OLLAMA_EMBEDDING_MODEL": "bge-m3:latest",
            "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
        }
    )
    server = StdioServerParameters(
        command="uvx",
        args=[
            "--from",
            "zotero-mcp-server[semantic,pdf]==0.9.1",
            "zotero-mcp-server",
            "serve",
            "--transport",
            "stdio",
        ],
        env=env,
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.list_tools()

    names = {tool.name for tool in response.tools}
    expected = {
        "zotero_search_items",
        "zotero_get_item_metadata",
        "zotero_get_item_fulltext",
        "zotero_semantic_search",
        "zotero_get_search_database_status",
        "zotero_read_pdf_pages",
        "zotero_find_related_papers",
    }
    missing = sorted(expected - names)
    forbidden_prefixes = ("scite_",)
    forbidden = sorted(name for name in names if name.startswith(forbidden_prefixes))
    if missing or forbidden:
        raise SystemExit(f"tool surface mismatch: missing={missing}, forbidden={forbidden}")
    print(f"Zotero MCP handshake passed with {len(names)} tools.")


if __name__ == "__main__":
    asyncio.run(main())
