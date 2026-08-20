"""Tolerant structured parser for the body of one Ren'Py `label`.

`ProjectIndex` (scanner.py) only needs to find labels and slice their
ranges. This module goes one level deeper: it walks the body of a single
label and returns an ordered tree of recognized statements (says, shows,
jumps, menus, if-branches, etc.). Anything unrecognized is preserved as
`{kind: "unparsed", line, raw}` so consumers know when the tree omits
something they shouldn't silently overwrite.

Two goals shape the design:

1. **Ordered body.** The Scene Inspector renders the body verbatim, so
   the tree must preserve top-to-bottom order. Categorical conveniences
   (`background`, `music`, `outgoing_targets`) are derived in a second
   pass and live in `shorthand`.
2. **Recursive shape.** `menu` choices and `if/elif/else` branches each
   contain a nested body of the same shape. One agent-facing pattern
   covers the whole structure.

The parser is indent-aware but not a real Python tokenizer: it splits on
lines, tracks indent levels, and matches each statement with a small set
of regexes. This is consistent with how `scanner.py` operates — when
truly authoritative reasoning is needed, defer to `get_lint_report`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from ..config import ServerConfig
    from .scanner import LabelInfo

# Body lines inside a label live at exactly this indent (DESIGN §3:
# tabs are normalized to 4 spaces before any read sees the file).
BODY_BASE_INDENT = 4

# ---------- statement patterns --------------------------------------------------

_SCENE_RE = re.compile(r"^scene\s+(?P<expr>.+?)\s*$")
_SHOW_RE = re.compile(r"^show\s+(?P<expr>.+?)\s*$")
_HIDE_RE = re.compile(r"^hide\s+(?P<expr>.+?)\s*$")
_PLAY_RE = re.compile(r"^play\s+(?P<channel>\w+)\s+(?P<asset>\".*?\"|'.*?')\s*(?P<rest>.*?)\s*$")
_STOP_RE = re.compile(r"^stop\s+(?P<channel>\w+)\s*(?P<rest>.*?)\s*$")
_PAUSE_RE = re.compile(r"^pause(?:\s+(?P<dur>.+?))?\s*$")
_JUMP_RE = re.compile(r"^jump\s+(?P<target>[A-Za-z_]\w*)\s*$")
_CALL_RE = re.compile(r"^call\s+(?P<target>[A-Za-z_]\w*)\b\s*(?P<rest>.*?)\s*$")
_RETURN_RE = re.compile(r"^return(?:\s+.+)?\s*$")
_WITH_RE = re.compile(r"^with\s+(?P<expr>.+?)\s*$")
_DOLLAR_RE = re.compile(r"^\$\s*(?P<expr>.+?)\s*$")
_MENU_RE = re.compile(r"^menu\s*(?P<label>[A-Za-z_]\w*)?\s*:\s*$")
_IF_RE = re.compile(r"^if\s+(?P<cond>.+?)\s*:\s*$")
_ELIF_RE = re.compile(r"^elif\s+(?P<cond>.+?)\s*:\s*$")
_ELSE_RE = re.compile(r"^else\s*:\s*$")

# Choice line inside a menu: `"text":` or `"text" if cond:`.
_CHOICE_RE = re.compile(
    r"^(?P<text>\".*?\"|'.*?')\s*(?:if\s+(?P<cond>.+?))?\s*:\s*$"
)

# Say-statements come in two flavors:
#   `c "text"`            (named — `c` is a Character var)
#   `"text"`              (narration)
# Optional `(args)` after the var (e.g. `c "..." (interact=False)`) is rare;
# when seen, the whole line falls through to `unparsed` rather than risk a
# wrong split.
_SAY_NAMED_RE = re.compile(r"^(?P<who>[A-Za-z_]\w*)\s+(?P<text>\".*?\"|'.*?')\s*$")
_SAY_NARR_RE = re.compile(r"^(?P<text>\".*?\"|'.*?')\s*$")


# ---------- public API ----------------------------------------------------------


def parse_label_body(
    body_text: str,
    body_start_line: int,
) -> dict[str, Any]:
    """Parse a label body (without its header line) into a structured tree.

    `body_start_line` is the 1-based file line of the FIRST body line. Used
    to populate per-statement `line` fields so the GUI can map back to source.

    Returns a dict with:
        body: ordered list of statement nodes (each has `kind` + `line`)
        unparsed: list of {line, raw} entries that didn't match any pattern
        shorthand: derived conveniences (background, music, outgoing_targets,
                   ends_with_return)
    """
    raw_lines = body_text.splitlines()
    items = _index_lines(raw_lines, body_start_line)

    unparsed: list[dict[str, Any]] = []
    body, _ = _parse_block(items, 0, BODY_BASE_INDENT, unparsed)
    shorthand = _derive_shorthand(body)
    return {"body": body, "unparsed": unparsed, "shorthand": shorthand}


# ---------- internals -----------------------------------------------------------


def _index_lines(raw_lines: list[str], body_start_line: int) -> list[dict[str, Any]]:
    """Annotate each non-blank, non-comment line with indent + 1-based file line."""
    out: list[dict[str, Any]] = []
    for offset, raw in enumerate(raw_lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        out.append(
            {
                "line": body_start_line + offset,
                "indent": indent,
                "stripped": stripped,
                "raw": raw.rstrip(),
            }
        )
    return out


def _parse_block(
    items: list[dict[str, Any]],
    start: int,
    base_indent: int,
    unparsed: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Parse statements at exactly `base_indent`. Stop when indent < base.

    Returns (statements, next_index_after_block).
    """
    out: list[dict[str, Any]] = []
    i = start
    while i < len(items):
        item = items[i]
        if item["indent"] < base_indent:
            return out, i
        if item["indent"] > base_indent:
            # Stray over-indent without a parent compound statement — the
            # caller should not have left these for us. Surface as unparsed
            # so nothing is lost silently, then advance past it.
            unparsed.append({"line": item["line"], "raw": item["stripped"]})
            i += 1
            continue

        node, consumed = _parse_statement(items, i, base_indent, unparsed)
        if node is None:
            unparsed.append({"line": item["line"], "raw": item["stripped"]})
            i += 1
            continue
        out.append(node)
        i = consumed
    return out, i


def _parse_statement(
    items: list[dict[str, Any]],
    idx: int,
    base_indent: int,
    unparsed: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, int]:
    """Parse the single statement (possibly compound) starting at `items[idx]`.

    Returns (node, next_index_after_statement). On no match, returns
    (None, idx+1) so the caller can decide whether to record the line as
    unparsed.
    """
    item = items[idx]
    line = item["line"]
    stripped = item["stripped"]

    # Compound statements first (they consume nested blocks).
    if m := _MENU_RE.match(stripped):
        choices, after = _parse_menu(items, idx + 1, base_indent + BODY_BASE_INDENT, unparsed)
        return (
            {"kind": "menu", "line": line, "menu_label": m.group("label"), "choices": choices},
            after,
        )

    if m := _IF_RE.match(stripped):
        branches, after = _parse_if(items, idx, base_indent, unparsed)
        return ({"kind": "if", "line": line, "branches": branches}, after)

    # Single-line statements.
    if m := _SCENE_RE.match(stripped):
        return ({"kind": "scene", "line": line, "expression": m.group("expr")}, idx + 1)
    if m := _SHOW_RE.match(stripped):
        return ({"kind": "show", "line": line, "expression": m.group("expr")}, idx + 1)
    if m := _HIDE_RE.match(stripped):
        return ({"kind": "hide", "line": line, "expression": m.group("expr")}, idx + 1)
    if m := _PLAY_RE.match(stripped):
        return (
            {
                "kind": "play",
                "line": line,
                "channel": m.group("channel"),
                "asset": _strip_quotes(m.group("asset")),
                "options": (m.group("rest") or "").strip() or None,
            },
            idx + 1,
        )
    if m := _STOP_RE.match(stripped):
        return (
            {
                "kind": "stop",
                "line": line,
                "channel": m.group("channel"),
                "options": (m.group("rest") or "").strip() or None,
            },
            idx + 1,
        )
    if m := _PAUSE_RE.match(stripped):
        return (
            {"kind": "pause", "line": line, "duration": (m.group("dur") or "").strip() or None},
            idx + 1,
        )
    if m := _JUMP_RE.match(stripped):
        return ({"kind": "jump", "line": line, "target": m.group("target")}, idx + 1)
    if m := _CALL_RE.match(stripped):
        return (
            {
                "kind": "call",
                "line": line,
                "target": m.group("target"),
                "rest": (m.group("rest") or "").strip() or None,
            },
            idx + 1,
        )
    if _RETURN_RE.match(stripped):
        return ({"kind": "return", "line": line}, idx + 1)
    if m := _WITH_RE.match(stripped):
        return ({"kind": "with", "line": line, "expression": m.group("expr")}, idx + 1)
    if m := _DOLLAR_RE.match(stripped):
        return ({"kind": "set", "line": line, "expression": m.group("expr")}, idx + 1)
    if m := _SAY_NAMED_RE.match(stripped):
        return (
            {
                "kind": "say",
                "line": line,
                "character": m.group("who"),
                "text": _strip_quotes(m.group("text")),
            },
            idx + 1,
        )
    if m := _SAY_NARR_RE.match(stripped):
        return (
            {
                "kind": "say",
                "line": line,
                "character": None,
                "text": _strip_quotes(m.group("text")),
            },
            idx + 1,
        )
    return None, idx + 1


def _parse_menu(
    items: list[dict[str, Any]],
    start: int,
    choice_indent: int,
    unparsed: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Parse the body of a `menu:` block.

    Each choice is `"text" [if cond]:` at `choice_indent`. The choice's
    nested body sits at `choice_indent + BODY_BASE_INDENT`.
    """
    choices: list[dict[str, Any]] = []
    i = start
    while i < len(items):
        item = items[i]
        if item["indent"] < choice_indent:
            return choices, i
        if item["indent"] > choice_indent:
            unparsed.append({"line": item["line"], "raw": item["stripped"]})
            i += 1
            continue
        m = _CHOICE_RE.match(item["stripped"])
        if not m:
            unparsed.append({"line": item["line"], "raw": item["stripped"]})
            i += 1
            continue
        body, after = _parse_block(items, i + 1, choice_indent + BODY_BASE_INDENT, unparsed)
        choices.append(
            {
                "text": _strip_quotes(m.group("text")),
                "condition": (m.group("cond") or "").strip() or None,
                "line": item["line"],
                "body": body,
            }
        )
        i = after
    return choices, i


def _parse_if(
    items: list[dict[str, Any]],
    start: int,
    base_indent: int,
    unparsed: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Parse an `if/elif*/else?` chain into a flat list of branches."""
    branches: list[dict[str, Any]] = []
    i = start
    first = True
    while i < len(items):
        item = items[i]
        if item["indent"] != base_indent:
            break
        stripped = item["stripped"]

        if first:
            m = _IF_RE.match(stripped)
            if not m:
                break
            kind = "if"
            cond: str | None = m.group("cond").strip()
            first = False
        elif m := _ELIF_RE.match(stripped):
            kind = "elif"
            cond = m.group("cond").strip()
        elif _ELSE_RE.match(stripped):
            kind = "else"
            cond = None
        else:
            break

        body, after = _parse_block(items, i + 1, base_indent + BODY_BASE_INDENT, unparsed)
        branches.append({"kind": kind, "condition": cond, "line": item["line"], "body": body})
        i = after
    return branches, i


def _strip_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] in ('"', "'") and text[-1] == text[0]:
        return text[1:-1]
    return text


def _derive_shorthand(body: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the categorical conveniences that don't preserve order.

    - `background`: expression of the FIRST top-level `scene` statement.
    - `music`: asset of the FIRST top-level `play music` statement.
    - `outgoing_targets`: every label name reached via `jump` or `call`,
      including those nested inside menu choices and if-branches.
    - `ends_with_return`: true when the final top-level statement is `return`.
    """
    background: str | None = None
    music: str | None = None
    for node in body:
        if node["kind"] == "scene" and background is None:
            background = node["expression"]
        if node["kind"] == "play" and node["channel"] == "music" and music is None:
            music = node["asset"]
        if background is not None and music is not None:
            break

    targets: list[str] = []
    _collect_targets(body, targets)
    seen: set[str] = set()
    deduped = [t for t in targets if not (t in seen or seen.add(t))]

    ends_with_return = bool(body) and body[-1]["kind"] == "return"
    return {
        "background": background,
        "music": music,
        "outgoing_targets": deduped,
        "ends_with_return": ends_with_return,
    }


def _collect_targets(body: list[dict[str, Any]], out: list[str]) -> None:
    for node in body:
        if node["kind"] in ("jump", "call"):
            out.append(node["target"])
        elif node["kind"] == "menu":
            for choice in node["choices"]:
                _collect_targets(choice["body"], out)
        elif node["kind"] == "if":
            for branch in node["branches"]:
                _collect_targets(branch["body"], out)


def parse_label_from_disk(
    config: "ServerConfig",
    label: "LabelInfo",
) -> dict[str, Any]:
    """Read a label's body from disk and parse it into the typed tree.

    Matches the logic `read_label_tree` uses, factored out so any tool
    that needs the structured body of a label by `LabelInfo` can grab
    it without re-implementing the slice-and-parse dance.
    """
    text = (config.project_root / label.range.file).read_text(
        encoding="utf-8", errors="replace"
    )
    lines = text.splitlines()
    body_text = "\n".join(lines[label.range.start_line : label.range.end_line])
    return parse_label_body(body_text, body_start_line=label.range.start_line + 1)


def iter_statements(body: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield every statement in `body`, recursing into menus and if-branches.

    Order is depth-first preorder: a parent compound statement (`menu` /
    `if`) is yielded before its nested children, then each child's body
    is walked in turn. Diagnostics that need to inspect every statement
    in a label — invalid jumps, undefined character references, missing
    asset references — should iterate via this helper so the recursion
    pattern stays consistent across every Tier 1 read tool.
    """
    for node in body:
        yield node
        if node["kind"] == "menu":
            for choice in node["choices"]:
                yield from iter_statements(choice["body"])
        elif node["kind"] == "if":
            for branch in node["branches"]:
                yield from iter_statements(branch["body"])


def infer_label_kind(name: str, body: list[dict[str, Any]], shorthand: dict[str, Any]) -> str:
    """Infer the Story Map node kind from structure.

    `start` if the label is named `start`. `ending` if it terminates with
    `return` and has no outgoing jumps/calls. `choice` if its last
    meaningful statement is a `menu`. Otherwise `scene`.
    """
    if name == "start":
        return "start"
    has_outgoing = bool(shorthand["outgoing_targets"])
    if shorthand["ends_with_return"] and not has_outgoing:
        return "ending"
    if body and body[-1]["kind"] == "menu":
        return "choice"
    return "scene"
