"""Detection aggregation property tests."""

from __future__ import annotations

from transcribe.detection.aggregate import RawDetection, merge_adjacent_spans


def _raw(start: int, end: int, conf: float, page_ids: list[str], wid: str) -> RawDetection:
    return RawDetection(
        finding_type="poetry",
        page_ids=tuple(page_ids),
        start_page_idx=start,
        end_page_idx=end,
        confidence=conf,
        reason="poem",
        title=None,
        input_fingerprint="fp",
        window_id=wid,
        raw={},
    )


def test_overlap_windows_merge_to_one():
    ordered = ["p0", "p1", "p2", "p3"]
    hits = [
        _raw(0, 1, 0.8, ["p0", "p1"], "w1"),
        _raw(1, 2, 0.85, ["p1", "p2"], "w2"),
    ]
    merged = merge_adjacent_spans(hits, ordered_page_ids=ordered, confidence_threshold=0.7)
    assert len(merged) == 1
    assert merged[0].page_ids == ("p0", "p1", "p2")


def test_dedupe_high_jaccard_overlap():
    ordered = ["p0", "p1", "p2"]
    hits = [
        _raw(0, 2, 0.9, ["p0", "p1", "p2"], "w1"),
        _raw(0, 2, 0.75, ["p0", "p1", "p2"], "w2"),
    ]
    merged = merge_adjacent_spans(hits, ordered_page_ids=ordered, confidence_threshold=0.7)
    assert len(merged) == 1
    assert merged[0].confidence == 0.9


def test_below_threshold_filtered():
    ordered = ["p0"]
    hits = [_raw(0, 0, 0.3, ["p0"], "w1")]
    merged = merge_adjacent_spans(hits, ordered_page_ids=ordered, confidence_threshold=0.7)
    assert merged == []
