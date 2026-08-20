#!/usr/bin/env python3
"""Start the bundled ZJU Learning Tools stdio MCP server."""

from __future__ import annotations

import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "runtime" / "src"))
sys.path.insert(0, str(PLUGIN_ROOT / "vendor" / "lazy-core"))

from zju_learning_tools.server import main


if __name__ == "__main__":
    main()
