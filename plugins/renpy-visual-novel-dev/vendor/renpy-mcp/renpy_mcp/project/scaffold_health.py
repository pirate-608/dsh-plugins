"""Detect and repair known-bad scaffold leftovers.

Two specific issues bite agents and novices when their freshly-created
project gets BUILT (not just previewed):

1. **`game/guisupport.rpy` imports `gui7`** — the SDK's project template
   ships this GUI-regen helper. At `init 100` it does
   `from gui7.parameters import GuiParameters`, then dynamically inserts
   `<sdk>/launcher/game/` into `sys.path`. That works when the project
   is run via `renpy.sh <project>` (the launcher dir is local), and
   crucially it works during `lint` too — so the developer sees green.
   But a built distribution doesn't ship the launcher; the `gui7`
   import raises `ModuleNotFoundError` and the standalone game crashes
   before its first frame.

2. **`build.name = "gui"` left in `options.rpy`** — the same template
   default. New scaffolds (post the slug-rewrite fix) don't have this
   any more, but projects scaffolded earlier still do. Result:
   distribute names artifacts `gui-X.Y-platform.zip` instead of
   `<project>-X.Y-platform.zip`.

This module surfaces both issues as structured diagnostics and offers
a `repair()` that fixes them in-place. The repair routes through the
standard writer pipeline where it can.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import ServerConfig
from .scaffold import slugify
from .scanner import ProjectIndex
from .writer import WriteRejected, apply_write

GUISUPPORT_REL = "game/guisupport.rpy"
OPTIONS_REL = "game/options.rpy"

# The minimum `guisupport.rpy` the repair leaves on disk. Drops the
# launcher-only `gui7` import block (which crashed built games) but
# preserves the `scale()` helper at `init -100` because the
# SDK-shipped `gui.rpy` calls `gui.scale(...)` 95+ times.
MIN_GUISUPPORT = (
    "# Minimum guisupport.rpy maintained by renpy-mcp's scaffold-health\n"
    "# repair. The original SDK template included a launcher-only\n"
    "# `gui7` import at init 100 that crashed standalone builds. The\n"
    "# `scale()` helper at init -100 is kept because gui.rpy depends\n"
    "# on it.\n"
    "init -100 python in gui:\n"
    "\n"
    "    def scale(n):\n"
    "        return int(n)\n"
)

_BUILD_NAME_RE = re.compile(
    r'^(?P<prefix>define\s+build\.name\s*=\s*)"(?P<name>[^"]*)"(?P<suffix>.*)$',
    re.MULTILINE,
)
_CONFIG_NAME_RE = re.compile(
    r'^define\s+config\.name\s*=\s*_\(\s*"(?P<name>[^"]*)"',
    re.MULTILINE,
)
# Match the actual `gui7` import patterns. Avoids false positives when
# the string `gui7` appears in a comment (including this module's own
# repair output).
_GUI7_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+gui7|import\s+gui7)\b",
    re.MULTILINE,
)


@dataclass(frozen=True)
class ScaffoldIssue:
    rule: str
    severity: str  # "error" | "warning"
    file: str | None
    message: str
    fix_summary: str


def _gui_uses_scale(config: ServerConfig) -> bool:
    """True when `game/gui.rpy` calls `gui.scale(...)` — i.e. depends on
    the helper that the original SDK `guisupport.rpy` defined."""
    gui_path = config.project_root / "game" / "gui.rpy"
    if not gui_path.is_file():
        return False
    try:
        text = gui_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "gui.scale(" in text


def _guisupport_is_minimal(text: str) -> bool:
    """The repair-applied minimum has the scale helper and no gui7 import."""
    return not _GUI7_IMPORT_RE.search(text) and "def scale" in text


def diagnose(config: ServerConfig) -> list[ScaffoldIssue]:
    """Return every known scaffold issue present in the project. Cheap; pure read."""
    issues: list[ScaffoldIssue] = []

    gs = config.project_root / GUISUPPORT_REL
    if gs.is_file():
        try:
            text = gs.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if _GUI7_IMPORT_RE.search(text):
            issues.append(
                ScaffoldIssue(
                    rule="guisupport_imports_gui7",
                    severity="error",
                    file=GUISUPPORT_REL,
                    message=(
                        "`game/guisupport.rpy` imports `gui7`, a Python module that "
                        "exists only in the Ren'Py launcher (`<sdk>/launcher/game/`). "
                        "It works during preview and lint but built distributions "
                        "raise `ModuleNotFoundError: gui7` at startup."
                    ),
                    fix_summary=(
                        "rewrite `game/guisupport.rpy` to keep only the `scale` "
                        "helper at `init -100`"
                    ),
                )
            )
    elif _gui_uses_scale(config):
        # File missing but `gui.rpy` calls `gui.scale(...)` — happens
        # when an over-eager prior repair (or the user) deleted the
        # whole file. Without this helper, `gui.rpy` raises
        # AttributeError at import time and lint, preview, and build
        # all break.
        issues.append(
            ScaffoldIssue(
                rule="guisupport_missing_scale_helper",
                severity="error",
                file=GUISUPPORT_REL,
                message=(
                    "`game/gui.rpy` calls `gui.scale(...)` but `guisupport.rpy` "
                    "is missing. The scale helper must exist or every gui-pixel "
                    "constant fails to evaluate at init time."
                ),
                fix_summary=(
                    "create a minimum `game/guisupport.rpy` defining "
                    "`gui.scale(n)`"
                ),
            )
        )

    options_path = config.project_root / OPTIONS_REL
    if options_path.is_file():
        try:
            text = options_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        m = _BUILD_NAME_RE.search(text)
        if m and m.group("name") == "gui":
            issues.append(
                ScaffoldIssue(
                    rule="build_name_is_gui",
                    severity="warning",
                    file=OPTIONS_REL,
                    message=(
                        '`build.name = "gui"` is the SDK template default. Distributed '
                        "artifacts will be named `gui-<version>-<platform>` instead of "
                        "`<project>-<version>-<platform>`."
                    ),
                    fix_summary='rewrite `build.name` to a slug derived from `config.name`',
                )
            )

    return issues


def repair(config: ServerConfig, index: ProjectIndex) -> dict[str, Any]:
    """Apply every fix `diagnose()` would suggest. Idempotent.

    Returns `{issues, actions}` where `actions` records what was done
    (or attempted but rejected, with the rejection text).
    """
    issues = diagnose(config)
    actions: list[dict[str, Any]] = []

    for issue in issues:
        if issue.rule in ("guisupport_imports_gui7", "guisupport_missing_scale_helper"):
            try:
                result = apply_write(config, index, GUISUPPORT_REL, MIN_GUISUPPORT)
                actions.append(
                    {
                        "rule": issue.rule,
                        "outcome": "rewrote" if issue.rule == "guisupport_imports_gui7" else "created",
                        "file": GUISUPPORT_REL,
                        "diff": result.diff,
                    }
                )
            except WriteRejected as exc:
                actions.append(
                    {
                        "rule": issue.rule,
                        "outcome": "error",
                        "file": GUISUPPORT_REL,
                        "error": str(exc),
                    }
                )
            continue

        if issue.rule == "build_name_is_gui":
            options_path = config.project_root / OPTIONS_REL
            text = options_path.read_text(encoding="utf-8", errors="replace")
            cn = _CONFIG_NAME_RE.search(text)
            project_name = cn.group("name") if cn else config.project_root.name
            safe = slugify(project_name)
            new_text, count = _BUILD_NAME_RE.subn(
                rf'\g<prefix>"{safe}"\g<suffix>', text, count=1
            )
            if not count:
                actions.append(
                    {
                        "rule": issue.rule,
                        "outcome": "skipped",
                        "file": OPTIONS_REL,
                        "error": "could not relocate the build.name line for rewrite",
                    }
                )
                continue
            try:
                result = apply_write(config, index, OPTIONS_REL, new_text)
                actions.append(
                    {
                        "rule": issue.rule,
                        "outcome": "rewrote",
                        "file": OPTIONS_REL,
                        "build_name": safe,
                        "diff": result.diff,
                    }
                )
            except WriteRejected as exc:
                actions.append(
                    {
                        "rule": issue.rule,
                        "outcome": "error",
                        "file": OPTIONS_REL,
                        "error": str(exc),
                    }
                )
            continue

        # Unknown rule — record it so the response stays informative.
        actions.append(
            {
                "rule": issue.rule,
                "outcome": "no-op",
                "error": "no repair handler for this rule",
            }
        )

    return {
        "issues": [
            {
                "rule": i.rule,
                "severity": i.severity,
                "file": i.file,
                "message": i.message,
                "fix_summary": i.fix_summary,
            }
            for i in issues
        ],
        "actions": actions,
    }
