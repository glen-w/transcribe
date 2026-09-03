"""Deterministic lexical counting for built-in detectors (no LLM)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcribe.analysis.modules._lexicon_markers import (
    MarkerHit,
    MarkerPhrase,
    iter_phrases,
    load_categorized_lexicon,
    match_phrases_in_text,
)

FIRST_PERSON_MATCHER = "first_person_i"
SWEAR_WORDS_MATCHER = "swear_words"
SWEAR_LEXICON_ID = "swear_words_en_v1"
SWEAR_LEXICON_FILENAME = "swear_words_en_v1.json"

# Standalone letter I / i as a word (includes "I" in "I'm" / "I've" via \b).
_FIRST_PERSON_RE = re.compile(r"\bi\b", re.IGNORECASE)

_DATA_DIR = Path(__file__).resolve().parent / "data"
_SWEAR_PATH = _DATA_DIR / SWEAR_LEXICON_FILENAME

_SWEAR_CACHE: dict[str, tuple[MarkerPhrase, ...]] | None = None
_SWEAR_DIGEST: str | None = None

_MAX_SAMPLES = 12


@dataclass(frozen=True)
class LexicalCountResult:
    count: int
    samples: tuple[str, ...]
    category_counts: dict[str, int]
    hits: tuple[MarkerHit, ...]

    def as_detector_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "count": self.count,
            "samples": list(self.samples),
        }
        if self.category_counts:
            out["category_counts"] = dict(self.category_counts)
        return out


def swear_lexicon_digest() -> str:
    return _load_swear_lexicon()[1]


def _load_swear_lexicon() -> tuple[dict[str, tuple[MarkerPhrase, ...]], str]:
    global _SWEAR_CACHE, _SWEAR_DIGEST
    if _SWEAR_CACHE is not None and _SWEAR_DIGEST is not None:
        return _SWEAR_CACHE, _SWEAR_DIGEST
    raw = _SWEAR_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    _SWEAR_CACHE = load_categorized_lexicon(_SWEAR_PATH)
    _SWEAR_DIGEST = digest
    return _SWEAR_CACHE, _SWEAR_DIGEST


def count_first_person(text: str) -> LexicalCountResult:
    """Count standalone first-person ``I`` / ``i`` references."""
    if not text:
        return LexicalCountResult(count=0, samples=(), category_counts={}, hits=())
    hits: list[MarkerHit] = []
    samples: list[str] = []
    for match in _FIRST_PERSON_RE.finditer(text):
        surface = match.group(0)
        hits.append(
            MarkerHit(
                unit_id="",
                unit_order=0.0,
                start=match.start(),
                end=match.end(),
                surface=surface,
                category="first_person",
                module="first_person",
            )
        )
        if len(samples) < _MAX_SAMPLES:
            samples.append(surface)
    return LexicalCountResult(
        count=len(hits),
        samples=tuple(samples),
        category_counts={"first_person": len(hits)} if hits else {},
        hits=tuple(hits),
    )


def count_swear_words(text: str) -> LexicalCountResult:
    """Count swear-word lexicon hits (greedy longest-match, case-insensitive)."""
    if not text:
        return LexicalCountResult(count=0, samples=(), category_counts={}, hits=())
    lexicon, _ = _load_swear_lexicon()
    phrases = iter_phrases(lexicon)
    hits = match_phrases_in_text(
        text,
        phrases,
        unit_id="",
        unit_order=0.0,
        module="swear_words",
    )
    category_counts: dict[str, int] = {}
    samples: list[str] = []
    for hit in hits:
        category_counts[hit.category] = category_counts.get(hit.category, 0) + 1
        if len(samples) < _MAX_SAMPLES:
            samples.append(hit.surface)
    return LexicalCountResult(
        count=len(hits),
        samples=tuple(samples),
        category_counts=category_counts,
        hits=tuple(hits),
    )


def run_lexical_matcher(matcher: str, text: str) -> LexicalCountResult:
    if matcher == FIRST_PERSON_MATCHER:
        return count_first_person(text)
    if matcher == SWEAR_WORDS_MATCHER:
        return count_swear_words(text)
    raise ValueError(f"unknown lexical matcher: {matcher}")


def _count_from_finding(finding: Any) -> tuple[str, int]:
    if hasattr(finding, "start_page_id"):
        page_id = str(getattr(finding, "start_page_id", "") or "")
        data = getattr(finding, "detector_data", None) or {}
    elif isinstance(finding, dict):
        page_id = str(finding.get("start_page_id") or "")
        data = finding.get("detector_data") or {}
    else:
        return "", 0
    if not isinstance(data, dict):
        data = {}
    try:
        count = int(data.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    return page_id, count


def lexical_page_count_rows(
    *,
    page_order: dict[str, int],
    page_counts: list[Any] | None = None,
    findings: list[Any] | None = None,
    pages_scanned: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build per-page count rows in notebook page order.

    Prefers published ``page_counts`` (includes zeros). Falls back to findings
    plus ``pages_scanned`` so older artifacts still render a complete series.
    """
    counts: dict[str, int] = {}
    if page_counts:
        for row in page_counts:
            if not isinstance(row, dict):
                continue
            page_id = str(row.get("page_id") or "")
            if not page_id:
                continue
            try:
                counts[page_id] = int(row.get("count") or 0)
            except (TypeError, ValueError):
                counts[page_id] = 0
    else:
        for finding in findings or []:
            page_id, count = _count_from_finding(finding)
            if page_id:
                counts[page_id] = count
        for page_id in pages_scanned or []:
            counts.setdefault(str(page_id), 0)

    ordered_ids = sorted(
        counts,
        key=lambda pid: (
            page_order[pid] if pid in page_order else 10**9,
            pid,
        ),
    )
    rows: list[dict[str, Any]] = []
    for page_id in ordered_ids:
        idx = page_order.get(page_id)
        order = (idx + 1) if isinstance(idx, int) else None
        rows.append(
            {
                "order": order,
                "page_id": page_id,
                "count": counts[page_id],
            }
        )
    return rows


def lexical_prompt_id(matcher: str) -> str:
    return f"lexical:{matcher}"


def validate_swear_lexicon_file() -> dict[str, Any]:
    """Load + parse lexicon (used by tests)."""
    data = json.loads(_SWEAR_PATH.read_text(encoding="utf-8"))
    if data.get("lexicon_id") != SWEAR_LEXICON_ID:
        raise ValueError(f"unexpected lexicon_id: {data.get('lexicon_id')}")
    lexicon, digest = _load_swear_lexicon()
    return {
        "lexicon_id": SWEAR_LEXICON_ID,
        "digest": digest,
        "category_count": len(lexicon),
        "phrase_count": sum(len(v) for v in lexicon.values()),
    }


__all__ = [
    "FIRST_PERSON_MATCHER",
    "LexicalCountResult",
    "SWEAR_LEXICON_ID",
    "SWEAR_WORDS_MATCHER",
    "count_first_person",
    "count_swear_words",
    "lexical_page_count_rows",
    "lexical_prompt_id",
    "run_lexical_matcher",
    "swear_lexicon_digest",
    "validate_swear_lexicon_file",
]
