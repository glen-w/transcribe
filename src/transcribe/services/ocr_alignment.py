"""Source-only OCR alignment for Review.

Raw vision attempts are independent evidence. The merged draft (composite) is a
recommendation, never a vote. Canonical/editor text is the resolution target
and does not participate in consensus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_BULLET_NORMS = frozenset({"-", "*", "•"})
_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_MIN_OMITTED_TOKENS = 3
# Punctuation / rule / pipe noise — not worth a Review disagreement step.
_PUNCT_NOISE_RE = re.compile(r"^[\s\|/\\.\-_*•·,;:'\"`~=+#]+$")
_PROMPT_INSTRUCTION_RE = re.compile(
    r"use\s+proper\s+punctuation|"
    r"format\s+the\s+output|"
    r"you are an?\s+(ocr|transcription)",
    re.IGNORECASE,
)


def is_non_reviewable_span(text: str) -> bool:
    """True when a span is punctuation/rule noise or a prompt-instruction fragment."""
    stripped = (text or "").strip()
    if not stripped:
        return True
    if _PUNCT_NOISE_RE.match(stripped):
        return True
    if _PROMPT_INSTRUCTION_RE.search(stripped) and len(stripped) < 160:
        return True
    return False


def region_variants_non_reviewable(variants: dict[str, str]) -> bool:
    """True when every source variant is non-reviewable junk."""
    if not variants:
        return True
    return all(is_non_reviewable_span(v) for v in variants.values())


@dataclass(frozen=True)
class AlignToken:
    """One alignment token with original offsets into the source string."""

    text: str
    norm: str
    start: int
    end: int


@dataclass(frozen=True)
class DisagreementRegion:
    """A reviewable span. Source regions are independent of composite/canonical."""

    key: str
    kind: str  # "source" | "departure"
    base_i1: int
    base_i2: int
    line_hint: int
    variants: dict[str, str]
    agreeing_ids: tuple[str, ...]
    composite_variant: str | None = None
    composite_matches_attempt_ids: tuple[str, ...] = ()
    composite_departure: bool = False
    omitted_from_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlignmentResult:
    """Derived alignment. ``source_disagreement_count`` ignores composite and canonical."""

    base_id: str
    base_original: str
    base_tokens: tuple[AlignToken, ...]
    source_ids: tuple[str, ...]
    agreement_ratio: float
    source_disagreement_count: int
    omitted_span_count: int
    departure_count: int
    regions: tuple[DisagreementRegion, ...]


def normalize_token(text: str) -> str:
    """Alignment-only token norm. Never used to rewrite persisted text."""
    if text in _BULLET_NORMS:
        return "*BULLET*"
    return text


def tokenize(original: str) -> list[AlignToken]:
    """Tokenise ``original``. Newlines and repeated whitespace are not tokens."""
    tokens: list[AlignToken] = []
    i = 0
    n = len(original)
    while i < n:
        if original[i].isspace():
            i += 1
            continue
        match = _TOKEN_RE.match(original, i)
        if match is None:
            i += 1
            continue
        raw = match.group(0)
        tokens.append(
            AlignToken(
                text=raw,
                norm=normalize_token(raw),
                start=match.start(),
                end=match.end(),
            )
        )
        i = match.end()
    return tokens


def normalize_span(text: str) -> str:
    """Alignment-only span identity (tokens joined). Display still uses exact text."""
    return " ".join(token.norm for token in tokenize(text))


def is_whitespace_only_change(old: str, new: str) -> bool:
    """True when texts match after alignment-only normalisation."""
    return normalize_span(old) == normalize_span(new)


def choose_base_id(sources: dict[str, str]) -> str:
    """Longest source text; stable tie-break on attempt id."""
    return min(sources, key=lambda aid: (-len(sources[aid]), aid))


def _span_from_tokens(original: str, tokens: list[AlignToken], i1: int, i2: int) -> str:
    if i1 >= i2 or not tokens:
        return ""
    i1 = max(0, min(i1, len(tokens)))
    i2 = max(i1, min(i2, len(tokens)))
    if i1 >= i2:
        return ""
    return original[tokens[i1].start : tokens[i2 - 1].end]


def _line_hint(original: str, tokens: list[AlignToken], i1: int) -> int:
    if not tokens:
        return 1
    idx = min(max(i1, 0), len(tokens) - 1)
    return 1 + original[: tokens[idx].start].count("\n")


def _opcodes(a: list[str], b: list[str]) -> list[tuple[str, int, int, int, int]]:
    return list(SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes())


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda item: (item[0], item[1]))
    merged: list[tuple[int, int]] = [ordered[0]]
    for start, end in ordered[1:]:
        prev_s, prev_e = merged[-1]
        if start <= prev_e:
            merged[-1] = (prev_s, max(prev_e, end))
        else:
            merged.append((start, end))
    return merged


def _extract_other_span(
    *,
    original: str,
    tokens: list[AlignToken],
    opcodes: list[tuple[str, int, int, int, int]],
    i1: int,
    i2: int,
) -> str:
    """Exact substring on ``original`` corresponding to base token range ``[i1, i2)``."""
    indices: list[int] = []
    for tag, a1, a2, b1, b2 in opcodes:
        if tag == "insert":
            if i1 <= a1 <= i2:
                indices.extend(range(b1, b2))
            continue
        if a2 <= i1 or a1 >= i2:
            continue
        overlap_lo = max(a1, i1)
        overlap_hi = min(a2, i2)
        if overlap_lo >= overlap_hi:
            continue
        if tag == "delete":
            continue
        # equal / replace: proportional slice when lengths match; else whole other slice
        if a2 > a1 and b2 > b1 and tag == "equal":
            lo = b1 + (overlap_lo - a1)
            hi = b1 + (overlap_hi - a1)
            indices.extend(range(lo, hi))
        else:
            indices.extend(range(b1, b2))
    if not indices:
        return ""
    lo = min(indices)
    hi = max(indices) + 1
    return _span_from_tokens(original, tokens, lo, hi)


def _map_base_range_to_chars(
    *,
    original: str,
    tokens: list[AlignToken],
    opcodes: list[tuple[str, int, int, int, int]],
    i1: int,
    i2: int,
) -> tuple[int, int]:
    """Map base token range to character offsets in ``original`` (canonical or other)."""
    if not tokens:
        return 0, 0
    span = _extract_other_span(
        original=original, tokens=tokens, opcodes=opcodes, i1=i1, i2=i2
    )
    if span:
        start = original.find(span)
        if start >= 0:
            return start, start + len(span)
    # Zero-width / failed extract: map to a boundary character.
    for tag, a1, a2, b1, b2 in opcodes:
        if tag == "equal" and a1 <= i1 < a2 and b2 > b1:
            offset = i1 - a1
            idx = min(b1 + offset, len(tokens) - 1)
            return tokens[idx].start, tokens[idx].start
        if tag == "insert" and a1 == i1:
            if b1 < len(tokens):
                return tokens[b1].start, tokens[b1].start
        if tag in {"replace", "delete"} and a1 <= i1 <= a2:
            if b1 < len(tokens):
                pos = tokens[b1].start
                return pos, pos
            return len(original), len(original)
    if i1 <= 0:
        return 0, 0
    return len(original), len(original)


def align_ocr(
    source_attempts: dict[str, str],
    *,
    composite_candidate: str | None = None,
    canonical_buffer: str | None = None,
    base_id: str | None = None,
) -> AlignmentResult:
    """Align independent source OCR texts. Composite and canonical are not votes.

    ``canonical_buffer`` is accepted so callers can pass the three channels
    explicitly; it does not affect agreement %, source-disagreement count, or
    agreeing IDs.
    """
    _ = canonical_buffer  # resolution target; consensus ignores it
    sources = {aid: text if text is not None else "" for aid, text in source_attempts.items()}
    source_ids = tuple(sorted(sources))
    if not sources:
        return AlignmentResult(
            base_id="",
            base_original="",
            base_tokens=(),
            source_ids=(),
            agreement_ratio=1.0,
            source_disagreement_count=0,
            omitted_span_count=0,
            departure_count=0,
            regions=(),
        )

    resolved_base = base_id if base_id in sources else choose_base_id(sources)
    base_original = sources[resolved_base]
    base_tokens = tokenize(base_original)
    base_norms = [token.norm for token in base_tokens]

    tokenized: dict[str, list[AlignToken]] = {resolved_base: base_tokens}
    opcodes_by_id: dict[str, list[tuple[str, int, int, int, int]]] = {}
    equal_mask = [True] * len(base_tokens) if base_tokens else []
    intervals: list[tuple[int, int]] = []
    omitted = 0

    for aid, text in sources.items():
        if aid == resolved_base:
            continue
        tokens = tokenize(text)
        tokenized[aid] = tokens
        ops = _opcodes(base_norms, [t.norm for t in tokens])
        opcodes_by_id[aid] = ops
        for tag, a1, a2, b1, b2 in ops:
            if tag == "equal":
                continue
            if tag == "insert":
                intervals.append((a1, a1))
                if (b2 - b1) >= _MIN_OMITTED_TOKENS:
                    omitted += 1
                continue
            for idx in range(a1, a2):
                if 0 <= idx < len(equal_mask):
                    equal_mask[idx] = False
            intervals.append((a1, a2))
            if tag == "delete" and (a2 - a1) >= _MIN_OMITTED_TOKENS:
                omitted += 1
            if tag == "replace" and (b2 - b1) - (a2 - a1) >= _MIN_OMITTED_TOKENS:
                omitted += 1

    merged = _merge_intervals(intervals)
    source_regions: list[DisagreementRegion] = []
    for i1, i2 in merged:
        variants: dict[str, str] = {}
        for aid, text in sources.items():
            if aid == resolved_base:
                variants[aid] = _span_from_tokens(base_original, base_tokens, i1, i2)
                continue
            variants[aid] = _extract_other_span(
                original=text,
                tokens=tokenized[aid],
                opcodes=opcodes_by_id[aid],
                i1=i1,
                i2=i2,
            )
        groups: dict[str, list[str]] = {}
        for aid, variant in variants.items():
            groups.setdefault(normalize_span(variant), []).append(aid)
        largest = (
            max(groups.values(), key=lambda ids: (len(ids), tuple(sorted(ids)))) if groups else []
        )
        omitted_from = tuple(
            sorted(aid for aid, variant in variants.items() if not normalize_span(variant))
        )
        # Keep junk in agreement_ratio (equal_mask already false) but do not
        # emit navigable Review steps for punctuation-only / prompt-leak spans.
        if region_variants_non_reviewable(variants):
            continue
        source_regions.append(
            DisagreementRegion(
                key=f"src:{i1}:{i2}",
                kind="source",
                base_i1=i1,
                base_i2=i2,
                line_hint=_line_hint(base_original, base_tokens, i1),
                variants=variants,
                agreeing_ids=tuple(sorted(largest)),
                omitted_from_ids=omitted_from,
            )
        )

    if base_tokens:
        agreement_ratio = sum(1 for flag in equal_mask if flag) / len(equal_mask)
    else:
        agreement_ratio = 1.0 if all(not tokenize(t) for t in sources.values()) else 0.0

    regions: list[DisagreementRegion] = list(source_regions)
    departure_count = 0
    comp_text = composite_candidate if composite_candidate is not None else None
    if comp_text is not None:
        comp_tokens = tokenize(comp_text)
        comp_ops = _opcodes(base_norms, [t.norm for t in comp_tokens])
        attached: list[DisagreementRegion] = []
        covered_departures: set[tuple[int, int]] = set()
        for region in source_regions:
            variant = _extract_other_span(
                original=comp_text,
                tokens=comp_tokens,
                opcodes=comp_ops,
                i1=region.base_i1,
                i2=region.base_i2,
            )
            matches = tuple(
                sorted(
                    aid
                    for aid, source_variant in region.variants.items()
                    if normalize_span(source_variant) == normalize_span(variant)
                    and normalize_span(variant)
                )
            )
            departure = bool(normalize_span(variant)) and not matches
            if departure:
                departure_count += 1
            attached.append(
                DisagreementRegion(
                    key=region.key,
                    kind=region.kind,
                    base_i1=region.base_i1,
                    base_i2=region.base_i2,
                    line_hint=region.line_hint,
                    variants=region.variants,
                    agreeing_ids=region.agreeing_ids,
                    composite_variant=variant or None,
                    composite_matches_attempt_ids=matches,
                    composite_departure=departure,
                    omitted_from_ids=region.omitted_from_ids,
                )
            )
            covered_departures.add((region.base_i1, region.base_i2))
        regions = attached

        dep_intervals: list[tuple[int, int]] = []
        for tag, a1, a2, _b1, _b2 in comp_ops:
            if tag == "equal":
                continue
            if tag == "insert":
                neighbours = [
                    equal_mask[i]
                    for i in (a1 - 1, a1)
                    if 0 <= i < len(equal_mask)
                ]
                if not equal_mask or all(neighbours):
                    dep_intervals.append((a1, a1))
                continue
            if a1 >= a2:
                continue
            if all(equal_mask[i] for i in range(a1, a2) if 0 <= i < len(equal_mask)):
                dep_intervals.append((a1, a2))
        for i1, i2 in _merge_intervals(dep_intervals):
            if (i1, i2) in covered_departures:
                continue
            if any(not (i2 <= r.base_i1 or i1 >= r.base_i2) for r in source_regions):
                continue
            variant = _extract_other_span(
                original=comp_text,
                tokens=comp_tokens,
                opcodes=comp_ops,
                i1=i1,
                i2=i2,
            )
            agreed = _span_from_tokens(base_original, base_tokens, i1, i2)
            if not normalize_span(variant) or normalize_span(variant) == normalize_span(agreed):
                continue
            departure_count += 1
            variants = {aid: agreed for aid in sources}
            regions.append(
                DisagreementRegion(
                    key=f"dep:{i1}:{i2}",
                    kind="departure",
                    base_i1=i1,
                    base_i2=i2,
                    line_hint=_line_hint(base_original, base_tokens, i1),
                    variants=variants,
                    agreeing_ids=source_ids,
                    composite_variant=variant,
                    composite_matches_attempt_ids=(),
                    composite_departure=True,
                )
            )

    return AlignmentResult(
        base_id=resolved_base,
        base_original=base_original,
        base_tokens=tuple(base_tokens),
        source_ids=source_ids,
        agreement_ratio=agreement_ratio,
        source_disagreement_count=len(source_regions),
        omitted_span_count=omitted,
        departure_count=departure_count,
        regions=tuple(regions),
    )


def grouped_source_variants(region: DisagreementRegion) -> list[tuple[tuple[str, ...], str]]:
    """Group source attempt ids that share an alignment-normalised variant."""
    buckets: dict[str, list[tuple[str, str]]] = {}
    for aid, variant in region.variants.items():
        buckets.setdefault(normalize_span(variant), []).append((aid, variant))
    groups: list[tuple[tuple[str, ...], str]] = []
    for items in buckets.values():
        ids = tuple(sorted(item[0] for item in items))
        display = items[0][1]
        groups.append((ids, display))
    groups.sort(key=lambda item: (-len(item[0]), item[1]))
    return groups


def apply_region_variant(
    canonical: str,
    alignment: AlignmentResult,
    region: DisagreementRegion,
    replacement: str,
) -> str:
    """Patch ``canonical`` at the span corresponding to ``region`` with exact ``replacement``."""
    can_tokens = tokenize(canonical)
    ops = _opcodes(
        [token.norm for token in alignment.base_tokens],
        [token.norm for token in can_tokens],
    )
    start, end = _map_base_range_to_chars(
        original=canonical,
        tokens=can_tokens,
        opcodes=ops,
        i1=region.base_i1,
        i2=region.base_i2,
    )
    if start > end:
        start, end = end, start
    return canonical[:start] + replacement + canonical[end:]


def next_unresolved_index(
    regions: tuple[DisagreementRegion, ...] | list[DisagreementRegion],
    resolved_keys: set[str],
    current: int,
    *,
    direction: int = 1,
) -> int:
    """Index of the next unresolved region after re-anchoring. Wraps within list."""
    if not regions:
        return 0
    n = len(regions)
    current = max(0, min(current, n - 1))
    step = 1 if direction >= 0 else -1
    for offset in range(1, n + 1):
        idx = (current + step * offset) % n
        if regions[idx].key not in resolved_keys:
            return idx
    return current


def first_unresolved_index(
    regions: tuple[DisagreementRegion, ...] | list[DisagreementRegion],
    resolved_keys: set[str],
    *,
    after_base_i1: int | None = None,
) -> int:
    """After apply: nearest subsequent unresolved region (else first unresolved)."""
    if not regions:
        return 0
    if after_base_i1 is not None:
        for i, region in enumerate(regions):
            if region.base_i1 >= after_base_i1 and region.key not in resolved_keys:
                return i
    for i, region in enumerate(regions):
        if region.key not in resolved_keys:
            return i
    return 0
