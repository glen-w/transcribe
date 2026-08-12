"""Deterministic grey scanner-bed border detection (Pillow-only)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PIL import Image


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


SCAN_BORDER_PARAMS = ScanBorderParams()


def _min_band_px(dim: int, params: ScanBorderParams) -> int:
    # ceil(1% of dim), floored via (dim + 99) // 100; at least 8
    return max(8, (dim + 99) // 100)


def _soft_max_band_px(dim: int, params: ScanBorderParams) -> int:
    """Hard upper bound for an edge band walk inside a grey bed.

    Leaves ``min_remaining_edge_px`` and respects the remaining-area fraction so a
    single edge cannot consume the page before the joint remaining-area check.
    """
    by_edge = max(0, dim - params.min_remaining_edge_px)
    by_frac = dim - (
        (dim * params.min_remaining_fraction_num) // params.min_remaining_fraction_den
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
    soft_max = _soft_max_band_px(dim, params)
    min_band = _min_band_px(dim, params)
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


def _inset_from_band(
    *,
    dim: int,
    k: int,
    params: ScanBorderParams,
    mu_band: float,
    mu_probe: float,
) -> int:
    min_band = _min_band_px(dim, params)
    if k < min_band:
        return 0
    if k >= _soft_max_band_px(dim, params):
        return 0
    if abs(mu_band - mu_probe) < params.min_mean_delta:
        return 0
    inset = k + params.paper_inset_px
    max_inset = dim - params.min_remaining_edge_px
    if max_inset < k:
        return 0
    if inset > max_inset:
        inset = max_inset
    return inset


def _interior_probe_span(remaining: int, params: ScanBorderParams) -> tuple[int, int]:
    """Return (offset, probe_width) into the page past a detected grey band.

    Prefers a full ``interior_probe_px`` window; shrinks the soft-shadow offset
    first when remaining interior is tight.
    """
    if remaining <= 0:
        return 0, 0
    offset = min(
        params.interior_probe_offset_px,
        max(0, remaining - params.interior_probe_px),
    )
    probe = min(params.interior_probe_px, remaining - offset)
    return offset, probe


def _edge_inset_left(gray: Image.Image, params: ScanBorderParams) -> int:
    width, _height = gray.size

    def sample(k: int) -> tuple[float, float]:
        return _strip_stats_vertical(gray, k)

    k = _walk_grey_band(dim=width, params=params, sample=sample)
    remaining = width - k
    offset, probe = _interior_probe_span(remaining, params)
    if probe <= 0:
        return 0
    mu_band = _region_mean_vertical(gray, 0, k)
    mu_probe = _region_mean_vertical(gray, k + offset, k + offset + probe)
    return _inset_from_band(
        dim=width, k=k, params=params, mu_band=mu_band, mu_probe=mu_probe
    )


def _edge_inset_right(gray: Image.Image, params: ScanBorderParams) -> int:
    width, _height = gray.size

    def sample(k: int) -> tuple[float, float]:
        return _strip_stats_vertical(gray, width - 1 - k)

    k = _walk_grey_band(dim=width, params=params, sample=sample)
    remaining = width - k
    offset, probe = _interior_probe_span(remaining, params)
    if probe <= 0:
        return 0
    mu_band = _region_mean_vertical(gray, width - k, width)
    mu_probe = _region_mean_vertical(
        gray, width - k - offset - probe, width - k - offset
    )
    return _inset_from_band(
        dim=width, k=k, params=params, mu_band=mu_band, mu_probe=mu_probe
    )


def _edge_inset_top(gray: Image.Image, params: ScanBorderParams) -> int:
    _width, height = gray.size

    def sample(k: int) -> tuple[float, float]:
        return _strip_stats_horizontal(gray, k)

    k = _walk_grey_band(dim=height, params=params, sample=sample)
    remaining = height - k
    offset, probe = _interior_probe_span(remaining, params)
    if probe <= 0:
        return 0
    mu_band = _region_mean_horizontal(gray, 0, k)
    mu_probe = _region_mean_horizontal(gray, k + offset, k + offset + probe)
    return _inset_from_band(
        dim=height, k=k, params=params, mu_band=mu_band, mu_probe=mu_probe
    )


def _edge_inset_bottom(gray: Image.Image, params: ScanBorderParams) -> int:
    _width, height = gray.size

    def sample(k: int) -> tuple[float, float]:
        return _strip_stats_horizontal(gray, height - 1 - k)

    k = _walk_grey_band(dim=height, params=params, sample=sample)
    remaining = height - k
    offset, probe = _interior_probe_span(remaining, params)
    if probe <= 0:
        return 0
    mu_band = _region_mean_horizontal(gray, height - k, height)
    mu_probe = _region_mean_horizontal(
        gray, height - k - offset - probe, height - k - offset
    )
    return _inset_from_band(
        dim=height, k=k, params=params, mu_band=mu_band, mu_probe=mu_probe
    )


def detect_scan_border_insets(
    gray: Image.Image, params: ScanBorderParams = SCAN_BORDER_PARAMS
) -> tuple[tuple[int, int, int, int] | None, str]:
    """Return (left, top, right, bottom) insets or None with noop reason.

    ``gray`` must be mode ``L``.
    """
    if gray.mode != "L":
        raise ValueError(f"expected mode L, got {gray.mode!r}")
    width, height = gray.size
    if width < params.min_dimension_px or height < params.min_dimension_px:
        return None, "noop: image below minimum dimension"

    left = _edge_inset_left(gray, params)
    right = _edge_inset_right(gray, params)
    top = _edge_inset_top(gray, params)
    bottom = _edge_inset_bottom(gray, params)

    if left == 0 and right == 0 and top == 0 and bottom == 0:
        return None, "noop: no border detected"

    rem_w = width - left - right
    rem_h = height - top - bottom
    min_w = max(
        params.min_remaining_edge_px,
        (width * params.min_remaining_fraction_num)
        // params.min_remaining_fraction_den,
    )
    min_h = max(
        params.min_remaining_edge_px,
        (height * params.min_remaining_fraction_num)
        // params.min_remaining_fraction_den,
    )
    if rem_w < min_w or rem_h < min_h:
        return None, "noop: remaining area below limit"

    # aspect = rem_w / rem_h compared to [1/5, 5/1] via cross-multiply
    if rem_h <= 0 or rem_w <= 0:
        return None, "noop: remaining area below limit"
    if rem_w * params.aspect_min_den < rem_h * params.aspect_min_num:
        return None, "noop: aspect ratio out of range"
    if rem_w * params.aspect_max_den > rem_h * params.aspect_max_num:
        return None, "noop: aspect ratio out of range"

    return (left, top, right, bottom), ""
