"""Review scan decode is cached across lane ticks."""

from __future__ import annotations

from pathlib import Path


def test_open_review_scan_is_cached(tmp_path: Path) -> None:
    from PIL import Image

    from transcribe.ui.review_workbench import _open_review_scan, _open_review_scan_cached

    path = tmp_path / "scan.png"
    Image.new("RGB", (8, 8), "white").save(path)
    _open_review_scan_cached.cache_clear()
    first = _open_review_scan(path, 0)
    miss = _open_review_scan_cached.cache_info()
    second = _open_review_scan(path, 0)
    hit = _open_review_scan_cached.cache_info()
    rotated = _open_review_scan(path, 1)
    assert first is second
    assert miss.misses == 1 and miss.hits == 0
    assert hit.hits == 1
    assert rotated is not first
    assert rotated.size[0] == 8
