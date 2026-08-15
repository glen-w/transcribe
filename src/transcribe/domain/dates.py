"""Partial calendar dates for archive metadata (not OCR/import timestamps)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Sequence

DATE_SOURCE_EXTRACTED = "extracted"
DATE_SOURCE_INHERITED = "inherited"
DATE_SOURCES = frozenset({DATE_SOURCE_EXTRACTED, DATE_SOURCE_INHERITED})

# Compact YYMMDD / bare YYYY only considered in this early window.
_EARLY_TEXT_MAX_CHARS = 280
_EARLY_TEXT_MAX_LINES = 5

# Auto-extract only diary-plausible calendar years (rejects page numbers / codes).
_EXTRACT_YEAR_MIN = 1900
_EXTRACT_YEAR_FUTURE_SLACK = 1

_PRECISION_RANK = {"day": 3, "month": 2, "year": 1}

# pattern_id used only as final tie-break (lower wins).
_PAT_YYMMDD = 0
_PAT_YMD = 1
_PAT_DMY = 2
_PAT_YM = 3
_PAT_MY = 4
_PAT_YEAR = 5
_PAT_DMY_YY = 6
_PAT_YMD_YY = 7
_PAT_MONTH_NAME_DAY = 8
_PAT_MONTH_NAME_MONTH = 9

_MONTH_NAME_TO_NUM: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
# Longer names first so "September" wins over "Sep".
_MONTH_NAME_ALT = "|".join(sorted(_MONTH_NAME_TO_NUM.keys(), key=len, reverse=True))
_MONTH_NAME_RE = rf"(?:{_MONTH_NAME_ALT})"
_ORDINAL_SUFFIX_RE = r"(?:st|nd|rd|th)?"


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

    def clearly_before(self, other: ApproximateDate) -> bool:
        """True when this date's range ends before ``other`` begins (no overlap)."""
        return self.to_date_end() < other.to_date_start()

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


def expand_yy(yy: int) -> int:
    """Century pivot: YY >= 70 → 19YY, else 20YY."""
    if yy < 0 or yy > 99:
        raise ValueError(f"invalid YY: {yy}")
    return 1900 + yy if yy >= 70 else 2000 + yy


@dataclass(frozen=True)
class DateRegression:
    """A notebook page whose date is clearly earlier than a prior dated page."""

    page_number: int  # 1-based notebook order
    page_id: str
    date: ApproximateDate
    previous_page_number: int
    previous_page_id: str
    previous_date: ApproximateDate

    def format_display(self) -> str:
        return (
            f"Page {self.page_number}: {self.date.format_display()} "
            f"(before page {self.previous_page_number}: "
            f"{self.previous_date.format_display()})"
        )


def find_date_regressions(
    pages: Sequence[tuple[str, ApproximateDate | None]],
) -> list[DateRegression]:
    """Flag dates that step backwards in notebook order.

    Notebooks usually advance chronologically. A hit means the page's date range
    is entirely before the previous dated page's range (overlapping partial dates
    are not flagged). Undated pages are skipped.
    """
    out: list[DateRegression] = []
    prev_number: int | None = None
    prev_id: str | None = None
    prev_date: ApproximateDate | None = None
    for i, (page_id, page_date) in enumerate(pages, start=1):
        if page_date is None:
            continue
        if (
            prev_date is not None
            and prev_number is not None
            and prev_id is not None
            and page_date.clearly_before(prev_date)
        ):
            out.append(
                DateRegression(
                    page_number=i,
                    page_id=page_id,
                    date=page_date,
                    previous_page_number=prev_number,
                    previous_page_id=prev_id,
                    previous_date=prev_date,
                )
            )
        prev_number = i
        prev_id = page_id
        prev_date = page_date
    return out


def format_approve_all_dates_help(
    regressions: Sequence[DateRegression],
    *,
    max_listed: int = 8,
) -> str:
    """Tooltip for bulk date approval, including any suspicious regressions."""
    base = "Approve all dates in this notebook"
    if not regressions:
        return (
            f"{base}. Notebook dates normally increase with page order; "
            "none look suspicious right now."
        )
    lines = [
        f"{base}. Warning: {len(regressions)} date"
        f"{'s' if len(regressions) != 1 else ''} look suspicious "
        "(later page, earlier date):"
    ]
    for hit in regressions[:max_listed]:
        lines.append(f"• {hit.format_display()}")
    extra = len(regressions) - max_listed
    if extra > 0:
        lines.append(f"• …and {extra} more")
    return "\n".join(lines)


def canonicalize_page_date_state(
    date: ApproximateDate | None,
    date_approved: bool,
    date_source: str | None,
) -> tuple[ApproximateDate | None, bool, str | None]:
    """Enforce date / approved / source invariants; raise on illegal combinations."""
    if date is None:
        if date_source is not None:
            raise ValueError("date_source must be null when date is null")
        return None, True, None
    if date_approved:
        if date_source is not None:
            raise ValueError("approved date must have date_source null")
        return date, True, None
    if date_source not in DATE_SOURCES:
        raise ValueError("unapproved date requires date_source 'extracted' or 'inherited'")
    return date, False, date_source


def page_date_fields_from_dict(
    data: dict[str, Any],
) -> tuple[ApproximateDate | None, bool, str | None]:
    """Load page date triple from persisted JSON; reject malformed values."""
    date = ApproximateDate.from_dict(data.get("date"))
    has_approved = "date_approved" in data
    has_source = "date_source" in data

    if not has_approved and not has_source:
        # Legacy manifests: dated or undated → human-approved, no source.
        return canonicalize_page_date_state(date, True, None)

    if has_approved:
        raw_approved = data["date_approved"]
        if type(raw_approved) is not bool:
            raise ValueError("date_approved must be a boolean")
        approved = raw_approved
    else:
        raise ValueError("date_source requires date_approved")

    if has_source:
        raw_source = data["date_source"]
        if raw_source is not None and raw_source not in DATE_SOURCES:
            raise ValueError(f"invalid date_source: {raw_source!r}")
        source = raw_source
    else:
        if date is None or approved:
            source = None
        else:
            raise ValueError("unapproved date requires date_source")

    return canonicalize_page_date_state(date, approved, source)


def parse_date_input(raw: str) -> ApproximateDate | None:
    """Parse UI / filter date strings. Empty → None. Raises ValueError if unrecognized."""
    text = raw.strip()
    if not text:
        return None

    named = _parse_month_name_input(text)
    if named is not None:
        return named

    compact = re.fullmatch(
        r"(\d{6})(?:[ \t]+(\d{4}|\d{1,2}:\d{2}))?",
        text,
    )
    if compact:
        try:
            return _parse_yymmdd(compact.group(1))
        except ValueError as exc:
            raise ValueError(f"Unrecognized date: {raw!r}") from exc

    parts = text.replace("/", "-").split("-")
    try:
        if len(parts) == 1:
            year = int(parts[0])
            if len(parts[0]) == 6:
                return _parse_yymmdd(parts[0])
            return ApproximateDate(year=year)
        if len(parts) == 2:
            a, b = int(parts[0]), int(parts[1])
            if a > 31:
                return ApproximateDate(year=a, month=b)
            return ApproximateDate(year=b, month=a)
        if len(parts) == 3:
            a, b, c = int(parts[0]), int(parts[1]), int(parts[2])
            if len(parts[0]) == 4 or a > 31:
                return ApproximateDate(year=a, month=b, day=c)
            if len(parts[2]) == 2:
                return ApproximateDate(year=expand_yy(c), month=b, day=a)
            return ApproximateDate(year=c, month=b, day=a)
    except ValueError as exc:
        raise ValueError(f"Unrecognized date: {raw!r}") from exc
    raise ValueError(f"Unrecognized date: {raw!r}")


def extract_page_date(
    text: str | None,
    *,
    today: date | None = None,
) -> ApproximateDate | None:
    """Best diary date from transcription text, or None."""
    if not text or not text.strip():
        return None
    ref = today or date.today()
    early_end = _early_text_end(text)
    candidates: list[tuple[ApproximateDate, int, int, int, int]] = []
    # (date, start, precision_rank, span_len, pattern_id)

    def _accept(d: ApproximateDate, start: int, span: int, pat: int) -> None:
        if not _plausible_extracted_year(d.year, today=ref):
            return
        candidates.append((d, start, _PRECISION_RANK[d.precision], span, pat))

    for m in re.finditer(
        r"(?<![A-Za-z0-9])(\d{6})(?:[ \t]+(\d{4}|\d{1,2}:\d{2}))?(?![A-Za-z0-9])",
        text,
    ):
        if m.start() >= early_end:
            continue
        try:
            d = _parse_yymmdd(m.group(1))
        except ValueError:
            continue
        _accept(d, m.start(), m.end() - m.start(), _PAT_YYMMDD)

    for m in re.finditer(
        r"(?<!\d)(\d{4})([-./])(\d{1,2})\2(\d{1,2})(?!\d)",
        text,
    ):
        try:
            d = ApproximateDate(year=int(m.group(1)), month=int(m.group(3)), day=int(m.group(4)))
        except ValueError:
            continue
        _accept(d, m.start(), m.end() - m.start(), _PAT_YMD)

    for m in re.finditer(
        r"(?<!\d)(\d{1,2})([-./])(\d{1,2})\2(\d{4})(?!\d)",
        text,
    ):
        try:
            d = ApproximateDate(year=int(m.group(4)), month=int(m.group(3)), day=int(m.group(1)))
        except ValueError:
            continue
        _accept(d, m.start(), m.end() - m.start(), _PAT_DMY)

    # Short-year DMY (e.g. 9/1/18). Early window only — diary stamps.
    for m in re.finditer(
        r"(?<!\d)(\d{1,2})([-./])(\d{1,2})\2(\d{2})(?!\d)",
        text,
    ):
        if m.start() >= early_end:
            continue
        try:
            d = ApproximateDate(
                year=expand_yy(int(m.group(4))),
                month=int(m.group(3)),
                day=int(m.group(1)),
            )
        except ValueError:
            continue
        _accept(d, m.start(), m.end() - m.start(), _PAT_DMY_YY)

    # Short-year YMD with - or . only (e.g. 18-01-09). Slash stays DMY.
    for m in re.finditer(
        r"(?<!\d)(\d{2})([-./])(\d{1,2})\2(\d{1,2})(?!\d)",
        text,
    ):
        if m.start() >= early_end:
            continue
        if m.group(2) == "/":
            continue
        try:
            d = ApproximateDate(
                year=expand_yy(int(m.group(1))),
                month=int(m.group(3)),
                day=int(m.group(4)),
            )
        except ValueError:
            continue
        _accept(d, m.start(), m.end() - m.start(), _PAT_YMD_YY)

    for m in re.finditer(
        rf"(?i)\b({_MONTH_NAME_RE})\s+(\d{{1,2}}){_ORDINAL_SUFFIX_RE},?\s+(\d{{4}})\b",
        text,
    ):
        if m.start() >= early_end:
            continue
        try:
            d = ApproximateDate(
                year=int(m.group(3)),
                month=_MONTH_NAME_TO_NUM[m.group(1).lower()],
                day=int(m.group(2)),
            )
        except ValueError:
            continue
        _accept(d, m.start(), m.end() - m.start(), _PAT_MONTH_NAME_DAY)

    for m in re.finditer(
        rf"(?i)\b(\d{{1,2}}){_ORDINAL_SUFFIX_RE}\s+({_MONTH_NAME_RE}),?\s+(\d{{4}})\b",
        text,
    ):
        if m.start() >= early_end:
            continue
        try:
            d = ApproximateDate(
                year=int(m.group(3)),
                month=_MONTH_NAME_TO_NUM[m.group(2).lower()],
                day=int(m.group(1)),
            )
        except ValueError:
            continue
        _accept(d, m.start(), m.end() - m.start(), _PAT_MONTH_NAME_DAY)

    for m in re.finditer(
        rf"(?i)\b({_MONTH_NAME_RE})\s+(\d{{4}})\b",
        text,
    ):
        if m.start() >= early_end:
            continue
        # Skip "Jan 2, 2018" / "January 2018" prefix of a day-precision form.
        after = text[m.end() : m.end() + 1]
        if after and after[0].isdigit():
            continue
        # If a day digit sits between month and year, the day patterns above win.
        try:
            d = ApproximateDate(
                year=int(m.group(2)),
                month=_MONTH_NAME_TO_NUM[m.group(1).lower()],
            )
        except ValueError:
            continue
        _accept(d, m.start(), m.end() - m.start(), _PAT_MONTH_NAME_MONTH)

    for m in re.finditer(r"(?<!\d)(\d{4})([-./])(\d{1,2})(?!\d)", text):
        # Avoid matching the YYYY-MM prefix of an already-matched YYYY-MM-DD.
        after = m.end()
        if (
            after < len(text)
            and text[after] in "-./"
            and after + 1 < len(text)
            and text[after + 1].isdigit()
        ):
            continue
        try:
            d = ApproximateDate(year=int(m.group(1)), month=int(m.group(3)))
        except ValueError:
            continue
        _accept(d, m.start(), m.end() - m.start(), _PAT_YM)

    for m in re.finditer(r"(?<!\d)(\d{1,2})/(\d{4})(?!\d)", text):
        try:
            d = ApproximateDate(year=int(m.group(2)), month=int(m.group(1)))
        except ValueError:
            continue
        _accept(d, m.start(), m.end() - m.start(), _PAT_MY)

    for m in re.finditer(r"(?<!\d)(\d{4})(?!\d)", text):
        if m.start() >= early_end:
            continue
        # Skip years that are the leading part of a longer structured date.
        rest = text[m.end() : m.end() + 1]
        if rest in "-./":
            continue
        token = m.group(1)
        # Diary stamps are YYMMDD HHMM; a lone HHMM (e.g. 1902, 1947) must not
        # become a calendar year — leave undated so inheritance can apply.
        if looks_like_hhmm(token):
            continue
        try:
            d = ApproximateDate(year=int(token))
        except ValueError:
            continue
        _accept(d, m.start(), m.end() - m.start(), _PAT_YEAR)

    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[1], -c[2], -c[3], c[4]))
    return candidates[0][0]


def looks_like_unparsed_date_stamp(
    text: str | None,
    *,
    today: date | None = None,
) -> bool:
    """True when early text looks date-stamped but ``extract_page_date`` found nothing.

    Used to refuse inheritance: a failed-looking stamp should stay undated for
    Review rather than silently carrying a neighbor's day.
    """
    if not text or not text.strip():
        return False
    if extract_page_date(text, today=today) is not None:
        return False
    early = text[: _early_text_end(text)]
    if re.search(
        rf"(?i)\b{_MONTH_NAME_RE}\s+\d{{1,2}}{_ORDINAL_SUFFIX_RE},?\s+\d{{2,4}}\b",
        early,
    ):
        return True
    if re.search(
        rf"(?i)\b\d{{1,2}}{_ORDINAL_SUFFIX_RE}\s+{_MONTH_NAME_RE},?\s+\d{{2,4}}\b",
        early,
    ):
        return True
    if re.search(rf"(?i)\b{_MONTH_NAME_RE}\s+\d{{4}}\b", early):
        return True
    if re.search(r"(?<!\d)\d{1,2}[-./]\d{1,2}[-./]\d{2,4}(?!\d)", early):
        return True
    if re.search(r"(?<![A-Za-z0-9])\d{6}(?![A-Za-z0-9])", early):
        return True
    return False


def is_plausible_diary_year(year: int, *, today: date | None = None) -> bool:
    """True when ``year`` is in the diary-plausible window (1900 .. today+slack).

    Used by OCR extract and archive timeline spikes so page numbers / codes
    (e.g. 507, 2405) do not stretch charts across impossible centuries.
    """
    ref = today or date.today()
    return _EXTRACT_YEAR_MIN <= year <= ref.year + _EXTRACT_YEAR_FUTURE_SLACK


def looks_like_hhmm(token: str) -> bool:
    """True when ``token`` is a plausible 24h HHMM diary time (00:00–23:59)."""
    if len(token) != 4 or not token.isdigit():
        return False
    hour = int(token[0:2])
    minute = int(token[2:4])
    return 0 <= hour <= 23 and 0 <= minute <= 59


def is_hhmm_shaped_year(date: ApproximateDate) -> bool:
    """True for year-only values that are more likely diary times than years."""
    return date.precision == "year" and looks_like_hhmm(f"{date.year:04d}")


def _plausible_extracted_year(year: int, *, today: date) -> bool:
    """Reject far-future / pre-1900 years that are usually page numbers or codes."""
    return is_plausible_diary_year(year, today=today)


def _early_text_end(text: str) -> int:
    lines = text.splitlines()
    chunk = "\n".join(lines[:_EARLY_TEXT_MAX_LINES])
    return min(len(chunk), _EARLY_TEXT_MAX_CHARS, len(text))


def _parse_yymmdd(token: str) -> ApproximateDate:
    if len(token) != 6 or not token.isdigit():
        raise ValueError(f"invalid YYMMDD: {token!r}")
    yy = int(token[0:2])
    month = int(token[2:4])
    day = int(token[4:6])
    return ApproximateDate(year=expand_yy(yy), month=month, day=day)


def _parse_month_name_input(text: str) -> ApproximateDate | None:
    """Parse a whole UI date string that uses English month names."""
    m = re.fullmatch(
        rf"(?i)({_MONTH_NAME_RE})\s+(\d{{1,2}}){_ORDINAL_SUFFIX_RE},?\s+(\d{{4}})",
        text,
    )
    if m:
        return ApproximateDate(
            year=int(m.group(3)),
            month=_MONTH_NAME_TO_NUM[m.group(1).lower()],
            day=int(m.group(2)),
        )
    m = re.fullmatch(
        rf"(?i)(\d{{1,2}}){_ORDINAL_SUFFIX_RE}\s+({_MONTH_NAME_RE}),?\s+(\d{{4}})",
        text,
    )
    if m:
        return ApproximateDate(
            year=int(m.group(3)),
            month=_MONTH_NAME_TO_NUM[m.group(2).lower()],
            day=int(m.group(1)),
        )
    m = re.fullmatch(rf"(?i)({_MONTH_NAME_RE})\s+(\d{{4}})", text)
    if m:
        return ApproximateDate(
            year=int(m.group(2)),
            month=_MONTH_NAME_TO_NUM[m.group(1).lower()],
        )
    return None


def normalize_tags(tags: list[str] | None) -> list[str]:
    """Ordered unique slugs. Implementation lives in the tagging kernel."""
    from transcribe.tagging.kernel import normalize_slugs

    return normalize_slugs(tags)


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


def bin_key_to_range(key: str, grain: str) -> tuple[ApproximateDate, ApproximateDate]:
    """Inclusive approximate-date bounds covering a timeline bin.

    Day-precision ends are used for month/week/day grains so archive range
    filters (sort-key compare) include every page dated inside the bin.
    """
    start = bin_key_to_date(key, grain)
    if grain == "year":
        return ApproximateDate(start.year), ApproximateDate(start.year)
    if grain == "month":
        end = _advance_bin_start(start, "month") - timedelta(days=1)
        return (
            ApproximateDate(start.year, start.month, start.day),
            ApproximateDate(end.year, end.month, end.day),
        )
    if grain == "week":
        end = start + timedelta(days=6)
        return (
            ApproximateDate(start.year, start.month, start.day),
            ApproximateDate(end.year, end.month, end.day),
        )
    return (
        ApproximateDate(start.year, start.month, start.day),
        ApproximateDate(start.year, start.month, start.day),
    )


def format_date_filter_input(value: ApproximateDate) -> str:
    """Format an ApproximateDate for archive From/To text inputs."""
    if value.day is not None and value.month is not None:
        return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
    if value.month is not None:
        return f"{value.year:04d}-{value.month:02d}"
    return f"{value.year:04d}"


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
