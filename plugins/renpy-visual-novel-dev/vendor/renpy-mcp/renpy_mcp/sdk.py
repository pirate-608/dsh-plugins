"""Subprocess shim around the Ren'Py SDK launcher.

We invoke `renpy.sh <project> <command>` for engine operations the scanner
cannot do itself: lint, force-recompile, build, generate-translations.

Implementation note: uses ``asyncio.create_subprocess_exec`` (argv list, no
shell interpretation) so user-controlled values never reach a shell parser.
"""

from __future__ import annotations

import asyncio
import platform
from dataclasses import dataclass
import tempfile
from pathlib import Path

from .config import sdk_launcher_name


@dataclass(frozen=True)
class SDKResult:
    returncode: int
    stdout: str
    stderr: str


def _sdk_command(sdk_root: Path, project_root: Path, *args: str) -> list[str]:
    """Build an SDK command that is safe to capture through async pipes."""
    if platform.system() == "Windows":
        python = sdk_root / "lib" / "py3-windows-x86_64" / "python.exe"
        renpy_py = sdk_root / "renpy.py"
        if python.is_file() and renpy_py.is_file():
            return [str(python), str(renpy_py), str(project_root), *args]
    return [str(sdk_root / sdk_launcher_name()), str(project_root), *args]


async def run(sdk_root: Path, project_root: Path, *args: str, timeout: float = 120.0) -> SDKResult:
    """Spawn the Ren'Py SDK launcher with the given subcommand argv and capture its output."""
    cmd = _sdk_command(sdk_root, project_root, *args)
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=stdout_file,
            stdin=asyncio.subprocess.DEVNULL,
            stderr=stderr_file,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read()
        stderr = stderr_file.read()
    return SDKResult(
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )


async def run_lint(sdk_root: Path, project_root: Path) -> SDKResult:
    """Invoke Ren'Py's built-in lint over the project."""
    return await run(sdk_root, project_root, "lint")
