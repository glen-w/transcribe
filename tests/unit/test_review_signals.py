"""Review header signals: source-only metrics and anomaly flags."""

from __future__ import annotations

from transcribe.services.ocr_alignment import align_ocr
from transcribe.services.review_signals import (
    build_review_signals,
    text_echoes_prompt,
    text_has_long_repetition,
    text_has_repetition,
    try_trim_late_repetition,
)


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


def test_text_has_repetition_detects_looping_span() -> None:
    looping = ("I'm talking lily and I'm not sure. ") * 6
    long_sentence = (
        "I'm talking lily and I'm not sure what I'm talking about. "
    ) * 4
    assert text_has_repetition(looping)
    assert text_has_repetition(long_sentence)
    assert not text_has_repetition("a unique notebook line with no looping span")
    assert not text_has_repetition("")


def test_text_has_long_repetition_catches_instruction_blocks() -> None:
    block = (
        "- Do not summarize, paraphrase, or infer missing text.\n"
        "- Retain spacing, punctuation, and line breaks as closely as possible.\n"
        "- If text is unclear or partially visible, extract as much as possible "
        "without guessing.\n\n"
    )
    looping = block * 4
    assert not text_has_repetition(looping)  # cycle > 80 chars
    assert text_has_long_repetition(looping)


def test_text_echoes_prompt_detects_instruction_leak() -> None:
    prompt = (
        "Extract all visible text from this handwritten notebook page "
        "without any changes.\n"
        "- Do not summarize, paraphrase, or infer missing text."
    )
    body = prompt + "\n" + ("- Do not summarize, paraphrase, or infer missing text.\n" * 20)
    assert text_echoes_prompt(body, prompt)
    assert not text_echoes_prompt("real diary line only", prompt)
    assert not text_echoes_prompt("x" * 100, "Free OCR.")  # short prompt ignored


def test_try_trim_late_repetition_salvages_fence_tail() -> None:
    # Unique lines so the diary body itself does not trip the short-repeat regex.
    diary = "\n".join(f"diary line {i} cafe across the street" for i in range(80))
    tail = ("\n```") * 80
    body = diary + tail
    trimmed = try_trim_late_repetition(body)
    assert trimmed is not None
    assert "diary line 0 cafe" in trimmed
    assert "```" not in trimmed


def test_try_trim_late_repetition_rejects_early_loop() -> None:
    block = ("I'm talking lily and I'm not sure. ") * 8
    assert try_trim_late_repetition(block) is None
