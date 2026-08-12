"""Visual declutter: border contract, states, idempotence, adversarial fixtures."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from transcribe.declutter import (
    DECLUTTER_VERSION,
    ENABLED_OPS,
    apply_declutter,
    encode_declutter_png,
    identity_sha256_for,
)
from transcribe.declutter.borders import SCAN_BORDER_PARAMS, detect_scan_border_insets
from transcribe.domain.fingerprint import compute_input_fingerprint, sha256_bytes


def _png_bytes(image: Image.Image) -> bytes:
    buf = BytesIO()
    image.save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def _paper(width: int = 400, height: int = 500, *, fill: tuple[int, ...] = (245, 240, 230)) -> Image.Image:
    return Image.new("RGB", (width, height), fill)


def _with_right_grey_bed(
    paper: Image.Image, *, bed: int = 80, grey: tuple[int, int, int] = (128, 128, 128)
) -> Image.Image:
    w, h = paper.size
    canvas = Image.new("RGB", (w + bed, h), grey)
    canvas.paste(paper, (0, 0))
    return canvas


def test_disabled_preserves_bytes_exactly() -> None:
    src = _png_bytes(_paper())
    result = apply_declutter(src, enabled=False)
    assert result.state == "disabled"
    assert result.image_bytes is src
    assert result.ops == ()
    assert result.params == {}
    assert result.note == ""
    assert result.identity_sha256 == identity_sha256_for(enabled=False)


def test_noop_clean_paper_preserves_bytes() -> None:
    src = _png_bytes(_paper())
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_noop"
    assert result.image_bytes is src
    assert result.ops == ENABLED_OPS
    assert result.note
    assert result.inset_left == 0


def test_crops_uniform_right_grey_bed() -> None:
    paper = _paper(400, 500)
    ImageDraw.Draw(paper).rectangle((20, 20, 80, 80), fill=(30, 60, 180))
    src = _png_bytes(_with_right_grey_bed(paper, bed=80))
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_cropped"
    assert result.width < result.original_width
    assert result.inset_right > 0
    assert result.image_bytes != src
    # New right edge should not be solid scanner grey
    out = Image.open(BytesIO(result.image_bytes)).convert("L")
    col = [out.getpixel((out.size[0] - 1, y)) for y in range(out.size[1])]
    mean = sum(col) / len(col)
    assert not (40 <= mean <= 200 and abs(mean - 128) < 5)


def test_wide_grey_bed_beyond_max_band_cap_crops() -> None:
    """Beds wider than max_band_cap_px must still crop (real scanner overscan)."""
    paper = _paper(2000, 2400)
    ImageDraw.Draw(paper).rectangle((40, 40, 120, 120), fill=(30, 60, 180))
    # 450px bed > default max_band_cap_px (400); soft extension must find the edge.
    src = _png_bytes(_with_right_grey_bed(paper, bed=450, grey=(160, 160, 160)))
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_cropped"
    assert result.inset_right >= 450
    assert abs(result.width - 2000) <= SCAN_BORDER_PARAMS.paper_inset_px + 1


def test_noisy_mid_bed_variance_still_crops() -> None:
    """Slightly textured grey columns mid-bed must not abort detection early."""
    paper = _paper(800, 1000)
    ImageDraw.Draw(paper).rectangle((40, 40, 120, 120), fill=(30, 60, 180))
    bed = 120
    canvas = Image.new("RGB", (800 + bed, 1000), (150, 150, 150))
    canvas.paste(paper, (0, 0))
    # Inject moderate noise in a mid-bed strip (var ~200–600, still bed-like).
    for x in range(800 + 40, 800 + 80):
        for y in range(0, 1000, 3):
            canvas.putpixel((x, y), (130, 130, 130))
    src = _png_bytes(canvas)
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_cropped"
    assert result.inset_right >= bed


def test_soft_page_edge_shadow_still_crops() -> None:
    """Soft luminance ramp at page edge must not fail the interior mean-delta check.

    Real flatbed scans often have a ~20–40px transition; an immediate probe sits
    in that shadow and used to no-op despite a clear grey bed.
    """
    paper = _paper(800, 1000, fill=(250, 250, 250))
    ImageDraw.Draw(paper).rectangle((40, 40, 120, 120), fill=(30, 60, 180))
    bed = 100
    grey = (155, 155, 155)
    canvas = Image.new("RGB", (800 + bed, 1000), grey)
    canvas.paste(paper, (0, 0))
    # Soft shadow: blend last 32px of paper toward bed grey
    for x in range(800 - 32, 800):
        t = (x - (800 - 32)) / 32.0
        v = int(250 * (1 - t) + 155 * t)
        for y in range(1000):
            canvas.putpixel((x, y), (v, v, v))
    src = _png_bytes(canvas)
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_cropped"
    assert result.inset_right >= bed


def test_idempotent_on_successful_crop() -> None:
    src = _png_bytes(_with_right_grey_bed(_paper(400, 500), bed=80))
    first = apply_declutter(src, enabled=True)
    assert first.state == "enabled_cropped"
    second = apply_declutter(first.image_bytes, enabled=True)
    assert second.state == "enabled_noop"
    assert second.image_bytes == first.image_bytes


def test_deterministic_crop_bytes() -> None:
    src = _png_bytes(_with_right_grey_bed(_paper(400, 500), bed=80))
    a = apply_declutter(src, enabled=True)
    b = apply_declutter(src, enabled=True)
    assert a.state == "enabled_cropped"
    assert a.image_bytes == b.image_bytes
    assert sha256_bytes(a.image_bytes) == sha256_bytes(b.image_bytes)


def test_error_fallback_preserves_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    src = _png_bytes(_paper())

    def boom(*_a, **_k):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr("transcribe.declutter.detect_scan_border_insets", boom)
    result = apply_declutter(src, enabled=True)
    assert result.state == "error_fallback"
    assert result.image_bytes is src
    assert "RuntimeError" in result.note


def test_tiny_image_noop() -> None:
    src = _png_bytes(Image.new("RGB", (32, 32), (128, 128, 128)))
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_noop"
    assert result.image_bytes == src


def test_narrow_gutter_below_min_band_noop() -> None:
    # min_band for width 400 is max(8, 4) = 8; bed of 4 must noop
    paper = _paper(400, 500)
    src = _png_bytes(_with_right_grey_bed(paper, bed=4))
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_noop"
    assert result.image_bytes == src


def test_black_border_not_treated_as_scanner_grey() -> None:
    paper = _paper(400, 500)
    canvas = Image.new("RGB", (480, 500), (0, 0, 0))
    canvas.paste(paper, (0, 0))
    src = _png_bytes(canvas)
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_noop"


def test_dark_page_edge_noop() -> None:
    paper = Image.new("RGB", (400, 500), (20, 20, 20))
    src = _png_bytes(_with_right_grey_bed(paper, bed=80))
    # Grey bed vs dark paper should still crop if delta is large enough
    result = apply_declutter(src, enabled=True)
    assert result.state in {"enabled_cropped", "enabled_noop"}


def test_grey_paper_full_frame_noop() -> None:
    src = _png_bytes(Image.new("RGB", (400, 500), (128, 128, 128)))
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_noop"
    assert result.image_bytes == src


def test_photograph_busy_edges_noop() -> None:
    img = Image.new("RGB", (400, 500))
    pixels = img.load()
    for y in range(500):
        for x in range(400):
            pixels[x, y] = ((x * 17 + y * 13) % 256, (x * 3) % 256, (y * 5) % 256)
    src = _png_bytes(img)
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_noop"


def test_shadow_vignette_without_grey_bed_noop() -> None:
    img = Image.new("RGB", (400, 500), (245, 240, 230))
    draw = ImageDraw.Draw(img)
    for i in range(40):
        shade = 245 - i * 3
        draw.rectangle((i, i, 399 - i, 499 - i), outline=(shade, shade - 5, shade - 10))
    src = _png_bytes(img)
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_noop"


def test_asymmetric_beds_crop() -> None:
    paper = _paper(400, 500)
    canvas = Image.new("RGB", (500, 560), (140, 140, 140))
    canvas.paste(paper, (20, 30))
    src = _png_bytes(canvas)
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_cropped"
    assert result.inset_left > 0
    assert result.inset_top > 0
    assert result.inset_right > 0
    assert result.inset_bottom > 0


def test_rgba_mode_crop() -> None:
    paper = Image.new("RGBA", (400, 500), (245, 240, 230, 255))
    canvas = Image.new("RGBA", (480, 500), (128, 128, 128, 255))
    canvas.paste(paper, (0, 0))
    src = _png_bytes(canvas)
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_cropped"
    out = Image.open(BytesIO(result.image_bytes))
    assert out.mode == "RGBA"


def test_L_mode_crop() -> None:
    paper = Image.new("L", (400, 500), 245)
    canvas = Image.new("L", (480, 500), 128)
    canvas.paste(paper, (0, 0))
    src = _png_bytes(canvas)
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_cropped"
    assert Image.open(BytesIO(result.image_bytes)).mode == "L"


def test_P_mode_converts_on_crop() -> None:
    paper = Image.new("P", (400, 500))
    paper.putpalette([i // 3 for i in range(768)])
    # Build via RGB then quantize for a realistic P image with grey bed
    rgb = _with_right_grey_bed(_paper(400, 500), bed=80)
    p = rgb.quantize(colors=64)
    src = _png_bytes(p)
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_cropped"
    assert Image.open(BytesIO(result.image_bytes)).mode == "RGB"


def test_torn_edge_against_grey_still_crops() -> None:
    paper = _paper(400, 500)
    canvas = Image.new("RGB", (480, 500), (128, 128, 128))
    canvas.paste(paper, (0, 0))
    # Jagged white tear into the grey bed
    draw = ImageDraw.Draw(canvas)
    for y in range(0, 500, 7):
        draw.rectangle((395, y, 410, y + 3), fill=(250, 250, 245))
    src = _png_bytes(canvas)
    result = apply_declutter(src, enabled=True)
    # May crop or noop depending on strip variance from jagged edge; must not error
    assert result.state in {"enabled_cropped", "enabled_noop"}
    if result.state == "enabled_noop":
        assert result.image_bytes == src


def test_provenance_geometry_on_crop() -> None:
    src = _png_bytes(_with_right_grey_bed(_paper(400, 500), bed=80))
    result = apply_declutter(src, enabled=True)
    assert result.state == "enabled_cropped"
    prov = result.provenance_dict()
    assert prov["declutter_state"] == "enabled_cropped"
    assert prov["declutter_version"] == DECLUTTER_VERSION
    assert prov["declutter_original_width"] == 480
    assert prov["declutter_crop_right"] - prov["declutter_crop_left"] == result.width
    assert prov["declutter_inset_right"] > 0


def test_ocr_fingerprint_invalidates_on_crop_not_on_noop() -> None:
    clean = _png_bytes(_paper(400, 500))
    noop = apply_declutter(clean, enabled=True)
    assert noop.state == "enabled_noop"
    assert sha256_bytes(noop.image_bytes) == sha256_bytes(clean)

    bordered = _png_bytes(_with_right_grey_bed(_paper(400, 500), bed=80))
    cropped = apply_declutter(bordered, enabled=True)
    assert cropped.state == "enabled_cropped"
    assert sha256_bytes(cropped.image_bytes) != sha256_bytes(bordered)

    common = dict(
        provider="ollama",
        model_name="m",
        model_digest="d",
        model_identity_verified=True,
        prompt_sha256="p",
        preprocess_profile="none",
        preprocess_version=1,
        generation_options={},
    )
    fp_pre, _ = compute_input_fingerprint(
        input_sha256=sha256_bytes(bordered), **common
    )
    fp_post, _ = compute_input_fingerprint(
        input_sha256=sha256_bytes(cropped.image_bytes), **common
    )
    assert fp_pre != fp_post

    fp_clean, _ = compute_input_fingerprint(
        input_sha256=sha256_bytes(clean), **common
    )
    fp_noop, _ = compute_input_fingerprint(
        input_sha256=sha256_bytes(noop.image_bytes), **common
    )
    assert fp_clean == fp_noop


def test_encode_strips_info_dict() -> None:
    img = Image.new("RGB", (32, 32), (10, 20, 30))
    img.info["comment"] = "secret"
    a = encode_declutter_png(img)
    b = encode_declutter_png(Image.open(BytesIO(a)))
    assert a == b


def test_detect_insets_contract_helpers() -> None:
    gray = Image.new("L", (400, 500), 245)
    for x in range(320, 400):
        for y in range(500):
            gray.putpixel((x, y), 128)
    insets, reason = detect_scan_border_insets(gray, SCAN_BORDER_PARAMS)
    assert reason == ""
    assert insets is not None
    assert insets[2] >= SCAN_BORDER_PARAMS.paper_inset_px
