"""Review header signals: source-only metrics and anomaly flags."""

from __future__ import annotations

from transcribe.services.ocr_alignment import align_ocr
from transcribe.services.review_signals import build_review_signals


def test_build_review_signals_uses_source_only_counts() -> None:
    sources = {
        "a": "alpha beta conversion gamma",
        "b": "alpha beta conversation gamma",
    }
    alignment = align_ocr(sources)
    signals = build_review_signals(alignment, sources, remaining=1)
    assert signals.disagreement_count == alignment.source_disagreement_count
    assert signals.agreement_ratio == alignment.agreement_ratio
    assert signals.remaining == 1
    assert "OCR disagreement" in signals.header_line()


def test_date_disagreement_flag() -> None:
    sources = {
        "a": "2024-01-15\nbody text",
        "b": "2024-03-20\nbody text",
    }
    alignment = align_ocr(sources)
    signals = build_review_signals(alignment, sources, remaining=0)
    assert signals.date_disagreement
    assert "date disagreement" in signals.header_line()


def test_markdown_contamination_flag() -> None:
    sources = {
        "a": "# Heading\nbody",
        "b": "# Heading\nbody",
    }
    alignment = align_ocr(sources)
    signals = build_review_signals(alignment, sources, remaining=0)
    assert signals.markdown_contamination
    assert "markdown contamination" in signals.header_line()


def test_prompt_instruction_leak_sets_markdown_contamination() -> None:
    sources = {
        "a": ". - Use proper punctuation and spacing.\nbody",
        "b": ". - Use proper punctuation and spacing.\nbody",
    }
    alignment = align_ocr(sources)
    signals = build_review_signals(alignment, sources, remaining=0)
    assert signals.markdown_contamination
    assert "markdown contamination" in signals.header_line()


def test_use_consistent_style_leak_sets_markdown_contamination() -> None:
    sources = {
        "a": "Use a consistent style for the page.\nok",
        "b": "Use a consistent style for the page.\nok",
    }
    alignment = align_ocr(sources)
    signals = build_review_signals(alignment, sources, remaining=0)
    assert signals.markdown_contamination