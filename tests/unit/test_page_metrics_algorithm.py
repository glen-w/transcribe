"""Offline unit coverage for Pillow page ink / blankness / hue metrics."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from transcribe.page_metrics.algorithm import (
    ALGORITHM_VERSION,
    analyse_image,
    analyse_image_bytes,
)


def _png(image: Image.Image) -> bytes:
    buf = BytesIO()
    image.save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def _paper(width: int = 200, height: int = 260, fill=(245, 240, 230)) -> Image.Image:
    return Image.new("RGB", (width, height), fill)


def test_blank_page_is_mostly_blank() -> None:
    metrics = analyse_image(_paper())
    assert metrics.algorithm_version == ALGORITHM_VERSION
    assert metrics.ink_coverage_pct < 2.0
    assert metrics.blankness_pct > 98.0
    assert metrics.ink_hue == "none"
    assert metrics.paper_tone in ("cream", "white", "warm")


def test_dense_blue_ink_reports_high_coverage_and_blue() -> None:
    img = _paper()
    draw = ImageDraw.Draw(img)
    # Dense scribbles covering a large fraction of the page.
    for y in range(20, 240, 4):
        draw.line((15, y, 185, y + 2), fill=(20, 50, 180), width=3)
    metrics = analyse_image(img)
    assert metrics.ink_coverage_pct > 15.0
    assert metrics.blankness_pct < 85.0
    assert metrics.ink_hue == "blue"
    assert metrics.ink_hue_degrees is not None


def test_red_ink_label() -> None:
    img = _paper()
    draw = ImageDraw.Draw(img)
    for y in range(30, 220, 5):
        draw.line((20, y, 180, y), fill=(190, 25, 30), width=4)
    metrics = analyse_image(img)
    assert metrics.ink_coverage_pct > 8.0
    assert metrics.ink_hue == "red"


def test_black_ink_near_grey() -> None:
    img = _paper(fill=(250, 250, 250))
    draw = ImageDraw.Draw(img)
    for y in range(25, 230, 4):
        draw.line((18, y, 182, y), fill=(25, 25, 25), width=3)
    metrics = analyse_image(img)
    assert metrics.ink_coverage_pct > 10.0
    assert metrics.ink_hue == "black"
    assert metrics.ink_hue_degrees is None


def test_analyse_image_bytes_matches_image() -> None:
    img = _paper()
    ImageDraw.Draw(img).rectangle((40, 40, 120, 160), fill=(30, 90, 40))
    a = analyse_image(img)
    b = analyse_image_bytes(_png(img))
    assert a.ink_coverage_pct == b.ink_coverage_pct
    assert a.ink_hue == b.ink_hue
    assert a.blankness_pct == b.blankness_pct


def test_sparse_vs_dense_ordering() -> None:
    sparse = _paper()
    ImageDraw.Draw(sparse).line((40, 40, 160, 40), fill=(10, 10, 10), width=2)
    dense = _paper()
    d = ImageDraw.Draw(dense)
    for y in range(10, 250, 3):
        d.line((10, y, 190, y), fill=(10, 10, 10), width=2)
    assert analyse_image(dense).ink_coverage_pct > analyse_image(sparse).ink_coverage_pct
