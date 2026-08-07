from __future__ import annotations

from io import BytesIO

from PIL import Image

from transcribe.preprocess import apply_preprocess


def test_gentle_contrast_changes_bytes():
    buf = BytesIO()
    Image.new("RGB", (32, 32), (10, 10, 10)).save(buf, format="PNG")
    raw = buf.getvalue()
    out = apply_preprocess(raw, "gentle_contrast")
    assert out != raw
    assert apply_preprocess(raw, "none") == raw
