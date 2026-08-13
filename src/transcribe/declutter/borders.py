"""Deterministic scanner-bed and stark-white overscan border detection (Pillow-only)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from PIL import Image

Edge = Literal["left", "right", "top", "bottom"]


@dataclass(frozen=True)
class ScanBorderParams:
    min_dimension_px: int = 64
    grey_mean_min: int = 40
    grey_mean_max: int = 200
    max_strip_variance: float = 100.0
    # When a strip mean stays bed-like but variance spikes (scanner texture /
    # JPEG noise), keep walking until variance reaches this paper-like floor
    # or mean leaves the grey band. Handwriting/ruled paper is typically >>2e3.
    noisy_bed_variance_max: float = 800.0
    interior_probe_px: int = 16
    # Skip soft page-edge shadow between bed and bright paper before probing.
    # Immediate adjacent probes often sit in the transition and fail min_mean_delta
    # even when a clear grey bed is present (common on flatbed overscan).
    interior_probe_offset_px: int = 32
    min_mean_delta: float = 25.0
    paper_inset_px: int = 2
    min_remaining_fraction_num: int = 70
    min_remaining_fraction_den: int = 100
    min_remaining_edge_px: int = 32
    aspect_min_num: int = 1
    aspect_min_den: int = 5
    aspect_max_num: int = 5
    aspect_max_den: int = 1
    # Soft search budget retained in frozen param identity (legacy / journal compat).
    max_band_cap_px: int = 400


@dataclass(frozen=True)
class UniformOverscanParams:
    """Stark-white blank overscan / letterbox gutter (not grey scanner bed)."""

    min_dimension_px: int = 64
    # Stark white only (#FFFFFF gutters / scanner software pads). Keep this high
    # so near-white paper (e.g. L≈252) is not walked as overscan until content.
    # Cream paper (~240) fails white_mean_min and relies on min_mean_delta vs 255.
    white_mean_min: int = 254
    max_strip_variance: float = 100.0
    interior_probe_px: int = 16
    interior_probe_offset_px: int = 32
    # Cream (~240) vs stark white (255) is ~15; keep this below that gap.
    min_mean_delta: float = 12.0
    paper_inset_px: int = 2
    min_remaining_fraction_num: int = 70
    min_remaining_fraction_den: int = 100
    min_remaining_edge_px: int = 32
    aspect_min_num: int = 1
    aspect_min_den: int = 5
    aspect_max_num: int = 5
    aspect_max_den: int = 1
    max_band_cap_px: int = 400


SCAN_BORDER_PARAMS = ScanBorderParams()
UNIFORM_OVERSCAN_PARAMS = UniformOverscanParams()

# Multi-pass budget: L-shaped grey+white overscan needs a second crop after the
# first edge type is removed so full-strip stats become uniform again.
_MAX_BORDER_PASSES = 4


def _min_band_px(dim: int) -> int:
    # ceil(1% of dim), floored via (dim + 99) // 100; at least 8
    return max(8, (dim + 99) // 100)


def _soft_max_band_px(
    dim: int,
    *,
    min_remaining_edge_px: int,
    min_remaining_fraction_num: int,
    min_remaining_fraction_den: int,
) -> int:
    """Hard upper bound for an edge band walk.

    Leaves ``min_remaining_edge_px`` and respects the remaining-area fraction so a
    single edge cannot consume the page before the joint remaining-area check.
    """
    by_edge = max(0, dim - min_remaining_edge_px)
    by_frac = dim - (
        (dim * min_remaining_fraction_num) // min_remaining_fraction_den
    )
    return min(by_edge, by_frac)


def _histogram_mean_var(hist: list[int]) -> tuple[float, float]:
    n = sum(hist)
    if n == 0:
        return 0.0, 0.0
    mean = sum(i * hist[i] for i in range(256)) / n
    var = sum(hist[i] * (i - mean) ** 2 for i in range(256)) / n
    return mean, var


def _strip_stats_vertical(gray: Image.Image, x: int) -> tuple[float, float]:
    """Mean and population variance for column x (full height)."""
    height = gray.size[1]
    hist = gray.crop((x, 0, x + 1, height)).histogram()[:256]
    return _histogram_mean_var(hist)


def _strip_stats_horizontal(gray: Image.Image, y: int) -> tuple[float, float]:
    width = gray.size[0]
    hist = gray.crop((0, y, width, y + 1)).histogram()[:256]
    return _histogram_mean_var(hist)


def _region_mean_vertical(gray: Image.Image, x0: int, x1: int) -> float:
    """Mean of columns [x0, x1)."""
    if x1 <= x0:
        return 0.0
    height = gray.size[1]
    hist = gray.crop((x0, 0, x1, height)).histogram()[:256]
    mean, _var = _histogram_mean_var(hist)
    return mean


def _region_mean_horizontal(gray: Image.Image, y0: int, y1: int) -> float:
    if y1 <= y0:
        return 0.0
    width = gray.size[0]
    hist = gray.crop((0, y0, width, y1)).histogram()[:256]
    mean, _var = _histogram_mean_var(hist)
    return mean


def _is_scanner_grey(mean: float, var: float, params: ScanBorderParams) -> bool:
    return (
        params.grey_mean_min <= mean <= params.grey_mean_max
        and var <= params.max_strip_variance
    )


def _mean_in_grey_range(mean: float, params: ScanBorderParams) -> bool:
    return params.grey_mean_min <= mean <= params.grey_mean_max


def _is_noisy_bed(mean: float, var: float, params: ScanBorderParams) -> bool:
    """Bed-like mean with elevated variance (texture / compression), not paper."""
    return (
        _mean_in_grey_range(mean, params)
        and var <= params.noisy_bed_variance_max
    )


def _is_stark_white(mean: float, var: float, params: UniformOverscanParams) -> bool:
    return mean >= params.white_mean_min and var <= params.max_strip_variance


def _walk_grey_band(
    *,
    dim: int,
    params: ScanBorderParams,
    sample: Callable[[int], tuple[float, float]],
) -> int:
    """Walk from the edge while columns/rows look like scanner grey.

    Continues up to ``soft_max`` (remaining-area safe). After the strict
    low-variance walk stops, tolerates noisy bed strips whose mean remains grey
    so JPEG/scanner texture does not truncate the band early.
    """
    soft_max = _soft_max_band_px(
        dim,
        min_remaining_edge_px=params.min_remaining_edge_px,
        min_remaining_fraction_num=params.min_remaining_fraction_num,
        min_remaining_fraction_den=params.min_remaining_fraction_den,
    )
    min_band = _min_band_px(dim)
    k = 0
    while k < soft_max:
        mean, var = sample(k)
        if _is_scanner_grey(mean, var, params):
            k += 1
            continue
        # Strict grey ended. Allow noisy continuation only once we already have a
        # band and only while mean stays bed-like below the paper-variance floor.
        if k >= min_band and _is_noisy_bed(mean, var, params):
            k += 1
            continue
        break
    return k


def _walk_white_band(
    *,
    dim: int,
    params: UniformOverscanParams,
    sample: Callable[[int], tuple[float, float]],
) -> int:
    """Walk from the edge while columns/rows are stark uniform white."""
    soft_max = _soft_max_band_px(
        dim,
        min_remaining_edge_px=params.min_remaining_edge_px,
        min_remaining_fraction_num=params.min_remaining_fraction_num,
        min_remaining_fraction_den=params.min_remaining_fraction_den,
    )
    k = 0
    while k < soft_max:
        mean, var = sample(k)
        if _is_stark_white(mean, var, params):
            k += 1
            continue
        break
    return k


def _inset_from_band(
    *,
    dim: int,
    k: int,
    min_mean_delta: float,
    paper_inset_px: int,
    min_remaining_edge_px: int,
    min_remaining_fraction_num: int,
    min_remaining_fraction_den: int,
    mu_band: float,
    mu_probe: float,
) -> int:
    min_band = _min_band_px(dim)
    if k < min_band:
        return 0
    soft_max = _soft_max_band_px(
        dim,
        min_remaining_edge_px=min_remaining_edge_px,
        min_remaining_fraction_num=min_remaining_fraction_num,
        min_remaining_fraction_den=min_remaining_fraction_den,
    )
    if k >= soft_max:
        return 0
    if abs(mu_band - mu_probe) < min_mean_delta:
        return 0
    inset = k + paper_inset_px
    max_inset = dim - min_remaining_edge_px
    if max_inset < k:
        return 0
    if inset > max_inset:
        inset = max_inset
    return inset


def _interior_probe_span(
    remaining: int, *, interior_probe_px: int, interior_probe_offset_px: int
) -> tuple[int, int]:
    """Return (offset, probe_width) into the page past a detected band.

    Prefers a full ``interior_probe_px`` window; shrinks the soft-shadow offset
    first when remaining interior is tight.
    """
    if remaining <= 0:
        return 0, 0
    offset = min(
        interior_probe_offset_px,
        max(0, remaining - interior_probe_px),
    )
    probe = min(interior_probe_px, remaining - offset)
    return offset, probe


def _edge_inset(
    gray: Image.Image,
    edge: Edge,
    *,
    walk: Callable[..., int],
    walk_params: ScanBorderParams | UniformOverscanParams,
) -> int:
    width, height = gray.size
    dim = width if edge in ("left", "right") else height

    if edge == "left":

        def sample(k: int) -> tuple[float, float]:
            return _strip_stats_vertical(gray, k)

        def band_mean(k: int) -> float:
            return _region_mean_vertical(gray, 0, k)

        def probe_mean(k: int, offset: int, probe: int) -> float:
            return _region_mean_vertical(gray, k + offset, k + offset + probe)

    elif edge == "right":

        def sample(k: int) -> tuple[float, float]:
            return _strip_stats_vertical(gray, width - 1 - k)

        def band_mean(k: int) -> float:
            return _region_mean_vertical(gray, width - k, width)

        def probe_mean(k: int, offset: int, probe: int) -> float:
            return _region_mean_vertical(
                gray, width - k - offset - probe, width - k - offset
            )

    elif edge == "top":

        def sample(k: int) -> tuple[float, float]:
            return _strip_stats_horizontal(gray, k)

        def band_mean(k: int) -> float:
            return _region_mean_horizontal(gray, 0, k)

        def probe_mean(k: int, offset: int, probe: int) -> float:
            return _region_mean_horizontal(gray, k + offset, k + offset + probe)

    else:  # bottom

        def sample(k: int) -> tuple[float, float]:
            return _strip_stats_horizontal(gray, height - 1 - k)

        def band_mean(k: int) -> float:
            return _region_mean_horizontal(gray, height - k, height)

        def probe_mean(k: int, offset: int, probe: int) -> float:
            return _region_mean_horizontal(
                gray, height - k - offset - probe, height - k - offset
            )

    k = walk(dim=dim, params=walk_params, sample=sample)
    remaining = dim - k
    offset, probe = _interior_probe_span(
        remaining,
        interior_probe_px=walk_params.interior_probe_px,
        interior_probe_offset_px=walk_params.interior_probe_offset_px,
    )
    if probe <= 0:
        return 0
    return _inset_from_band(
        dim=dim,
        k=k,
        min_mean_delta=walk_params.min_mean_delta,
        paper_inset_px=walk_params.paper_inset_px,
        min_remaining_edge_px=walk_params.min_remaining_edge_px,
        min_remaining_fraction_num=walk_params.min_remaining_fraction_num,
        min_remaining_fraction_den=walk_params.min_remaining_fraction_den,
        mu_band=band_mean(k),
        mu_probe=probe_mean(k, offset, probe),
    )


def _validate_insets(
    width: int,
    height: int,
    left: int,
    top: int,
    right: int,
    bottom: int,
    *,
    min_remaining_edge_px: int,
    min_remaining_fraction_num: int,
    min_remaining_fraction_den: int,
    aspect_min_num: int,
    aspect_min_den: int,
    aspect_max_num: int,
    aspect_max_den: int,
) -> tuple[tuple[int, int, int, int] | None, str]:
    if left == 0 and right == 0 and top == 0 and bottom == 0:
        return None, "noop: no border detected"

    rem_w = width - left - right
    rem_h = height - top - bottom
    min_w = max(
        min_remaining_edge_px,
        (width * min_remaining_fraction_num) // min_remaining_fraction_den,
    )
    min_h = max(
        min_remaining_edge_px,
        (height * min_remaining_fraction_num) // min_remaining_fraction_den,
    )
    if rem_w < min_w or rem_h < min_h:
        return None, "noop: remaining area below limit"

    if rem_h <= 0 or rem_w <= 0:
        return None, "noop: remaining area below limit"
    if rem_w * aspect_min_den < rem_h * aspect_min_num:
        return None, "noop: aspect ratio out of range"
    if rem_w * aspect_max_den > rem_h * aspect_max_num:
        return None, "noop: aspect ratio out of range"

    return (left, top, right, bottom), ""


def detect_scan_border_insets(
    gray: Image.Image, params: ScanBorderParams = SCAN_BORDER_PARAMS
) -> tuple[tuple[int, int, int, int] | None, str]:
    """Return (left, top, right, bottom) grey-bed insets or None with noop reason.

    ``gray`` must be mode ``L``.
    """
    if gray.mode != "L":
        raise ValueError(f"expected mode L, got {gray.mode!r}")
    width, height = gray.size
    if width < params.min_dimension_px or height < params.min_dimension_px:
        return None, "noop: image below minimum dimension"

    left = _edge_inset(gray, "left", walk=_walk_grey_band, walk_params=params)
    right = _edge_inset(gray, "right", walk=_walk_grey_band, walk_params=params)
    top = _edge_inset(gray, "top", walk=_walk_grey_band, walk_params=params)
    bottom = _edge_inset(gray, "bottom", walk=_walk_grey_band, walk_params=params)

    return _validate_insets(
        width,
        height,
        left,
        top,
        right,
        bottom,
        min_remaining_edge_px=params.min_remaining_edge_px,
        min_remaining_fraction_num=params.min_remaining_fraction_num,
        min_remaining_fraction_den=params.min_remaining_fraction_den,
        aspect_min_num=params.aspect_min_num,
        aspect_min_den=params.aspect_min_den,
        aspect_max_num=params.aspect_max_num,
        aspect_max_den=params.aspect_max_den,
    )


def detect_white_border_insets(
    gray: Image.Image, params: UniformOverscanParams = UNIFORM_OVERSCAN_PARAMS
) -> tuple[tuple[int, int, int, int] | None, str]:
    """Return (left, top, right, bottom) stark-white overscan insets or None.

    ``gray`` must be mode ``L``.
    """
    if gray.mode != "L":
        raise ValueError(f"expected mode L, got {gray.mode!r}")
    width, height = gray.size
    if width < params.min_dimension_px or height < params.min_dimension_px:
        return None, "noop: image below minimum dimension"

    left = _edge_inset(gray, "left", walk=_walk_white_band, walk_params=params)
    right = _edge_inset(gray, "right", walk=_walk_white_band, walk_params=params)
    top = _edge_inset(gray, "top", walk=_walk_white_band, walk_params=params)
    bottom = _edge_inset(gray, "bottom", walk=_walk_white_band, walk_params=params)

    return _validate_insets(
        width,
        height,
        left,
        top,
        right,
        bottom,
        min_remaining_edge_px=params.min_remaining_edge_px,
        min_remaining_fraction_num=params.min_remaining_fraction_num,
        min_remaining_fraction_den=params.min_remaining_fraction_den,
        aspect_min_num=params.aspect_min_num,
        aspect_min_den=params.aspect_min_den,
        aspect_max_num=params.aspect_max_num,
        aspect_max_den=params.aspect_max_den,
    )


def _merge_insets(
    a: tuple[int, int, int, int] | None,
    b: tuple[int, int, int, int] | None,
) -> tuple[int, int, int, int]:
    aa = a or (0, 0, 0, 0)
    bb = b or (0, 0, 0, 0)
    return (
        max(aa[0], bb[0]),
        max(aa[1], bb[1]),
        max(aa[2], bb[2]),
        max(aa[3], bb[3]),
    )


def detect_declutter_border_insets(
    gray: Image.Image,
    *,
    scan_params: ScanBorderParams = SCAN_BORDER_PARAMS,
    overscan_params: UniformOverscanParams = UNIFORM_OVERSCAN_PARAMS,
) -> tuple[tuple[int, int, int, int] | None, str]:
    """Detect grey scanner-bed and stark-white overscan insets (multi-pass).

    L-shaped artefacts (e.g. grey bed on the right + white gutter on the bottom)
    make full-strip stats non-uniform on the shared corner. Cropping one edge
    type and re-detecting recovers the other. Insets are returned in original
    image coordinates.
    """
    if gray.mode != "L":
        raise ValueError(f"expected mode L, got {gray.mode!r}")
    orig_w, orig_h = gray.size
    if orig_w < scan_params.min_dimension_px or orig_h < scan_params.min_dimension_px:
        return None, "noop: image below minimum dimension"

    acc_left = acc_top = acc_right = acc_bottom = 0
    working = gray
    last_reason = "noop: no border detected"

    for _ in range(_MAX_BORDER_PASSES):
        grey_insets, grey_reason = detect_scan_border_insets(working, scan_params)
        white_insets, white_reason = detect_white_border_insets(
            working, overscan_params
        )
        merged = _merge_insets(grey_insets, white_insets)
        if merged == (0, 0, 0, 0):
            if grey_reason != "noop: no border detected":
                last_reason = grey_reason
            else:
                last_reason = white_reason
            break

        left, top, right, bottom = merged
        # Validate against the *original* frame with accumulated insets so a
        # later pass cannot violate remaining-area / aspect safety.
        trial = (
            acc_left + left,
            acc_top + top,
            acc_right + right,
            acc_bottom + bottom,
        )
        validated, reason = _validate_insets(
            orig_w,
            orig_h,
            trial[0],
            trial[1],
            trial[2],
            trial[3],
            min_remaining_edge_px=scan_params.min_remaining_edge_px,
            min_remaining_fraction_num=scan_params.min_remaining_fraction_num,
            min_remaining_fraction_den=scan_params.min_remaining_fraction_den,
            aspect_min_num=scan_params.aspect_min_num,
            aspect_min_den=scan_params.aspect_min_den,
            aspect_max_num=scan_params.aspect_max_num,
            aspect_max_den=scan_params.aspect_max_den,
        )
        if validated is None:
            last_reason = reason
            break

        acc_left, acc_top, acc_right, acc_bottom = validated
        w, h = working.size
        working = working.crop((left, top, w - right, h - bottom))
    else:
        last_reason = "noop: no border detected"

    if acc_left == 0 and acc_top == 0 and acc_right == 0 and acc_bottom == 0:
        return None, last_reason
    return (acc_left, acc_top, acc_right, acc_bottom), ""
