"""Partial calendar dates for archive metadata (not OCR/import timestamps)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


@dataclass(frozen=True)
class ApproximateDate:
    """User-owned diary/calendar date. Omit month/day when approximate."""

    year: int
    month: int | None = None
    day: int | None = None

    def __post_init__(self) -> None:
        if self.year < 1 or self.year > 9999:
            raise ValueError(f"invalid year: {self.year}")
        if self.month is not None and not (1 <= self.month <= 12):
            raise ValueError(f"invalid month: {self.month}")
        if self.day is not None:
            if self.month is None:
                raise ValueError("day requires month")
            # Validate via date construction (handles month lengths / leap years).
            date(self.year, self.month, self.day)

    @property
    def precision(self) -> str:
        if self.day is not None:
            return "day"
        if self.month is not None:
            return "month"
        return "year"

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"y": self.year}
        if self.month is not None:
            out["m"] = self.month
        if self.day is not None:
            out["d"] = self.day
        return out

    @classmethod
    def from_dict(cls, data: Any) -> ApproximateDate | None:
        if data is None:
            return None
        if not isinstance(data, dict):
            raise ValueError("date must be an object or null")
        if "y" not in data:
            return None
        return cls(
            year=int(data["y"]),
            month=int(data["m"]) if data.get("m") is not None else None,
            day=int(data["d"]) if data.get("d") is not None else None,
        )

    def sort_key(self) -> tuple[int, int, int]:
        """Ascending chronological key; missing parts sort early within precision."""
        return (self.year, self.month or 0, self.day or 0)

    def to_date_start(self) -> date:
        """Earliest calendar day covered by this approximate date."""
        return date(self.year, self.month or 1, self.day or 1)

    def to_date_end(self) -> date:
        """Latest calendar day covered by this approximate date."""
        if self.day is not None and self.month is not None:
            return date(self.year, self.month, self.day)
        if self.month is not None:
            if self.month == 12:
                return date(self.year, 12, 31)
            return date(self.year, self.month + 1, 1) - timedelta(days=1)
        return date(self.year, 12, 31)

    def format_display(self) -> str:
        if self.day is not None and self.month is not None:
            return f"{self.day:02d}/{self.month:02d}/{self.year}"
        if self.month is not None:
            return f"{self.month:02d}/{self.year}"
        return str(self.year)

    def bin_key(self, grain: str) -> str:
        """Stable timeline bin label for day/week/month/year grains."""
        start = self.to_date_start()
        if grain == "year":
            return f"{start.year:04d}"
        if grain == "month":
            return f"{start.year:04d}-{start.month:02d}"
        if grain == "week":
            iso = start.isocalendar()
            return f"{iso.year:04d}-W{iso.week:02d}"
        return start.isoformat()


def normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in tags:
        token = " ".join(str(raw).strip().lower().split())
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def inclusive_day_span(start: ApproximateDate, end: ApproximateDate) -> int | None:
    """Inclusive day count when both dates can form a meaningful span."""
    a = start.to_date_start()
    b = end.to_date_end()
    if b < a:
        return None
    return (b - a).days + 1


def pages_per_day(
    page_count: int, start: ApproximateDate | None, end: ApproximateDate | None
) -> float | None:
    if page_count <= 0 or start is None or end is None:
        return None
    span = inclusive_day_span(start, end)
    if span is None or span < 1:
        return None
    return round(page_count / span, 2)


def min_date(dates: list[ApproximateDate]) -> ApproximateDate | None:
    if not dates:
        return None
    return min(dates, key=lambda d: d.sort_key())


def max_date(dates: list[ApproximateDate]) -> ApproximateDate | None:
    if not dates:
        return None
    return max(dates, key=lambda d: d.sort_key())


def _bin_key_for_date(d: date, grain: str) -> str:
    if grain == "year":
        return f"{d.year:04d}"
    if grain == "month":
        return f"{d.year:04d}-{d.month:02d}"
    if grain == "week":
        iso = d.isocalendar()
        return f"{iso.year:04d}-W{iso.week:02d}"
    return d.isoformat()


def bin_key_to_date(key: str, grain: str) -> date:
    """Parse a bin key into a representative start date for charting."""
    if grain == "year":
        return date(int(key), 1, 1)
    if grain == "month":
        y, m = key.split("-", 1)
        return date(int(y), int(m), 1)
    if grain == "week":
        y, w = key.split("-W", 1)
        return date.fromisocalendar(int(y), int(w), 1)
    return date.fromisoformat(key)


def _advance_bin_start(d: date, grain: str) -> date:
    if grain == "year":
        return date(d.year + 1, 1, 1)
    if grain == "month":
        if d.month == 12:
            return date(d.year + 1, 1, 1)
        return date(d.year, d.month + 1, 1)
    if grain == "week":
        return d + timedelta(days=7)
    return d + timedelta(days=1)


def fill_bin_series(
    grain: str,
    span_start: date | ApproximateDate,
    span_end: date | ApproximateDate,
    counts: dict[str, int],
) -> list[tuple[str, int]]:
    """Return a complete calendar sequence of (bin_key, count), including zeros.

    Gaps between sparse activity become explicit zero bins so dormant periods
    remain visible on charts.
    """
    start = span_start.to_date_start() if isinstance(span_start, ApproximateDate) else span_start
    end = span_end.to_date_end() if isinstance(span_end, ApproximateDate) else span_end
    if end < start:
        return []
    # Align cursor to the start of the bin that contains ``start``.
    cursor = bin_key_to_date(_bin_key_for_date(start, grain), grain)
    end_key = _bin_key_for_date(end, grain)
    out: list[tuple[str, int]] = []
    # Safety cap for pathological spans (e.g. day grain over decades).
    max_bins = 4000
    while len(out) < max_bins:
        key = _bin_key_for_date(cursor, grain)
        out.append((key, int(counts.get(key, 0))))
        if key >= end_key:
            break
        cursor = _advance_bin_start(cursor, grain)
    return out
