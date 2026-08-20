"""Entry point: python -m autocad_mcp"""

# Warm the pure-Python DXF dependency before the MCP request loop starts.
# Importing it lazily inside a Windows stdio tool call can stall the first call.
import ezdxf  # noqa: F401

from autocad_mcp.server import main

main()