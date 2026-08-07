"""Optional image preprocessing (off by default)."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps

PREPROCESS_VERSION = 1


def apply_preprocess(image_bytes: bytes, profile: str) -> bytes:
    if profile in ("", "none"):
        return image_bytes
    if profile != "gentle_contrast":
        raise ValueError(f"unknown preprocess profile: {profile!r}")
    image = Image.open(BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image)
    image = ImageOps.grayscale(image)
    image = ImageOps.autocontrast(image)
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()
