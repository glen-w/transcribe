"""Cross-window detection aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RawDetection:
    finding_type: str
    page_ids: tuple[str, ...]
    start_page_idx: int
    end_page_idx: int
    confidence: float
    reason: str
    title: str | None
    input_fingerprint: str
    window_id: str
    raw: dict[str, Any]


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _compatible_titles(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return True
    return a.casefold() == b.casefold()


def merge_adjacent_spans(
    raw_detections: list[RawDetection],
    *,
    ordered_page_ids: list[str],
    confidence_threshold: float,
) -> list[RawDetection]:
    """Deterministically merge overlapping/adjacent raw window hits."""
    filtered = [r for r in raw_detections if r.confidence >= confidence_threshold]
    if not filtered:
        return []

    filtered.sort(
        key=lambda r: (r.start_page_idx, r.end_page_idx, -r.confidence),
    )

    merged: list[RawDetection] = []
    for cand in filtered:
        placed = False
        for i, existing in enumerate(merged):
            if existing.finding_type != cand.finding_type:
                continue
            if not _compatible_titles(existing.title, cand.title):
                continue
            overlap_or_touch = existing.end_page_idx >= cand.start_page_idx - 1
            page_set_a = set(existing.page_ids)
            page_set_b = set(cand.page_ids)
            jaccard = _jaccard(page_set_a, page_set_b)
            if overlap_or_touch or jaccard >= 0.5:
                new_start = min(existing.start_page_idx, cand.start_page_idx)
                new_end = max(existing.end_page_idx, cand.end_page_idx)
                new_pages = tuple(
                    ordered_page_ids[new_start : new_end + 1],
                )
                new_conf = max(existing.confidence, cand.confidence)
                reasons = existing.reason
                if cand.reason and cand.reason not in reasons:
                    reasons = f"{reasons}; {cand.reason}" if reasons else cand.reason
                title = existing.title or cand.title
                merged[i] = RawDetection(
                    finding_type=existing.finding_type,
                    page_ids=new_pages,
                    start_page_idx=new_start,
                    end_page_idx=new_end,
                    confidence=new_conf,
                    reason=reasons[:2000],
                    title=title,
                    input_fingerprint=cand.input_fingerprint,
                    window_id=f"{existing.window_id}+{cand.window_id}",
                    raw=cand.raw,
                )
                placed = True
                break
        if not placed:
            merged.append(cand)

    # Dedupe pass for high Jaccard overlap
    deduped: list[RawDetection] = []
    for cand in sorted(merged, key=lambda r: (-r.confidence, -(r.end_page_idx - r.start_page_idx))):
        skip = False
        cand_set = set(cand.page_ids)
        for kept in deduped:
            if kept.finding_type != cand.finding_type:
                continue
            if _jaccard(set(kept.page_ids), cand_set) >= 0.5:
                skip = True
                break
        if not skip:
            deduped.append(cand)
    deduped.sort(key=lambda r: (r.start_page_idx, r.end_page_idx))
    return deduped


def raw_from_window_response(
    *,
    parsed: dict[str, Any],
    window_page_ids: tuple[str, ...],
    ordered_page_ids: list[str],
    finding_type: str,
    input_fingerprint: str,
    window_id: str,
) -> RawDetection | None:
    if not parsed.get("detected"):
        return None
    idx_map = {pid: i for i, pid in enumerate(ordered_page_ids)}
    win_indices = [idx_map[pid] for pid in window_page_ids if pid in idx_map]
    if not win_indices:
        return None
    win_start = min(win_indices)
    win_end = max(win_indices)

    if parsed.get("starts_on_this_window"):
        start_idx = win_start
    else:
        start_idx = win_start

    if parsed.get("continues_after"):
        end_idx = min(win_end + 1, len(ordered_page_ids) - 1)
    else:
        end_idx = win_end

    if parsed.get("continues_before") and start_idx > 0:
        start_idx = max(0, start_idx - 1)

    span_ids = tuple(ordered_page_ids[start_idx : end_idx + 1])
    title = parsed.get("title")
    return RawDetection(
        finding_type=finding_type,
        page_ids=span_ids,
        start_page_idx=start_idx,
        end_page_idx=end_idx,
        confidence=float(parsed.get("confidence") or 0.0),
        reason=str(parsed.get("reason") or ""),
        title=title if isinstance(title, str) else None,
        input_fingerprint=input_fingerprint,
        window_id=window_id,
        raw=parsed,
    )
