"""Defensible Review uncertainty signals (no calibrated OCR confidence)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from transcribe.domain.dates import extract_page_date
from transcribe.services.ocr_alignment import AlignmentResult, normalize_span

# 12–80 so a looping handwritten sentence (~50–70 chars) still matches when
# concatenated; 3 consecutive copies. Used by Review chrome and truncated OCR fail.
_REPEAT_RE = re.compile(r"(.{12,80}?)\1{2,}", re.DOTALL)
# Longer window for truncated OCR fail only: prompt-instruction blocks are
# often 120–220 chars per cycle and slip past the 80-char Review regex.
_LONG_REPEAT_RE = re.compile(r"(.{12,240}?)\1{2,}", re.DOTALL)


def text_has_repetition(text: str) -> bool:
    """True when ``text`` contains a 12–80 character span repeated 3+ times."""
    return bool(_REPEAT_RE.search(text or ""))


def text_has_long_repetition(text: str) -> bool:
    """True when ``text`` contains a 12–240 character span repeated 3+ times."""
    return bool(_LONG_REPEAT_RE.search(text or ""))


def text_echoes_prompt(text: str, prompt_text: str, *, min_prompt_chars: int = 40) -> bool:
    """True when truncated OCR output contains a substantial prompt substring."""
    body = (text or "").strip()
    prompt = (prompt_text or "").strip()
    if len(prompt) < min_prompt_chars or not body:
        return False
    # Prefer a mid-sized needle so tiny prompts (Free OCR.) do not false-positive.
    needle = prompt if len(prompt) <= 120 else prompt[:120]
    return needle in body


def first_repetition_match(text: str) -> re.Match[str] | None:
    """First short- or long-window repetition match, or None."""
    body = text or ""
    return _REPEAT_RE.search(body) or _LONG_REPEAT_RE.search(body)


def try_trim_late_repetition(
    text: str,
    *,
    min_keep_ratio: float = 0.7,
    min_prefix_chars: int = 40,
) -> str | None:
    """Salvage truncated OCR when looping only pads the tail.

    If a repetition cycle starts at/after ``min_keep_ratio`` of the text, return
    the prefix before that cycle. If looping starts earlier, return ``None``
    (caller should fail the attempt). If there is no repetition, return ``text``.
    """
    body = text or ""
    match = first_repetition_match(body)
    if match is None:
        return body
    if not body:
        return None
    if (match.start() / len(body)) < min_keep_ratio:
        return None
    prefix = body[: match.start()].rstrip()
    # Drop a partial fence run left before the 3× match unit.
    prefix = re.sub(r"(?:\n?```)+\s*$", "", prefix).rstrip()
    if len(prefix) < min_prefix_chars:
        return None
    return prefix
_MD_HEADING_RE = re.compile(r"(?m)^#{1,6}\s")
_PROMPT_LEAK_RE = re.compile(
    r"format\s+the\s+output\s+in\s+markdown|"
    r"you are an?\s+(ocr|transcription)|"
    r"use\s+proper\s+punctuation\s+and\s+spacing|"
    r"use\s+a\s+consistent\s+style",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReviewSignals:
    disagreement_count: int
    remaining: int
    agreement_ratio: float
    omitted_span_count: int
    departure_count: int
    date_disagreement: bool
    length_disagreement: bool
    repetition: bool
    markdown_contamination: bool

    def header_line(self) -> str:
        parts = [
            f"{self.disagreement_count} OCR disagreement"
            f"{'s' if self.disagreement_count != 1 else ''}",
        ]
        if self.disagreement_count:
            parts.append(f"{self.remaining} remaining")
        parts.append(f"{self.agreement_ratio:.0%} text agreement")
        if self.omitted_span_count:
            parts.append(
                f"{self.omitted_span_count} possible omitted "
                f"{'span' if self.omitted_span_count == 1 else 'spans'}"
            )
        if self.departure_count:
            parts.append(
                f"{self.departure_count} merged-draft departure"
                f"{'s' if self.departure_count != 1 else ''}"
            )
        if self.date_disagreement:
            parts.append("date disagreement")
        if self.length_disagreement:
            parts.append("length disagreement")
        if self.repetition:
            parts.append("repetition")
        if self.markdown_contamination:
            parts.append("markdown contamination")
        return " · ".join(parts)


def _length_disagreement(sources: dict[str, str]) -> bool:
    lengths = [len(normalize_span(text)) for text in sources.values()]
    if len(lengths) < 2:
        return False
    shortest, longest = min(lengths), max(lengths)
    if shortest == 0:
        return longest > 40
    return (longest / shortest) >= 1.5 and (longest - shortest) >= 40


def _date_disagreement(sources: dict[str, str]) -> bool:
    dates = []
    for text in sources.values():
        found = extract_page_date(text)
        dates.append(found.as_dict() if found is not None else None)
    present = [d for d in dates if d is not None]
    if len(present) < 2:
        return False
    return any(d != present[0] for d in present[1:])


def build_review_signals(
    alignment: AlignmentResult,
    sources: dict[str, str],
    *,
    remaining: int,
) -> ReviewSignals:
    blob = "\n".join(sources.values())
    return ReviewSignals(
        disagreement_count=alignment.source_disagreement_count,
        remaining=remaining,
        agreement_ratio=alignment.agreement_ratio,
        omitted_span_count=alignment.omitted_span_count,
        departure_count=alignment.departure_count,
        date_disagreement=_date_disagreement(sources),
        length_disagreement=_length_disagreement(sources),
        repetition=text_has_repetition(blob),
        markdown_contamination=bool(_MD_HEADING_RE.search(blob) or _PROMPT_LEAK_RE.search(blob)),
    )
