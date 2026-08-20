"""Lifecycle tools — launch/stop/inspect long-running SDK subprocesses,
plus iteration helpers (`warp_to`, `set_drafting_mode`).

These tools manage processes and small auto-generated `.rpy` files that
exist only to support iteration. They live in this module rather than
in a Tier 2/3 write tier because the user thinks of them as "things I
toggle while iterating," not "things I author into the game" — same
mental model as `launch_preview` / `stop_preview`.

State (the running preview's process handle, the warp-temp-file flag)
lives module-local. Only one preview can be running per server instance
— `warp_to` and `launch_preview` both refuse if the slot is occupied.

Safety: subprocess spawns use the asyncio argv-list API (no shell
interpretation), so caller-supplied paths never reach a shell parser.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
import signal
import time
from pathlib import Path
from typing import Any

import mcp.types as types

from .. import sdk as renpy_sdk
from ..config import ServerConfig, sdk_launcher_name
from ..project.asset_refs import collect_missing_image_refs
from ..project import scaffold_health
from ..project.scanner import ProjectIndex
from ..project.writer import WriteRejected, apply_write, delete_file
from ._shared import quote
from .registry import ToolDef, ToolRegistry

log = logging.getLogger("renpy_mcp.lifecycle")

# Auto-generated .rpy files that prop up the iteration loop. Both live
# under `game/` so Ren'Py picks them up; both are created and removed by
# tools in this module.
_WARP_TEMP_REL = "game/_ide_after_warp.rpy"
_DRAFTING_REL = "game/_ide_drafting.rpy"
_AFTER_WARP_LABEL = "after_warp"

_preview_proc: asyncio.subprocess.Process | None = None
_warp_temp_active: bool = False
_atexit_registered = False


def _terminate_preview_on_exit() -> None:
    """Best-effort cleanup if the MCP server exits while a preview is alive.

    Uses raw ``os.kill`` (not the asyncio Process API) because by atexit
    time the event loop is gone and ``proc.terminate()`` would no-op or
    raise. ProcessLookupError is benign — the process already exited.
    """
    global _preview_proc
    if _preview_proc is None or _preview_proc.returncode is not None:
        return
    pid = _preview_proc.pid
    try:
        os.kill(pid, signal.SIGTERM)
        log.info("atexit: SIGTERM sent to preview pid=%d", pid)
    except ProcessLookupError:
        pass
    except OSError as exc:
        log.warning("atexit: failed to terminate preview pid=%d: %s", pid, exc)


def register(registry: ToolRegistry, config: ServerConfig, index: ProjectIndex) -> None:
    global _atexit_registered
    if not _atexit_registered:
        atexit.register(_terminate_preview_on_exit)
        _atexit_registered = True
    registry.add(_launch_preview(config))
    registry.add(_stop_preview(config))
    registry.add(_get_preview_status())
    registry.add(_warp_to(config, index))
    registry.add(_set_drafting_mode(config, index))
    registry.add(_generate_translation_scaffolding(config, index))
    registry.add(_build_distribution(config))


def _launch_preview(config: ServerConfig) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        global _preview_proc
        if _preview_proc is not None and _preview_proc.returncode is None:
            return _ok({"already_running": True, "pid": _preview_proc.pid})

        cmd = [str(config.sdk_root / sdk_launcher_name()), str(config.project_root)]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        _preview_proc = proc
        return _ok({"started": True, "pid": proc.pid, "command": cmd})

    return ToolDef(
        name="launch_preview",
        description=(
            "Launch the Ren'Py SDK against the project to play the game in a "
            "window. Returns immediately; the player closes the window when "
            "done. Refuses if a preview is already running — call `stop_preview` "
            "first or use `get_preview_status` to inspect."
        ),
        input_schema=schema,
        handler=handler,
    )


def _stop_preview(config: ServerConfig) -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        global _preview_proc, _warp_temp_active
        if _preview_proc is None or _preview_proc.returncode is not None:
            # Nothing alive to terminate; still scrub a leftover warp temp
            # so a crashed preview doesn't strand it across server restarts.
            warp_cleaned = _maybe_remove_warp_temp(config)
            _warp_temp_active = False
            return _ok({"running": False, "warp_temp_removed": warp_cleaned})
        pid = _preview_proc.pid
        _preview_proc.terminate()
        try:
            await asyncio.wait_for(_preview_proc.wait(), timeout=5.0)
            forced = False
        except asyncio.TimeoutError:
            _preview_proc.kill()
            await _preview_proc.wait()
            forced = True
        rc = _preview_proc.returncode
        _preview_proc = None
        # Clean up the after-warp temp file once the preview is actually down.
        warp_cleaned = False
        if _warp_temp_active:
            warp_cleaned = _maybe_remove_warp_temp(config)
            _warp_temp_active = False
        return _ok(
            {
                "stopped": True,
                "pid": pid,
                "exit_code": rc,
                "force_killed": forced,
                "warp_temp_removed": warp_cleaned,
            }
        )

    return ToolDef(
        name="stop_preview",
        description=(
            "Terminate the running Ren'Py preview. Sends SIGTERM first; "
            "SIGKILL if the process hasn't exited within 5 seconds. Safe to "
            "call when nothing is running (returns running=false). If the "
            "preview was started via `warp_to`, also removes the temporary "
            "`game/_ide_after_warp.rpy` written for that warp."
        ),
        input_schema=schema,
        handler=handler,
    )


def _get_preview_status() -> ToolDef:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def handler(_arguments: dict[str, Any]) -> list[types.TextContent]:
        global _preview_proc
        if _preview_proc is None:
            return _ok({"running": False})
        if _preview_proc.returncode is None:
            return _ok(
                {
                    "running": True,
                    "pid": _preview_proc.pid,
                    "warp_active": _warp_temp_active,
                }
            )
        rc = _preview_proc.returncode
        pid = _preview_proc.pid
        _preview_proc = None
        return _ok({"running": False, "last_pid": pid, "last_exit_code": rc})

    return ToolDef(
        name="get_preview_status",
        description=(
            "Report whether a Ren'Py preview is running. When idle and the "
            "previous run exited, returns the last PID and exit code so the "
            "caller can detect crashes. While running, also reports "
            "`warp_active` (true when started via `warp_to`)."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- warp_to ------------------------------------------------------------


def _warp_to(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "label": {
                "type": "string",
                "description": "Label name to warp into.",
            },
            "overrides": {
                "type": "object",
                "description": (
                    "Optional variable overrides applied via the `after_warp` "
                    "hook before the label runs. Keys must be valid Python "
                    "identifiers; values may be string, integer, float, "
                    "boolean, or null. Strings are quoted and escaped for "
                    "Ren'Py automatically."
                ),
                "additionalProperties": True,
            },
        },
        "required": ["label"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        global _preview_proc, _warp_temp_active

        label_name: str = arguments["label"]
        overrides: dict[str, Any] = arguments.get("overrides") or {}
        if not isinstance(overrides, dict):
            return _err("overrides must be an object mapping name to value")

        snap = index.snapshot()
        if not any(l.name == label_name for l in snap.labels):
            return _err(f"no such label: {label_name}")

        # Refuse to clobber an existing warp temp — usually means a prior
        # warp died without cleanup. Surface it so the agent sees the
        # state instead of silently overwriting.
        if (config.project_root / _WARP_TEMP_REL).is_file():
            return _err(
                f"`{_WARP_TEMP_REL}` already exists; call `stop_preview` to clean it up first"
            )

        # If the project already defines a `label after_warp:`, defer to it
        # — colliding would either overwrite user logic or generate a
        # duplicate label name (caught by the writer, but the diagnostic
        # would be confusing).
        if any(l.name == _AFTER_WARP_LABEL for l in snap.labels):
            return _err(
                "project already defines `label after_warp:` — `warp_to` "
                "cannot install its override hook without colliding. "
                "Remove or rename the user-defined `after_warp` first."
            )

        if _preview_proc is not None and _preview_proc.returncode is None:
            return _err(
                f"preview is already running (pid={_preview_proc.pid}); call "
                "`stop_preview` before warping"
            )

        # Format override lines.
        override_lines: list[str] = []
        for name, value in overrides.items():
            if not isinstance(name, str) or not name.isidentifier():
                return _err(f"override name `{name}` is not a valid Python identifier")
            try:
                rendered = _format_override_value(value)
            except ValueError as exc:
                return _err(str(exc))
            override_lines.append(f"    $ {name} = {rendered}")

        body = ["# Auto-generated by warp_to. Removed by stop_preview."]
        body.append(f"label {_AFTER_WARP_LABEL}:")
        if override_lines:
            body.extend(override_lines)
        body.append("    return")
        body.append("")
        new_text = "\n".join(body)

        try:
            apply_write(config, index, _WARP_TEMP_REL, new_text)
        except WriteRejected as rejection:
            return _err(str(rejection))

        cmd = [
            str(config.sdk_root / sdk_launcher_name()),
            str(config.project_root),
            "--warp",
            label_name,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        _preview_proc = proc
        _warp_temp_active = True
        return _ok(
            {
                "warped": True,
                "label": label_name,
                "overrides": overrides,
                "pid": proc.pid,
                "command": cmd,
                "temp_file": _WARP_TEMP_REL,
            }
        )

    return ToolDef(
        name="warp_to",
        description=(
            "Launch the Ren'Py preview starting at a specific label, optionally "
            "applying variable overrides via Ren'Py's `after_warp` hook. Use "
            "this to iterate on a mid-game scene without playing through every "
            "preceding scene. The tool writes a temporary "
            "`game/_ide_after_warp.rpy` containing `label after_warp: $ var = "
            "value` lines for the overrides; that file is removed when "
            "`stop_preview` is called. Refuses if a preview is already "
            "running, if the temp file already exists, or if the project "
            "already defines a user `label after_warp:`."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- set_drafting_mode --------------------------------------------------


def _set_drafting_mode(config: ServerConfig, index: ProjectIndex) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "on": {
                "type": "boolean",
                "description": (
                    "When true, write `game/_ide_drafting.rpy` with fallback "
                    "`image NAME = Solid(\"#444\")` definitions for every "
                    "missing image reference detected in the project. When "
                    "false, remove the file."
                ),
            },
        },
        "required": ["on"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        on = bool(arguments["on"])
        target = config.project_root / _DRAFTING_REL

        if not on:
            if not target.is_file():
                return _ok(
                    {
                        "drafting": False,
                        "summary": "drafting mode already off",
                        "file": _DRAFTING_REL,
                        "removed": False,
                    }
                )
            try:
                result = delete_file(config, index, _DRAFTING_REL)
            except WriteRejected as rejection:
                return _err(str(rejection))
            return _ok(
                {
                    "drafting": False,
                    "summary": "drafting mode off",
                    "file": _DRAFTING_REL,
                    "removed": True,
                    "diff": result.diff,
                }
            )

        # Drafting on: walk missing image refs and emit fallback aliases.
        missing = collect_missing_image_refs(config, index)
        names: list[str] = []
        seen: set[str] = set()
        for ref in missing:
            if ref["name"] in seen:
                continue
            seen.add(ref["name"])
            names.append(ref["name"])

        body = ["# Auto-generated by set_drafting_mode. Removed when drafting mode is off."]
        body.append("# Each fallback is a Solid color so missing assets render as a tile.")
        body.append("")
        for name in names:
            body.append(f"image {name} = Solid(\"#444444\")")
        body.append("")
        new_text = "\n".join(body)

        try:
            apply_write(config, index, _DRAFTING_REL, new_text)
        except WriteRejected as rejection:
            return _err(str(rejection))
        return _ok(
            {
                "drafting": True,
                "summary": f"drafting mode on; {len(names)} fallback(s) registered",
                "file": _DRAFTING_REL,
                "fallbacks": names,
            }
        )

    return ToolDef(
        name="set_drafting_mode",
        description=(
            "Toggle a project-local flag that injects fallback `image NAME = "
            "Solid(...)` definitions for every missing image reference, so "
            "the game runs while assets are still being generated. Backed by "
            "`game/_ide_drafting.rpy`, written when `on=true` and removed "
            "when `on=false`. The same scanning logic that powers "
            "`find_missing_assets` decides which images need fallbacks, so "
            "the diagnostic and the drafting list always agree. Audio "
            "fallbacks are not generated — silence is rarely the right "
            "iteration substitute."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- helpers ------------------------------------------------------------


def _format_override_value(value: Any) -> str:
    """Render a Python value as a Ren'Py expression for `$ var = ...`."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        # bool is a subclass of int — handle BEFORE the int branch.
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return quote(value)
    raise ValueError(
        f"unsupported override value type: {type(value).__name__}; "
        "must be string, int, float, bool, or null"
    )


def _maybe_remove_warp_temp(config: ServerConfig) -> bool:
    """Remove `_ide_after_warp.rpy` if present. Returns True iff removed."""
    target = config.project_root / _WARP_TEMP_REL
    if not target.is_file():
        return False
    try:
        target.unlink()
        # Remove the .rpyc shadow if Ren'Py wrote one.
        for ext in (".rpyc", ".rpyc.bak"):
            shadow = target.with_suffix(ext)
            if shadow.is_file():
                shadow.unlink()
        return True
    except OSError as exc:
        log.warning("failed to remove %s: %s", _WARP_TEMP_REL, exc)
        return False


# ---------- generate_translation_scaffolding -----------------------------------
#
# Wraps `renpy.sh <project> translate <language>`. Ren'Py is the one
# writing the new files under `game/tl/<language>/`; our writer pipeline
# is bypassed for the same reason `new_project` is — there are no
# existing `.rpy` to diff against, and the SDK's emission is the source
# of truth. Documented as the third sanctioned non-`apply_write` path
# in DESIGN.md §3.


def _generate_translation_scaffolding(
    config: ServerConfig, index: ProjectIndex
) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "description": "Language identifier (e.g. `spanish`, `japanese`).",
            },
        },
        "required": ["language"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        language: str = arguments["language"]
        if not language.replace("_", "").replace("-", "").isalnum():
            return _err(
                f"language `{language}` must be alphanumeric (with - or _ "
                "allowed); rejected to keep it shell-safe"
            )
        try:
            result = await renpy_sdk.run(
                config.sdk_root, config.project_root, "translate", language
            )
        except Exception as exc:  # noqa: BLE001 — surface as a structured error
            return _err(f"failed to invoke renpy.sh translate: {exc}")
        # Ren'Py wrote new .rpy files; re-snapshot the index so subsequent
        # reads (find_stale_translations, get_translation_coverage) see them.
        index.refresh()
        return _ok(
            {
                "language": language,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )

    return ToolDef(
        name="generate_translation_scaffolding",
        description=(
            "Wrap `renpy.sh <project> translate <language>` to generate "
            "translation skeleton files under `game/tl/<language>/`. "
            "Ren'Py emits one `translate <language> ...:` block per "
            "translatable string; afterwards `find_stale_translations` "
            "shows which still need human work. The index is refreshed so "
            "the new files appear in subsequent reads. SDK-gated; requires "
            "the Ren'Py launcher to be reachable."
        ),
        input_schema=schema,
        handler=handler,
    )


# ---------- build_distribution -------------------------------------------------


def _build_distribution(config: ServerConfig) -> ToolDef:
    schema = {
        "type": "object",
        "properties": {
            "targets": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
                "description": (
                    "Distribution targets (e.g. `[\"pc\", \"mac\", \"linux\"]`). "
                    "Each becomes a separate `--package <name>` flag."
                ),
            },
            "destination": {
                "type": "string",
                "description": (
                    "Optional output directory for the built artifacts. "
                    "When omitted, Ren'Py defaults to "
                    "`<project_parent>/<name>-<version>-dists/`. "
                    "When given, the path is created if it doesn't exist."
                ),
            },
        },
        "required": ["targets"],
        "additionalProperties": False,
    }

    async def handler(arguments: dict[str, Any]) -> list[types.TextContent]:
        targets: list[str] = arguments["targets"]
        if not isinstance(targets, list) or not targets:
            return _err("targets must be a non-empty list of package names")
        cleaned: list[str] = []
        for t in targets:
            if not isinstance(t, str) or not t.replace("_", "").replace("-", "").isalnum():
                return _err(
                    f"target `{t}` must be alphanumeric (- and _ allowed); "
                    "rejected to keep `--package=` shell-safe"
                )
            cleaned.append(t)

        # Ren'Py's distribute command is implemented IN THE LAUNCHER, not in
        # core. The argv shape is `renpy.sh <launcher_dir> distribute
        # <project_dir> [--package X --package Y] [--destination=<path>]`.
        launcher_dir = config.sdk_root / "launcher"
        extra_args: list[str] = []
        for t in cleaned:
            extra_args.extend(["--package", t])

        # Resolve and validate the destination. Default behavior (no
        # `--destination`) lands artifacts at
        # `<project_parent>/<name>-<version>-dists/` — already "next to
        # the source folder." Caller can override.
        destination_arg: str | None = arguments.get("destination")
        resolved_dest: Path | None = None
        if destination_arg is not None:
            if not isinstance(destination_arg, str) or not destination_arg.strip():
                return _err("destination must be a non-empty path string")
            resolved_dest = Path(destination_arg).expanduser().resolve()
            try:
                resolved_dest.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return _err(f"could not create destination `{resolved_dest}`: {exc}")
            extra_args.extend(["--destination", str(resolved_dest)])

        # Record build-start time so we can recognize artifacts whose
        # mtime advanced during this run. Path-identity snapshots fail
        # the common case where Ren'Py OVERWRITES an existing artifact
        # with the same filename — which is exactly what happens on
        # repeat builds with no destination override.
        snapshot_root = (
            resolved_dest
            if resolved_dest is not None
            else config.project_root.parent
        )
        # Subtract a 1 second tolerance so filesystems with second-level
        # timestamp granularity don't lose the boundary.
        build_started_at = time.time() - 1.0

        try:
            # `distribute` can take a while on large projects; allow up to 10
            # minutes. Same shape as `run_lint` but with a longer ceiling.
            result = await renpy_sdk.run(
                config.sdk_root,
                launcher_dir,
                "distribute",
                str(config.project_root),
                *extra_args,
                timeout=600.0,
            )
        except Exception as exc:  # noqa: BLE001
            return _err(f"failed to invoke renpy.sh distribute: {exc}")

        # Surface every .zip / .bz2 inside the snapshot root whose
        # mtime advanced after the build started. This catches both
        # newly-created and freshly-overwritten artifacts.
        artifacts: list[str] = []
        if snapshot_root.is_dir():
            for p in snapshot_root.rglob("*"):
                if not p.is_file() or p.suffix.lower() not in (".zip", ".bz2"):
                    continue
                try:
                    if p.stat().st_mtime >= build_started_at:
                        artifacts.append(str(p.resolve()))
                except OSError:
                    continue

        # Scaffold-health pre-flight: a guisupport.rpy that imports
        # `gui7` will crash the artifact at startup even though lint and
        # the build itself succeed. Surface those issues so the user
        # knows BEFORE they try to run the artifact.
        scaffold_issues = [
            {
                "rule": i.rule,
                "severity": i.severity,
                "file": i.file,
                "message": i.message,
                "fix_summary": i.fix_summary,
            }
            for i in scaffold_health.diagnose(config)
        ]

        return _ok(
            {
                "targets": cleaned,
                "destination": str(resolved_dest) if resolved_dest else None,
                "default_destination": str(
                    config.project_root.parent.resolve()
                ),
                "artifacts": sorted(artifacts),
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "scaffold_warnings": scaffold_issues,
            }
        )

    return ToolDef(
        name="build_distribution",
        description=(
            "Wrap Ren'Py's `distribute` command to produce platform-specific "
            "build artifacts. `targets` is a list of Ren'Py package names "
            "(`pc`, `mac`, `linux`, `web`, `steam`, etc.). Optional "
            "`destination` overrides where the artifacts land — defaults to "
            "`<project_parent>/<name>-<version>-dists/` (next to the source "
            "folder). Returns the list of artifact paths produced. Slow — "
            "can take minutes on large projects. SDK-gated."
        ),
        input_schema=schema,
        handler=handler,
    )


def _err(message: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps({"error": message}, indent=2, ensure_ascii=False))]


def _ok(payload: Any) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False))]
