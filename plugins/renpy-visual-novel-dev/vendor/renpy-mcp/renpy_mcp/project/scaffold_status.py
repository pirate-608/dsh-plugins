"""Heuristic "is this scaffold still fresh?" report.

Tells an agent — at a glance — what's authored vs. what's still SDK-template
placeholder. Complements ``scaffold_health.diagnose()``: that catches
distribution-breaking template leftovers; this one catches *content*
leftovers (Eileen's placeholder dialogue, untouched route stubs, the
default project name) that lint won't flag but that ship visibly broken
games.

Read-only; never mutates the project. Agents typically call this between
``new_project`` and the first authoring step, or right before
``launch_preview`` to confirm the wiring is in place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import DEFAULT_PROJECT_SLUG, ServerConfig
from . import scaffold_health
from .scanner import ProjectIndex

# Phrases that ship with the SDK's project template's `script.rpy`.
# Regenerated scaffolds use the minimal stub which has none of these.
_SDK_PLACEHOLDER_PHRASES = (
    "You've created a new Ren'Py game",
    "Once you add a story, pictures, and music",
    "show eileen happy",
    'define e = Character("Eileen"',
    'image bg room = ',
)

# Bodies that authoring tools emit when they want to mark a label
# "stub me later". An agent who scaffolds a route and then tells the
# user "I'm done" without filling these is a common failure mode.
_TODO_BODY_RE = re.compile(r"^\s*#\s*TODO\b", re.MULTILINE)
_PLACEHOLDER_BODY_RE = re.compile(r"^\s*#\s*placeholder\b", re.MULTILINE | re.IGNORECASE)


@dataclass(frozen=True)
class StatusFinding:
    rule: str
    severity: str  # "error" | "warning" | "info"
    message: str
    fix_hint: str  # which tool the agent should call to clear the issue


def evaluate(config: ServerConfig, index: ProjectIndex) -> dict[str, Any]:
    """Return a structured summary of how "scaffolded" the project still is.

    Findings are non-blocking by design — the goal is to nudge, not gate.
    A project with zero findings is one whose `start` label is wired,
    whose name has been customized, and which carries no SDK template
    placeholder dialogue.
    """
    findings: list[StatusFinding] = []
    snap = index.snapshot()
    is_default_slug = config.project_root.name == DEFAULT_PROJECT_SLUG

    # ---- start label state ----------------------------------------------------
    start_state = _classify_start(config, snap)
    findings.extend(start_state["findings"])

    # ---- SDK placeholder dialogue --------------------------------------------
    placeholder_files = _scan_for_sdk_placeholders(config)
    for rel, phrase in placeholder_files:
        findings.append(
            StatusFinding(
                rule="sdk_placeholder_content",
                severity="warning",
                message=(
                    f"`{rel}` still contains the SDK template's placeholder "
                    f"phrase {phrase!r}. Rewrite via add_dialogue_block / "
                    "delete_label / set_start_target."
                ),
                fix_hint="add_dialogue_block / delete_label / set_start_target",
            )
        )

    # Eileen the SDK placeholder character ships with the template. New
    # projects (post script.rpy overwrite) won't have her, but agents
    # might add her by accident.
    eileen = next((c for c in snap.characters if c.var_name == "e" and (c.display_name or "") == "Eileen"), None)
    if eileen is not None:
        findings.append(
            StatusFinding(
                rule="placeholder_character_eileen",
                severity="info",
                message=(
                    'Character `e = Character("Eileen")` is the SDK template '
                    "default. If your story doesn't include Eileen, redefine "
                    "her with `update_character` or remove via tier-4 escape."
                ),
                fix_hint="update_character or apply_unified_diff",
            )
        )

    # ---- TODO / placeholder route bodies -------------------------------------
    todo_labels = _scan_label_todos(config, snap)
    for label_name, file_rel in todo_labels:
        findings.append(
            StatusFinding(
                rule="todo_label_body",
                severity="info",
                message=(
                    f"Label `{label_name}` body looks like an unfilled "
                    "scaffold (TODO / placeholder comment). Fill it via "
                    "create_scene / add_dialogue_block before previewing."
                ),
                fix_hint="add_dialogue_block / create_scene",
            )
        )
        # Don't flood the response if the agent ran create_route("foo", [...20 nodes]).
        if len(findings) > 30:
            break

    # ---- project name still default-y ----------------------------------------
    config_name = _read_config_name(config)
    if config_name is not None and config_name.strip().lower() in ("the question", "my game", "untitled"):
        findings.append(
            StatusFinding(
                rule="default_project_name",
                severity="info",
                message=(
                    f"`config.name` is still `{config_name}` — the SDK "
                    "template default. Update via update_options_field("
                    'field="config.name", value="\\"<your title>\\"").'
                ),
                fix_hint='update_options_field(field="config.name", ...)',
            )
        )
    if is_default_slug:
        findings.append(
            StatusFinding(
                rule="auto_scaffolded_default_project",
                severity="info",
                message=(
                    "Session is bound to the auto-scaffolded `games/default/` "
                    "fallback. Call `new_project(name=...)` to branch into a "
                    "named subfolder before authoring."
                ),
                fix_hint="new_project",
            )
        )

    # ---- distribution-breaking leftovers from scaffold_health ----------------
    health_issues = scaffold_health.diagnose(config)
    for issue in health_issues:
        findings.append(
            StatusFinding(
                rule=issue.rule,
                severity=issue.severity,
                message=issue.message,
                fix_hint=issue.fix_summary,
            )
        )

    fresh = (
        not findings
        and start_state["wired"]
        and not is_default_slug
    )
    return {
        "fresh": fresh,
        "is_default_project": is_default_slug,
        "start_label": start_state["summary"],
        "findings": [
            {
                "rule": f.rule,
                "severity": f.severity,
                "message": f.message,
                "fix_hint": f.fix_hint,
            }
            for f in findings
        ],
        "findings_count": len(findings),
        "label_count": len(snap.labels),
        "character_count": len(snap.characters),
        "image_count": len(snap.images),
    }


# ---------- helpers -------------------------------------------------------------


def _classify_start(config: ServerConfig, snap: Any) -> dict[str, Any]:
    """Inspect `label start:`'s body and report whether it's wired.

    "Wired" = body is exactly a single `jump <other-label>` to an existing
    label. Anything else (empty `return`, scaffold dialogue, agent-authored
    content) is reported in the appropriate finding.
    """
    findings: list[StatusFinding] = []
    start = next((l for l in snap.labels if l.name == "start"), None)
    if start is None:
        findings.append(
            StatusFinding(
                rule="missing_start_label",
                severity="error",
                message=(
                    "No `label start:` exists. Ren'Py needs a `start` label "
                    "as the New Game entry point — call `create_scene("
                    'name="start", ...)` or `set_start_target` after '
                    "authoring an opening label."
                ),
                fix_hint="create_scene(name=\"start\") or set_start_target",
            )
        )
        return {"wired": False, "summary": {"present": False}, "findings": findings}

    body = _read_label_body(config, start)
    body_stripped = [l.strip() for l in body if l.strip()]
    is_empty_return = body_stripped == ["return"]
    is_jump = (
        len(body_stripped) == 1
        and body_stripped[0].startswith("jump ")
        and not body_stripped[0].startswith("jump start")
    )
    target = body_stripped[0].split(maxsplit=1)[1] if is_jump else None

    if is_empty_return:
        findings.append(
            StatusFinding(
                rule="empty_start_label",
                severity="warning",
                message=(
                    "`label start:` body is just `return`. The player will "
                    "click New Game and immediately exit to the title. Wire "
                    "the entry with set_start_target(target=\"<your label>\")."
                ),
                fix_hint="set_start_target",
            )
        )
        return {
            "wired": False,
            "summary": {"present": True, "wired": False, "body": body_stripped},
            "findings": findings,
        }

    if is_jump:
        existing = {l.name for l in snap.labels}
        if target not in existing:
            findings.append(
                StatusFinding(
                    rule="start_jumps_to_unknown_label",
                    severity="error",
                    message=(
                        f"`label start:` jumps to `{target}` but no such "
                        "label exists yet. Author the target with create_scene "
                        "/ create_choice_node / create_route, or rewire with "
                        "set_start_target."
                    ),
                    fix_hint="create_scene(name=\"%s\") or set_start_target" % target,
                )
            )
            return {
                "wired": False,
                "summary": {"present": True, "wired": False, "jumps_to": target},
                "findings": findings,
            }
        return {
            "wired": True,
            "summary": {"present": True, "wired": True, "jumps_to": target},
            "findings": findings,
        }

    # Body has authored content but no jump — could be a fully self-
    # contained start, which is fine, OR a half-converted scaffold.
    findings.append(
        StatusFinding(
            rule="start_label_inline_content",
            severity="info",
            message=(
                "`label start:` has authored content rather than a `jump`. "
                "That's fine for a one-scene VN; for branching stories most "
                "authors keep `start` as a thin redirect via set_start_target."
            ),
            fix_hint="(no fix needed if intentional)",
        )
    )
    return {
        "wired": True,
        "summary": {"present": True, "wired": True, "body_lines": len(body_stripped)},
        "findings": findings,
    }


def _read_label_body(config: ServerConfig, label: Any) -> list[str]:
    """Slice `label`'s body lines from disk (1-based start_line + 1 .. end_line)."""
    rel = label.range.file
    text = (config.project_root / rel).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    return lines[label.range.start_line : label.range.end_line]


def _scan_for_sdk_placeholders(config: ServerConfig) -> list[tuple[str, str]]:
    """Return (relative-path, phrase) for each .rpy file under game/ that
    still contains an SDK-template placeholder phrase."""
    out: list[tuple[str, str]] = []
    game_dir = config.game_dir
    if not game_dir.is_dir():
        return out
    for rpy in sorted(game_dir.rglob("*.rpy")):
        # Skip the GUI/screens.rpy which legitimately ship template-y
        # phrases like "show eileen happy" inside docstring comments.
        if rpy.name in ("screens.rpy", "gui.rpy"):
            continue
        try:
            text = rpy.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for phrase in _SDK_PLACEHOLDER_PHRASES:
            if phrase in text:
                rel = rpy.relative_to(config.project_root).as_posix()
                out.append((rel, phrase))
                break  # one finding per file is plenty
    return out


def _scan_label_todos(config: ServerConfig, snap: Any) -> list[tuple[str, str]]:
    """Return (label_name, file) for every label whose body contains
    only TODO/placeholder comments and boilerplate (jump/return)."""
    out: list[tuple[str, str]] = []
    for label in snap.labels:
        body = _read_label_body(config, label)
        non_blank = [l.strip() for l in body if l.strip()]
        if not non_blank:
            continue
        # A label is a stub when every non-blank line is either a
        # comment, a `return`, or a `jump <label>`. That's exactly the
        # shape `create_route` emits — and what an agent leaves behind
        # when they scaffold a route and then forget to fill it.
        def _is_boilerplate(line: str) -> bool:
            if line.startswith("#"):
                return True
            if line == "return":
                return True
            if line.startswith("jump ") or line.startswith("call "):
                return True
            return False

        if not all(_is_boilerplate(l) for l in non_blank):
            continue
        if any(
            _TODO_BODY_RE.search(l) or _PLACEHOLDER_BODY_RE.search(l)
            for l in non_blank
        ):
            out.append((label.name, label.range.file))
    return out


_CONFIG_NAME_RE = re.compile(r'define\s+config\.name\s*=\s*_\(\s*"([^"]*)"\s*\)')


def _read_config_name(config: ServerConfig) -> str | None:
    options = config.project_root / "game" / "options.rpy"
    if not options.is_file():
        return None
    try:
        text = options.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _CONFIG_NAME_RE.search(text)
    return m.group(1) if m else None


__all__ = ["evaluate", "StatusFinding"]
