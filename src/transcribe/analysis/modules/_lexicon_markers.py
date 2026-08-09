"""Shared lexicon marker matching (TX lexicon_markers adaptation; speakers stripped)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ALGORITHM_VERSION = "lexicon_markers_v1"
TOKENIZER_VERSION = "unicode_word_v1"

_TOKEN_RE = re.compile(r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*", re.UNICODE)


@dataclass(frozen=True)
class MarkerPhrase:
    surface: str
    category: str
    token_count: int


@dataclass(frozen=True)
class MarkerHit:
    unit_id: str
    unit_order: float
    start: int
    end: int
    surface: str
    category: str
    module: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "unit_order": self.unit_order,
            "start": self.start,
            "end": self.end,
            "surface": self.surface,
            "category": self.category,
            "module": self.module,
        }


def tokenize(text: str) -> list[str]:
    return [
        m.group(0).casefold()
        for m in _TOKEN_RE.finditer(text or "")
        if len(m.group(0)) >= 2
    ]


def count_tokens(text: str) -> int:
    return len(tokenize(text))


def _phrase_token_count(phrase: str) -> int:
    return max(1, len(tokenize(phrase)))


def load_categorized_lexicon(path: Path | str) -> dict[str, tuple[MarkerPhrase, ...]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    categories = raw.get("categories") or {}
    if not isinstance(categories, dict):
        raise ValueError(f"Invalid lexicon categories in {path}")
    out: dict[str, list[MarkerPhrase]] = {}
    for category, phrases in categories.items():
        if not isinstance(phrases, list):
            continue
        items: list[MarkerPhrase] = []
        for phrase in phrases:
            surface = str(phrase).strip()
            if not surface:
                continue
            items.append(
                MarkerPhrase(
                    surface=surface.casefold(),
                    category=str(category),
                    token_count=_phrase_token_count(surface),
                )
            )
        items.sort(key=lambda p: (-len(p.surface), p.surface))
        out[str(category)] = items
    return {k: tuple(v) for k, v in out.items()}


def iter_phrases(
    lexicon: Mapping[str, Sequence[MarkerPhrase]],
    enabled_categories: Iterable[str] | None = None,
) -> list[MarkerPhrase]:
    enabled = (
        None if enabled_categories is None else {str(c) for c in enabled_categories}
    )
    phrases: list[MarkerPhrase] = []
    for category, items in lexicon.items():
        if enabled is not None and category not in enabled:
            continue
        phrases.extend(items)
    phrases.sort(key=lambda p: (-len(p.surface), p.surface))
    return phrases


def match_phrases_in_text(
    text: str,
    phrases: Sequence[MarkerPhrase],
    *,
    unit_id: str,
    unit_order: float,
    module: str,
) -> list[MarkerHit]:
    """Greedy non-overlapping longest-match-first over casefolded text."""
    if not text or not phrases:
        return []
    lower = text.casefold()
    occupied = [False] * len(lower)
    hits: list[MarkerHit] = []

    candidates: list[tuple[int, int, MarkerPhrase]] = []
    for phrase in phrases:
        needle = phrase.surface
        if not needle:
            continue
        start = 0
        while True:
            idx = lower.find(needle, start)
            if idx < 0:
                break
            end = idx + len(needle)
            if _has_alnum_neighbor(lower, idx, end):
                start = idx + 1
                continue
            candidates.append((idx, end, phrase))
            start = idx + 1

    candidates.sort(key=lambda c: (c[0], -(c[1] - c[0])))
    for start, end, phrase in candidates:
        if any(occupied[start:end]):
            continue
        for i in range(start, end):
            occupied[i] = True
        hits.append(
            MarkerHit(
                unit_id=unit_id,
                unit_order=unit_order,
                start=start,
                end=end,
                surface=text[start:end],
                category=phrase.category,
                module=module,
            )
        )
    hits.sort(key=lambda h: (h.unit_order, h.start, h.end))
    return hits


def _has_alnum_neighbor(text: str, start: int, end: int) -> bool:
    left_ok = start == 0 or not text[start - 1].isalnum()
    right_ok = end >= len(text) or not text[end].isalnum()
    return not (left_ok and right_ok)


def stats_for_scope(
    category_counts: Mapping[str, int],
    token_count: int,
    categories: Sequence[str],
    min_tokens_for_rates: int,
) -> dict[str, Any]:
    total_hits = sum(int(category_counts.get(c, 0)) for c in categories)
    rates: dict[str, float | None] = {}
    can_rate = token_count >= min_tokens_for_rates and token_count > 0
    for category in categories:
        count = int(category_counts.get(category, 0))
        rates[category] = (count * 100.0 / token_count) if can_rate else None
    return {
        "token_count": int(token_count),
        "total_marker_hits": int(total_hits),
        "category_counts": {c: int(category_counts.get(c, 0)) for c in categories},
        "hits_per_100_tokens": (
            (total_hits * 100.0 / token_count) if can_rate else None
        ),
        "category_rates_per_100_tokens": rates,
    }


def derive_epistemic_shares(global_stats: Mapping[str, Any]) -> dict[str, float | None]:
    counts = global_stats.get("category_counts") or {}
    if not isinstance(counts, Mapping):
        return {"hedge_share": None, "booster_share": None}
    hedges = (
        int(counts.get("epistemic_hedge", 0))
        + int(counts.get("approximator", 0))
        + int(counts.get("modal_uncertainty", 0))
    )
    boosters = int(counts.get("certainty_booster", 0))
    total = hedges + boosters
    if total <= 0:
        return {"hedge_share": None, "booster_share": None}
    return {
        "hedge_share": hedges / total,
        "booster_share": boosters / total,
    }
