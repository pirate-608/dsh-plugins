"""Indentation normalization.

Ren'Py is indent-sensitive and forbids mixing tabs and spaces in the same
block. The most common LLM mistake is emitting a tab character on a line
that should have used 4 spaces. We normalize aggressively for tabs
(unconditional tab -> 4 spaces) but never re-flow space-based indent, since
2-space and 4-space code can both be valid and we cannot know which level
the surrounding block uses without parsing.
"""

from __future__ import annotations


def normalize_tabs(text: str, *, tab_width: int = 4) -> tuple[str, list[str]]:
    """Convert leading tab indentation to spaces. Returns (text, warnings)."""
    out_lines: list[str] = []
    warnings: list[str] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        # Only touch leading whitespace; embedded tabs (rare in .rpy) are left alone.
        stripped = line.lstrip()
        leading = line[: len(line) - len(stripped)]
        if "\t" in leading:
            new_leading = leading.expandtabs(tab_width)
            out_lines.append(new_leading + stripped)
            warnings.append(
                f"line {idx}: converted leading tab(s) to {tab_width} spaces"
            )
        else:
            out_lines.append(line)

    # splitlines drops a single trailing newline; restore it if the original had one.
    result = "\n".join(out_lines)
    if text.endswith("\n"):
        result += "\n"
    return result, warnings
