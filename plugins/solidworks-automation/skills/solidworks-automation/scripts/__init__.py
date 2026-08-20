"""
SolidWorks Automation Python helper package.
"""

from .sw_connect import connect_solidworks, deg, mm, new_document, open_document, save_document
from .sw_macro_guard import build_prompt, generate_macro_with_guard, validate_vba_macro
from .sw_preflight import run_preflight
from .sw_session import SolidWorksSession, session

__all__ = [
    "SolidWorksSession",
    "build_prompt",
    "connect_solidworks",
    "deg",
    "generate_macro_with_guard",
    "mm",
    "new_document",
    "open_document",
    "run_preflight",
    "save_document",
    "session",
    "validate_vba_macro",
]
