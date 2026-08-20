#!/usr/bin/env python3
"""Enter the user-owned interactive authentication CLI."""

from __future__ import annotations

import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "runtime" / "src"))
sys.path.insert(0, str(PLUGIN_ROOT / "vendor" / "lazy-core"))

from zju_learning_tools.auth_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
