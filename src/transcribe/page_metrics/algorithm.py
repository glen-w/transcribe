"""Deterministic Pillow ink / blankness / hue classification (v1)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image

ALGORITHM_VERSION = "1"

InkHue = Literal[
    "black", "blue", "red", "brown", "green", "other", "mixed", "none"
]
PaperTone = Literal["white", "cream", "grey", "warm", "cool", "unknown"]

# Max long edge before downsample (keeps scans fast; identity uses render SHA, not pixels).
MAX_SIDE_PX = 800

# Luminance gap below paper median to count as ink (0–255 scale).
INK_LUMA_DELTA = 28
# Minimum chroma (approx max-min of RGB) to treat as chromatic ink vs grey ink.
CHROMA_INK_MIN = 18
# Near-grey ink → black label.
GREY_SAT_MAX = 0.22
# Hue histogram: require a clear peak vs runner-up.
MIXED_RATIO = 0.55


@dataclass(frozen=True)
class PageInkMetrics:
    ink_coverage_pct: float
    blankness_pct: float
    ink_hue: InkHue
    ink_hue_degrees: float | None
    paper_tone: PaperTone
    width: int
    height: int
    pixel_count: int
    ink_pixel_count: int
    algorithm_version: str = ALGORITHM_VERSION


def _luma(r: int, g: int, b: int) -> float:
    return 0.299 * r + 0.587 * g + 0.114 * b


def _chroma(r: int, g: int, b: int) -> int:
    return max(r, g, b) - min(r, g, b)


def _hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx = max(rf, gf, bf)
    mn = min(rf, gf, bf)
    diff = mx - mn
    if diff < 1e-9:
        h = 0.0
    elif mx == rf:
        h = (60 * ((gf - bf) / diff) + 360) % 360
    elif mx == gf:
        h = (60 * ((bf - rf) / diff) + 120) % 360
    else:
        h = (60 * ((rf - gf) / diff) + 240) % 360
    s = 0.0 if mx < 1e-9 else diff / mx
    return h, s, mx


def _hue_label(degrees: float) -> InkHue:
    # Wrap-friendly buckets for common pen inks.
    h = degrees % 360.0
    if h < 20 or h >= 340:
        return "red"
    if 20 <= h < 50:
        return "brown"
    if 50 <= h < 160:
        return "green"
    if 160 <= h < 260:
        return "blue"
    if 260 <= h < 340:
        return "red"
    return "other"


def _paper_tone_from_samples(samples: list[tuple[int, int, int]]) -> PaperTone:
    if not samples:
        return "unknown"
    # Use upper quartile of luminance as paper reference colour.
    ordered = sorted(samples, key=lambda p: _luma(*p))
    idx = max(0, int(len(ordered) * 0.75) - 1)
    r, g, b = ordered[idx]
    luma = _luma(r, g, b)
    chroma = _chroma(r, g, b)
    if luma >= 220 and chroma < 25:
        return "white"
    if luma >= 180 and chroma < 40 and r >= g >= b - 5:
        return "cream"
    if chroma < 20:
        return "grey"
    if r > b + 15:
        return "warm"
    if b > r + 15:
        return "cool"
    return "unknown"


def _prepare_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "P":
        work = image.convert("RGB")
    elif image.mode == "RGBA":
        bg = Image.new("RGB", image.size, (255, 255, 255))
        bg.paste(image, mask=image.split()[3])
        work = bg
    elif image.mode == "L":
        work = image.convert("RGB")
    elif image.mode != "RGB":
        work = image.convert("RGB")
    else:
        work = image
    w, h = work.size
    long_edge = max(w, h)
    if long_edge > MAX_SIDE_PX:
        scale = MAX_SIDE_PX / float(long_edge)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        work = work.resize((nw, nh), Image.Resampling.BILINEAR)
    return work


def _classify_hue(ink_rgb: list[tuple[int, int, int]]) -> tuple[InkHue, float | None]:
    if not ink_rgb:
        return "none", None
    grey = 0
    chromatic: list[float] = []
    for r, g, b in ink_rgb:
        h, s, _v = _hsv(r, g, b)
        if s <= GREY_SAT_MAX or _chroma(r, g, b) < CHROMA_INK_MIN:
            grey += 1
        else:
            chromatic.append(h)
    if not chromatic:
        return "black", None
    # Prefer black when most ink is near-grey.
    if grey >= len(chromatic) * 2 and grey >= len(ink_rgb) * 0.55:
        return "black", None
    labels = [_hue_label(h) for h in chromatic]
    counts = Counter(labels)
    top_label, top_n = counts.most_common(1)[0]
    second_n = counts.most_common(2)[1][1] if len(counts) > 1 else 0
    if top_n < max(3, int(len(chromatic) * 0.25)):
        return "mixed", None
    if second_n > 0 and top_n / (top_n + second_n) < MIXED_RATIO:
        return "mixed", None
    # Peak hue degrees among pixels of the winning label.
    peak_hues = [h for h, lab in zip(chromatic, labels) if lab == top_label]
    peak = sum(peak_hues) / len(peak_hues) if peak_hues else None
    return top_label, peak


def analyse_image(image: Image.Image) -> PageInkMetrics:
    """Classify ink coverage / blankness / dominant hue for one page image."""
    rgb = _prepare_rgb(image)
    pixels = list(rgb.getdata())
    width, height = rgb.size
    n = len(pixels)
    if n == 0:
        return PageInkMetrics(
            ink_coverage_pct=0.0,
            blankness_pct=100.0,
            ink_hue="none",
            ink_hue_degrees=None,
            paper_tone="unknown",
            width=width,
            height=height,
            pixel_count=0,
            ink_pixel_count=0,
        )

    lumas = [_luma(r, g, b) for r, g, b in pixels]
    ordered = sorted(lumas)
    paper_luma = ordered[int(len(ordered) * 0.70)]

    ink_rgb: list[tuple[int, int, int]] = []
    for (r, g, b), luma in zip(pixels, lumas):
        chroma = _chroma(r, g, b)
        is_ink = luma <= paper_luma - INK_LUMA_DELTA or (
            chroma >= CHROMA_INK_MIN and luma < paper_luma - 8
        )
        if is_ink:
            ink_rgb.append((r, g, b))

    ink_n = len(ink_rgb)
    coverage = round(100.0 * ink_n / n, 2)
    blankness = round(100.0 - coverage, 2)
    hue, hue_deg = _classify_hue(ink_rgb)
    # Sample for paper tone: brighter non-ink pixels.
    paper_samples = [
        px
        for px, luma in zip(pixels, lumas)
        if luma > paper_luma - INK_LUMA_DELTA / 2
    ]
    tone = _paper_tone_from_samples(paper_samples[:5000] or pixels[:5000])

    return PageInkMetrics(
        ink_coverage_pct=coverage,
        blankness_pct=blankness,
        ink_hue=hue,
        ink_hue_degrees=None if hue_deg is None else round(hue_deg, 1),
        paper_tone=tone,
        width=width,
        height=height,
        pixel_count=n,
        ink_pixel_count=ink_n,
    )


def analyse_image_bytes(data: bytes) -> PageInkMetrics:
    with Image.open(BytesIO(data)) as img:
        img.load()
        return analyse_image(img)


def analyse_image_path(path) -> PageInkMetrics:
    with Image.open(path) as img:
        img.load()
        return analyse_image(img)
