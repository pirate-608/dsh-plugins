"""Escape Ren'Py text-tag and substitution metacharacters in dialogue.

Ren'Py treats `{...}` as text tags and `[...]` as variable substitutions
inside say-statement strings. A literal `{` or `[` in the prose has to be
doubled. LLMs forget this constantly.

The rule: when the *agent* gives us the dialogue text as a separate field,
we escape `{`, `}`, `[`, `]` ourselves so the agent never has to think
about it. The agent CAN bypass escaping by providing already-escaped text
via a `raw: true` flag on the relevant write tool.
"""

from __future__ import annotations


def escape_dialogue(text: str) -> str:
    """Double every Ren'Py text-tag / substitution metacharacter in `text`."""
    return (
        text.replace("{", "{{")
        .replace("}", "}}")
        .replace("[", "[[")
        .replace("]", "]]")
    )


def reject_multiline(text: str) -> str | None:
    """Return an error message if ``text`` contains a raw newline/carriage return.

    Ren'Py say-statement strings live on one line; a literal ``\\n`` in the
    text field would break the quoted string across lines in the generated
    ``.rpy`` — the rest of the script indents wrongly and the file fails
    to lint. Callers should pass multi-line speech as separate calls.
    """
    if "\n" in text or "\r" in text:
        return (
            "text must be single-line; split multi-line speech into separate "
            "calls (one line per call for `add_say`, one entry per line for "
            "`add_dialogue_block`)"
        )
    return None
