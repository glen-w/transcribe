"""Deterministic grey scanner-bed border detection (Pillow-only)."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class ScanBorderParams:
    min_dimension_px: int = 64
    grey_mean_min: int = 40
    grey_mean_max: int = 200
    max_strip_variance: float = 100.0
    interior_probe_px: int = 16
    min_mean_delta: float = 25.0
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


def _max_band_px(dim: int, params: ScanBorderParams) -> int:
    return min(dim // 4, params.max_band_cap_px)


def _min_band_px(dim: int, params: ScanBorderParams) -> int:
    # ceil(1% of dim), floored via (dim + 99) // 100; at least 8
    return max(8, (dim + 99) // 100)


def _strip_stats_vertical(gray: Image.Image, x: int) -> tuple[float, float]:
    """Mean and population variance for column x (full height)."""
    height = gray.size[1]
    pixels = [gray.getpixel((x, y)) for y in range(height)]
    n = len(pixels)
    if n == 0:
        return 0.0, 0.0
    mean = sum(pixels) / n
    var = sum((p - mean) ** 2 for p in pixels) / n
    return mean, var


def _strip_stats_horizontal(gray: Image.Image, y: int) -> tuple[float, float]:
    width = gray.size[0]
    pixels = [gray.getpixel((x, y)) for x in range(width)]
    n = len(pixels)
    if n == 0:
        return 0.0, 0.0
    mean = sum(pixels) / n
    var = sum((p - mean) ** 2 for p in pixels) / n
    return mean, var


def _region_mean_vertical(gray: Image.Image, x0: int, x1: int) -> float:
    """Mean of columns [x0, x1)."""
    height = gray.size[1]
    total = 0.0
    count = 0
    for x in range(x0, x1):
        for y in range(height):
            total += gray.getpixel((x, y))
            count += 1
    return total / count if count else 0.0


def _region_mean_horizontal(gray: Image.Image, y0: int, y1: int) -> float:
    width = gray.size[0]
    total = 0.0
    count = 0
    for y in range(y0, y1):
        for x in range(width):
            total += gray.getpixel((x, y))
            count += 1
    return total / count if count else 0.0


def _is_scanner_grey(mean: float, var: float, params: ScanBorderParams) -> bool:
    return (
        params.grey_mean_min <= mean <= params.grey_mean_max
        and var <= params.max_strip_variance
    )


def _edge_inset_left(gray: Image.Image, params: ScanBorderParams) -> int:
    width, _height = gray.size
    max_band = _max_band_px(width, params)
    min_band = _min_band_px(width, params)
    k = 0
    while k < max_band:
        mean, var = _strip_stats_vertical(gray, k)
        if not _is_scanner_grey(mean, var, params):
            break
        k += 1
    if k < min_band:
        return 0
    remaining = width - k
    if remaining <= 0:
        return 0
    probe = min(params.interior_probe_px, remaining)
    mu_band = _region_mean_vertical(gray, 0, k)
    mu_probe = _region_mean_vertical(gray, k, k + probe)
    if abs(mu_band - mu_probe) < params.min_mean_delta:
        return 0
    inset = k + params.paper_inset_px
    # Clamp so this edge alone would leave min_remaining_edge_px
    max_inset = width - params.min_remaining_edge_px
    if max_inset < k:
        return 0
    if inset > max_inset:
        inset = max_inset
    return inset


def _edge_inset_right(gray: Image.Image, params: ScanBorderParams) -> int:
    width, _height = gray.size
    max_band = _max_band_px(width, params)
    min_band = _min_band_px(width, params)
    k = 0
    while k < max_band:
        x = width - 1 - k
        mean, var = _strip_stats_vertical(gray, x)
        if not _is_scanner_grey(mean, var, params):
            break
        k += 1
    if k < min_band:
        return 0
    remaining = width - k
    if remaining <= 0:
        return 0
    probe = min(params.interior_probe_px, remaining)
    mu_band = _region_mean_vertical(gray, width - k, width)
    mu_probe = _region_mean_vertical(gray, width - k - probe, width - k)
    if abs(mu_band - mu_probe) < params.min_mean_delta:
        return 0
    inset = k + params.paper_inset_px
    max_inset = width - params.min_remaining_edge_px
    if max_inset < k:
        return 0
    if inset > max_inset:
        inset = max_inset
    return inset


def _edge_inset_top(gray: Image.Image, params: ScanBorderParams) -> int:
    _width, height = gray.size
    max_band = _max_band_px(height, params)
    min_band = _min_band_px(height, params)
    k = 0
    while k < max_band:
        mean, var = _strip_stats_horizontal(gray, k)
        if not _is_scanner_grey(mean, var, params):
            break
        k += 1
    if k < min_band:
        return 0
    remaining = height - k
    if remaining <= 0:
        return 0
    probe = min(params.interior_probe_px, remaining)
    mu_band = _region_mean_horizontal(gray, 0, k)
    mu_probe = _region_mean_horizontal(gray, k, k + probe)
    if abs(mu_band - mu_probe) < params.min_mean_delta:
        return 0
    inset = k + params.paper_inset_px
    max_inset = height - params.min_remaining_edge_px
    if max_inset < k:
        return 0
    if inset > max_inset:
        inset = max_inset
    return inset


def _edge_inset_bottom(gray: Image.Image, params: ScanBorderParams) -> int:
    _width, height = gray.size
    max_band = _max_band_px(height, params)
    min_band = _min_band_px(height, params)
    k = 0
    while k < max_band:
        y = height - 1 - k
        mean, var = _strip_stats_horizontal(gray, y)
        if not _is_scanner_grey(mean, var, params):
            break
        k += 1
    if k < min_band:
        return 0
    remaining = height - k
    if remaining <= 0:
        return 0
    probe = min(params.interior_probe_px, remaining)
    mu_band = _region_mean_horizontal(gray, height - k, height)
    mu_probe = _region_mean_horizontal(gray, height - k - probe, height - k)
    if abs(mu_band - mu_probe) < params.min_mean_delta:
        return 0
    inset = k + params.paper_inset_px
    max_inset = height - params.min_remaining_edge_px
    if max_inset < k:
        return 0
    if inset > max_inset:
        inset = max_inset
    return inset


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
