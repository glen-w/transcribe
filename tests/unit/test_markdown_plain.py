"""OCR / user text must not become Streamlit headings in compact GUI surfaces."""

from __future__ import annotations

from transcribe.markdown_plain import escape_markdown_plain
from transcribe.services.archive import highlight_terms


def test_escape_markdown_plain_neutralizes_heading() -> None:
    escaped = escape_markdown_plain("# Translucents - Why sad?")
    assert escaped.startswith("\\#")
    assert "\\-" in escaped
    assert not escaped.startswith("# ")


def test_highlight_terms_escapes_ocr_heading_but_bolds_match() -> None:
    text = "# Translucents - Why sad? Some search issues"
    out = highlight_terms(text, "Translucents")
    assert out.startswith("\\#")
    assert "**Translucents**" in out
    assert "\\-" in out


def test_highlight_terms_escapes_when_query_empty() -> None:
    assert highlight_terms("# Heading", "   ").startswith("\\#")


def test_highlight_terms_empty_text() -> None:
    assert highlight_terms("", "foo") == ""
