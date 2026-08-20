from __future__ import annotations

import platform
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_TIERS = frozenset({1, 2, 3})
DEFAULT_GAMES_SUBDIR = "games"
DEFAULT_PROJECT_SLUG = "default"


def sdk_launcher_name() -> str:
    """Return the SDK launcher script appropriate for the current OS."""
    return "renpy.exe" if platform.system() == "Windows" else "renpy.sh"


@dataclass
class ServerConfig:
    """Runtime configuration for the MCP server.

    ``project_root`` is mutable so ``new_project`` can rebind the session to
    a newly scaffolded project without tearing down the server. Everything
    else is set at startup and stays put. ``games_root`` is the directory
    under which ``new_project`` drops new projects by default — typically
    ``<cwd>/games/``.
    """

    project_root: Path
    sdk_root: Path
    tiers: frozenset[int] = field(default_factory=lambda: DEFAULT_TIERS)
    games_root: Path | None = None

    @property
    def game_dir(self) -> Path:
        return self.project_root / "game"

    @property
    def sdk_launcher(self) -> Path:
        return self.sdk_root / sdk_launcher_name()

    def is_bound(self) -> bool:
        return self.project_root.is_dir() and self.game_dir.is_dir()

    def bind_project(self, new_root: Path) -> None:
        """Switch the session to a new project root. Caller handles index refresh."""
        self.project_root = new_root.resolve()

    def validate(self) -> None:
        if not self.project_root.is_dir():
            raise ValueError(f"project root does not exist: {self.project_root}")
        if not self.game_dir.is_dir():
            raise ValueError(
                f"project root is not a Ren'Py project (no game/ subdir): {self.project_root}"
            )
        if not self.sdk_launcher.is_file():
            raise ValueError(
                f"SDK root missing launcher `{sdk_launcher_name()}`: {self.sdk_root}"
            )
