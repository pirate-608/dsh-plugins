"""Minimal Ren'Py project scaffolder.

Creates a runnable empty project. Prefers the SDK's own project template
(``<sdk>/gui/``) when available — that template ships the GUI/options/screens
boilerplate every Ren'Py game relies on. Falls back to a tiny hand-written
skeleton when the SDK is missing or its template can't be found, so CI and
tests that don't have the SDK still work.

The server calls this at startup when ``--project`` is omitted (so the index
has something valid to scan) and ``new_project`` calls it to spin up fresh
games on demand. Everything beyond ``label start`` is expected to be added
through the tiered tool surface.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

_MIN_SCRIPT_RPY = """\
# Entry point. The `start` label runs first when the player clicks
# "New Game". Body is intentionally empty — fill it via
# add_dialogue_block(label="start", lines=[...]) or point start at
# your real opening with set_start_target(target="<label>").

label start:
    return
"""

_MIN_OPTIONS_RPY = """\
## Auto-generated options.rpy — edit through update_options_field.

define config.name = _("{name}")
define config.version = "0.1.0"
define gui.show_name = True
define config.has_sound = True
define config.has_music = True
define config.has_voice = True
"""

# Template files we deliberately DO NOT carry over from the SDK template:
#  - cache/: generated at runtime, no point seeding
#  - saves/: runtime state
#  - testcases.rpy: SDK test-harness template, irrelevant to authored games
#  - tl/: empty translation scaffold; Ren'Py makes it on demand
_TEMPLATE_SKIP = {"cache", "saves", "testcases.rpy", "tl"}

_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def slugify(text: str) -> str:
    """Normalize arbitrary text into a project-dir-safe slug.

    Lowercase, ASCII, collapses dashes/spaces/punctuation to underscores.
    Never empty — falls back to ``project``.
    """
    s = text.strip().lower().replace(" ", "_").replace("-", "_")
    s = _SLUG_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "project"


def _sdk_template_game_dir(sdk_root: Path | None) -> Path | None:
    """Return the SDK's project template ``game/`` dir, or None if unavailable."""
    if sdk_root is None:
        return None
    candidate = sdk_root / "gui" / "game"
    return candidate if candidate.is_dir() else None


def scaffold_project(
    root: Path,
    *,
    display_name: str | None = None,
    sdk_root: Path | None = None,
) -> str:
    """Create a minimal runnable Ren'Py project at ``root``.

    Returns a short human-readable summary of what was done (template source
    used, whether the target already existed). Idempotent: never overwrites
    existing files — if the target game dir already has a script.rpy, the
    function leaves it alone.
    """
    game = root / "game"
    already_present = game.is_dir() and (game / "script.rpy").exists()
    game.mkdir(parents=True, exist_ok=True)
    (game / "images").mkdir(exist_ok=True)
    (game / "audio").mkdir(exist_ok=True)

    if already_present:
        return f"project already scaffolded at {root}"

    template = _sdk_template_game_dir(sdk_root)
    if template is not None:
        _copy_template(template, game)
        # The SDK template's script.rpy ships with placeholder dialogue
        # ("You've created a new Ren'Py game.") and a placeholder Eileen
        # character. Both pollute list_characters / read_label until the
        # agent notices and replaces them — which low-tier models often
        # don't. Overwrite with the same minimal stub the no-SDK path
        # uses so a fresh project always starts from a clean `label start`.
        (game / "script.rpy").write_text(_MIN_SCRIPT_RPY, encoding="utf-8")
        # Tweak options.rpy's config.name in-place so the title bar reads
        # the chosen display name, not the SDK's default placeholder.
        _rename_in_options(game / "options.rpy", display_name or root.name)
        # Replace the SDK template's `guisupport.rpy` with the slim
        # version that drops the launcher-only `gui7` import. Without
        # this step, every new project lints and previews fine but
        # crashes at startup as soon as it's distributed. See
        # project/scaffold_health.py for the full story.
        _slim_guisupport(game / "guisupport.rpy")
        return f"scaffolded {root} from SDK template"

    (game / "script.rpy").write_text(_MIN_SCRIPT_RPY, encoding="utf-8")
    (game / "options.rpy").write_text(
        _MIN_OPTIONS_RPY.format(name=display_name or root.name),
        encoding="utf-8",
    )
    return f"scaffolded {root} (minimal skeleton; no SDK template found)"


def _copy_template(src: Path, dst: Path) -> None:
    for child in src.iterdir():
        if child.name in _TEMPLATE_SKIP:
            continue
        target = dst / child.name
        if target.exists():
            continue
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


_CONFIG_NAME_RE = re.compile(
    r"""^(?P<prefix>define\s+config\.name\s*=\s*_\()"[^"]*"(?P<suffix>\).*)$""",
    re.MULTILINE,
)
# Ren'Py's project template ships with `define build.name = "gui"` left
# over from the launcher's own options. Distribute artifacts get named
# after `build.name`, so without this rewrite every new project ends up
# producing `gui-1.0-pc.zip` instead of `<project>-<version>-pc.zip`.
_BUILD_NAME_RE = re.compile(
    r"""^(?P<prefix>define\s+build\.name\s*=\s*)"[^"]*"(?P<suffix>.*)$""",
    re.MULTILINE,
)


def _slim_guisupport(target: Path) -> None:
    """Overwrite (or create) `game/guisupport.rpy` with the minimum the
    SDK-shipped `gui.rpy` actually needs — the `gui.scale` helper at
    `init -100`. Drops the launcher-only `gui7` regen block that
    crashes built distributions.
    """
    # Late import: scaffold_health imports from this module too, so the
    # shared MIN_GUISUPPORT constant lives there. Defer to avoid a
    # circular-import at module load.
    from .scaffold_health import MIN_GUISUPPORT

    target.write_text(MIN_GUISUPPORT, encoding="utf-8")


def _rename_in_options(options_path: Path, new_name: str) -> None:
    if not options_path.is_file():
        return
    text = options_path.read_text(encoding="utf-8")
    escaped = new_name.replace('"', '\\"')
    text, _ = _CONFIG_NAME_RE.subn(
        rf'\g<prefix>"{escaped}"\g<suffix>', text, count=1
    )
    # `build.name` becomes part of `build.directory_name` and the
    # generated artifact filenames. Ren'Py rejects spaces, colons, and
    # semicolons in `build.directory_name`, so we slugify the name here
    # even when the caller's display_name is human-friendly. The original
    # display name still survives via config.name above.
    build_safe = slugify(new_name)
    text, _ = _BUILD_NAME_RE.subn(
        rf'\g<prefix>"{build_safe}"\g<suffix>', text, count=1
    )
    options_path.write_text(text, encoding="utf-8")
