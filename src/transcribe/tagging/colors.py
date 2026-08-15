"""Tag colour helpers — host-agnostic (stdlib only).

Copy-boundary: this module may be copied into TranscriptX. Do not import
``transcribe.*`` or ``transcriptx.*``.
"""

from __future__ import annotations

import hashlib
import re

# GitHub-like label palette (stable, colourblind-friendly-ish defaults).
DEFAULT_PALETTE: tuple[str, ...] = (
    "#1d76db",
    "#0e8a16",
    "#b60205",
    "#d93f0b",
    "#fbca04",
    "#5319e7",
    "#006b75",
    "#0052cc",
    "#e99695",
    "#f9d0c4",
    "#fef2c0",
    "#c2e0c6",
    "#bfdadc",
    "#c5def5",
    "#d4c5f9",
    "#735c0f",
)

_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$")


def parse_hex_color(value: str) -> str:
    """Return canonical ``#rrggbb``. Raises ValueError if not a hex colour."""
    text = str(value).strip()
    if not _HEX_RE.fullmatch(text):
        raise ValueError(f"invalid hex colour: {value!r}")
    text = text.removeprefix("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    return "#" + text.lower()


def default_color_for_slug(slug: str) -> str:
    """Deterministic palette colour so the same slug always looks the same."""
    digest = hashlib.sha256(slug.encode("utf-8")).digest()
    return DEFAULT_PALETTE[digest[0] % len(DEFAULT_PALETTE)]


def _linear(channel: int) -> float:
    x = channel / 255.0
    if x <= 0.04045:
        return x / 12.92
    return ((x + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    parsed = parse_hex_color(hex_color)
    r = int(parsed[1:3], 16)
    g = int(parsed[3:5], 16)
    b = int(parsed[5:7], 16)
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast_text_color(background: str) -> str:
    """Dark text on light pills, white text on dark pills."""
    try:
        lum = relative_luminance(background)
    except ValueError:
        return "#ffffff"
    return "#111111" if lum > 0.45 else "#ffffff"
