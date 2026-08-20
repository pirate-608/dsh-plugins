"""Parse `renpy.sh <project> lint` output into structured findings.

Ren'Py prints lint as free-form text — file:line + message, occasionally
spanning multiple lines, sprinkled with global advisories ("It is advised
to set config.check_conflicting_properties..."), framed by a Statistics
block and a final "X errors, Y warnings, ..." summary line.

Agents drive better when they get the same structured shape every other
diagnostic in this server returns: a list of `{rule, severity, file,
line, message, label?}`. This module is the parser; the `get_lint_report`
tool calls it and folds the result alongside the raw stdout.

Severity inference is heuristic: Ren'Py does not tag findings, so we map
common phrasing to error / warning / info. Wrong inferences shouldn't
break agent loops because the raw message is preserved verbatim.
"""

from __future__ import annotations

import re
from typing import Any


# `game/script.rpy:5 The jump is to nonexistent label 'nowhere'.`
_FINDING_RE = re.compile(
    r"^(?P<file>[\w./-]+\.rpy[m]?):(?P<line>\d+)\s+(?P<message>.*)$"
)
# `File "game/script.rpy", line 11:` — alternate format for "defined twice".
_FILE_LINE_RE = re.compile(
    r'^(?:and\s+)?File\s+"(?P<file>[\w./-]+\.rpy[m]?)",\s+line\s+(?P<line>\d+):\s*$'
)
# Inline `File "x", line N:` patterns embedded in a finding's message;
# Ren'Py uses this to point at the duplicate location of "defined twice".
_INLINE_FILE_LINE_RE = re.compile(
    r'File\s+"(?P<file>[\w./-]+\.rpy[m]?)",\s+line\s+(?P<line>\d+)'
)
# `1 errors, 2 warnings, 3 informational messages, 4 obsolete creator-defined names.`
_SUMMARY_RE = re.compile(
    r"(?P<errors>\d+)\s+errors?(?:,\s*(?P<warnings>\d+)\s+warnings?)?"
    r"(?:,\s*(?P<info>\d+)\s+informational[^,]*)?"
    r"(?:,\s*(?P<obsolete>\d+)\s+obsolete[^.]*)?",
    re.IGNORECASE,
)
_STATS_HEADER_RE = re.compile(r"^Statistics:\s*$")
_FOOTER_PHRASES = (
    "Lint is not a substitute",
    "Try changing config.script_version",
)
_ADVISORY_PHRASES = (
    "It is advised",
    "It is suggested",
    "Please ",
)


def _infer_severity(message: str) -> str:
    m = message.lower()
    # Errors — things Ren'Py treats as broken at runtime / build.
    if any(
        token in m
        for token in (
            "nonexistent",
            "is not loadable",
            "defined twice",
            "duplicate",
            "syntax error",
            "is undefined",
            "no such",
            "not defined",
            "does not exist",
            "invalid ",
            "could not load",
        )
    ):
        return "error"
    # Informational / advisory.
    if any(
        token in m
        for token in (
            "obsolete",
            "deprecated",
            "is advised",
            "should ",
            "informational",
        )
    ):
        return "info"
    return "warning"


def parse_lint_output(stdout: str) -> dict[str, Any]:
    """Convert lint stdout into the standard diagnostics shape.

    Returns:
        {
          "findings": [{rule, severity, file, line, message}],
          "advisories": [str, ...],
          "statistics": {...} or None,
          "summary": {errors, warnings, info, obsolete} or None,
          "summary_line": str or None,  # raw one-liner for display
        }

    Findings preserve the order Ren'Py prints them. Continuation lines
    (no file:line prefix, not an advisory) attach to the previous
    finding's message. Statistics come back as a dict of free-form
    string lines so the caller can render them; we don't try to parse
    individual numbers.
    """
    findings: list[dict[str, Any]] = []
    advisories: list[str] = []
    statistics_lines: list[str] = []
    summary: dict[str, int] | None = None
    summary_line: str | None = None

    in_stats = False
    in_footer = False
    current: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            # Lift any inline `File "x", line N:` references out of the
            # message into the structured `references` list. Mirrors what
            # the standalone-line case does for multi-line lint output.
            inline_refs = [
                {"file": m.group("file"), "line": int(m.group("line"))}
                for m in _INLINE_FILE_LINE_RE.finditer(current["message"])
                # Skip self-reference (the finding's own file/line).
                if not (
                    m.group("file") == current.get("file")
                    and int(m.group("line")) == current.get("line")
                )
            ]
            if inline_refs:
                refs = current.setdefault("references", [])
                for ref in inline_refs:
                    if ref not in refs:
                        refs.append(ref)
            findings.append(current)
            current = None

    for raw in stdout.splitlines():
        line = raw.rstrip()

        if not line:
            # Blank line ends a finding's message accumulation.
            flush()
            continue

        if _STATS_HEADER_RE.match(line):
            flush()
            in_stats = True
            continue

        if any(line.startswith(p) for p in _FOOTER_PHRASES):
            flush()
            in_stats = False
            in_footer = True
            continue

        if in_footer:
            # Footer can contain a summary line; keep scanning for it.
            if _has_summary(line):
                summary, summary_line = _capture_summary(line)
            continue

        if in_stats:
            # Sometimes a summary line appears INSIDE the Statistics block
            # (older Ren'Py); detect it so it doesn't get lost.
            if _has_summary(line):
                summary, summary_line = _capture_summary(line)
            statistics_lines.append(line)
            continue

        m = _FINDING_RE.match(line)
        if m:
            flush()
            current = {
                "rule": "renpy_lint",
                "severity": _infer_severity(m.group("message")),
                "file": m.group("file"),
                "line": int(m.group("line")),
                "message": m.group("message").strip(),
            }
            continue

        m2 = _FILE_LINE_RE.match(line)
        if m2:
            # Alternate `File "x", line N:` framing — typically follows
            # a "The label X is defined twice, at" header. Attach to the
            # active finding, or to the most recent already-flushed
            # finding when a blank line broke the streak (Ren'Py prints
            # `at File "X", line 11:` then a blank line then `and File
            # "X", line 14:`).
            ref = {"file": m2.group("file"), "line": int(m2.group("line"))}
            target = current if current is not None else (findings[-1] if findings else None)
            if target is not None and ref not in target.setdefault("references", []):
                if not (
                    ref["file"] == target.get("file")
                    and ref["line"] == target.get("line")
                ):
                    target["references"].append(ref)
            elif target is None:
                # Truly standalone — emit as its own finding so the
                # location still surfaces.
                current = {
                    "rule": "renpy_lint",
                    "severity": "error",
                    "file": ref["file"],
                    "line": ref["line"],
                    "message": "(see related finding)",
                }
            continue

        if any(line.startswith(p) for p in _ADVISORY_PHRASES):
            flush()
            advisories.append(line.strip())
            continue

        if _has_summary(line):
            flush()
            summary, summary_line = _capture_summary(line)
            continue

        # Continuation of the previous finding's message.
        if current is not None:
            current["message"] = f"{current['message']} {line.strip()}"

    flush()

    # If Ren'Py omitted the summary line entirely (some versions skip it
    # when there are zero findings), synthesize one from what we counted.
    if summary is None:
        synthesized = {
            "errors": sum(1 for f in findings if f["severity"] == "error"),
            "warnings": sum(1 for f in findings if f["severity"] == "warning"),
            "info": sum(1 for f in findings if f["severity"] == "info"),
            "obsolete": 0,
        }
        summary = synthesized

    return {
        "findings": findings,
        "advisories": advisories,
        "statistics": statistics_lines or None,
        "summary": summary,
        "summary_line": summary_line,
    }


def _has_summary(line: str) -> bool:
    if "error" not in line.lower():
        return False
    return _SUMMARY_RE.search(line) is not None


def _capture_summary(line: str) -> tuple[dict[str, int], str]:
    m = _SUMMARY_RE.search(line)
    assert m is not None  # caller checked _has_summary
    counts = {
        "errors": int(m.group("errors") or 0),
        "warnings": int(m.group("warnings") or 0),
        "info": int(m.group("info") or 0),
        "obsolete": int(m.group("obsolete") or 0),
    }
    return counts, line.strip()


__all__ = ["parse_lint_output"]
