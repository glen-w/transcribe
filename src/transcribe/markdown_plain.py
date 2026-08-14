"""Escape OCR / user text so Streamlit markdown cannot promote it to headings."""

from __future__ import annotations


def escape_markdown_plain(text: str) -> str:
    """Escape markdown so ``st.caption`` / ``st.markdown`` keep a uniform font.

    OCR (``faithful_markdown``) often starts with ``#`` / ``-`` / ``*``. Feeding
    that into Streamlit markdown turns one search snippet or quote into an
    ``h1`` while neighbours stay caption-sized.
    """
    # Backslash first so later escapes are not re-escaped.
    out = text.replace("\\", "\\\\")
    for ch in (
        "`",
        "*",
        "_",
        "{",
        "}",
        "[",
        "]",
        "(",
        ")",
        "#",
        "+",
        "-",
        ".",
        "!",
        "|",
        "~",
    ):
        out = out.replace(ch, "\\" + ch)
    return out
