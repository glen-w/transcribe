"""Unit tests for ApproximateDate parsing and extraction."""

from __future__ import annotations

import pytest

from transcribe.domain.dates import (
    ApproximateDate,
    canonicalize_page_date_state,
    expand_yy,
    extract_page_date,
    fill_bin_series,
    find_date_regressions,
    format_approve_all_dates_help,
    format_date_filter_input,
    bin_key_to_range,
    inclusive_day_span,
    looks_like_unparsed_date_stamp,
    normalize_tags,
    parse_date_input,
)


def test_partial_dates_and_validation():
    assert ApproximateDate(2020).as_dict() == {"y": 2020}
    assert ApproximateDate(2020, 5).as_dict() == {"y": 2020, "m": 5}
    with pytest.raises(ValueError):
        ApproximateDate(2020, day=1)
    with pytest.raises(ValueError):
        ApproximateDate(2020, 2, 30)


def test_normalize_tags():
    assert normalize_tags([" Dream ", "DREAM", "note", ""]) == ["dream", "note"]


def test_inclusive_span():
    assert inclusive_day_span(ApproximateDate(2015, 12, 30), ApproximateDate(2016, 1, 6)) == 8


def test_fill_bin_series_includes_zeros():
    filled = fill_bin_series(
        "month",
        ApproximateDate(2017, 1, 1),
        ApproximateDate(2017, 4, 1),
        {"2017-01": 3, "2017-04": 1},
    )
    assert [k for k, _ in filled] == ["2017-01", "2017-02", "2017-03", "2017-04"]
    assert dict(filled)["2017-02"] == 0
    assert dict(filled)["2017-01"] == 3


def test_bin_key_to_range_covers_full_bin():
    y0, y1 = bin_key_to_range("2024", "year")
    assert y0 == ApproximateDate(2024)
    assert y1 == ApproximateDate(2024)

    m0, m1 = bin_key_to_range("2024-03", "month")
    assert m0 == ApproximateDate(2024, 3, 1)
    assert m1 == ApproximateDate(2024, 3, 31)

    w0, w1 = bin_key_to_range("2024-W10", "week")
    assert w0 == ApproximateDate(2024, 3, 4)  # ISO week 10 Monday
    assert w1 == ApproximateDate(2024, 3, 10)

    d0, d1 = bin_key_to_range("2024-03-15", "day")
    assert d0 == d1 == ApproximateDate(2024, 3, 15)

    assert format_date_filter_input(m0) == "2024-03-01"
    assert format_date_filter_input(y0) == "2024"


def test_expand_yy_century_pivot():
    assert expand_yy(69) == 2069
    assert expand_yy(70) == 1970
    assert expand_yy(23) == 2023


def test_parse_date_input_formats():
    assert parse_date_input("") is None
    assert parse_date_input("2020") == ApproximateDate(2020)
    assert parse_date_input("2020-05") == ApproximateDate(2020, 5)
    assert parse_date_input("05/2020") == ApproximateDate(2020, 5)
    assert parse_date_input("2020-05-23") == ApproximateDate(2020, 5, 23)
    assert parse_date_input("23/05/2020") == ApproximateDate(2020, 5, 23)
    assert parse_date_input("9/1/18") == ApproximateDate(2018, 1, 9)
    assert parse_date_input("Jan 2, 2018") == ApproximateDate(2018, 1, 2)
    assert parse_date_input("2 January 2018") == ApproximateDate(2018, 1, 2)
    assert parse_date_input("January 2018") == ApproximateDate(2018, 1)
    assert parse_date_input("260523") == ApproximateDate(2026, 5, 23)
    assert parse_date_input("260523 1504") == ApproximateDate(2026, 5, 23)
    assert parse_date_input("260523 15:04") == ApproximateDate(2026, 5, 23)
    with pytest.raises(ValueError):
        parse_date_input("not-a-date")
    with pytest.raises(ValueError):
        parse_date_input("260230")  # impossible day


def test_extract_month_names_and_short_year_dmy():
    """Adventure Time regressions: month names + short-year slash stamps."""
    at3 = (
        "I loves you, smuggle puffin!\n\nHello Glen!\nJan 2, 2018.\n\n"
        "It is the very beginning of 2018 and I love you very much."
    )
    assert extract_page_date(at3) == ApproximateDate(2018, 1, 2)
    assert extract_page_date("2 January 2018\nnotes") == ApproximateDate(2018, 1, 2)
    assert extract_page_date("2nd Jan 2018 entry") == ApproximateDate(2018, 1, 2)
    assert extract_page_date("January 2018\nresolutions") == ApproximateDate(2018, 1)
    assert extract_page_date("9/1/18\n15h37") == ApproximateDate(2018, 1, 9)
    assert extract_page_date("03/01/2018\nAm") == ApproximateDate(2018, 1, 3)
    # OCR garble of 9/1/18 → 9/11/18 still extracts (DMY), not inherit.
    assert extract_page_date("9/11/18\n15h37") == ApproximateDate(2018, 11, 9)


def test_looks_like_unparsed_date_stamp():
    assert not looks_like_unparsed_date_stamp("plain prose only")
    assert not looks_like_unparsed_date_stamp("9/1/18\nnotes")  # parses
    assert not looks_like_unparsed_date_stamp("Jan 2, 2018.")  # parses
    assert not looks_like_unparsed_date_stamp("1902\nnotes")  # HHMM, not a stamp
    # Impossible calendar forms look stamped but fail extract.
    assert looks_like_unparsed_date_stamp("32/01/18\nnotes")
    assert looks_like_unparsed_date_stamp("260230 at the top")
    assert looks_like_unparsed_date_stamp("Jan 99, 2018\nnotes")
    # Mid-page noise must not trip the early-window heuristic.
    filler = "word " * 80
    assert not looks_like_unparsed_date_stamp(filler + "32/01/18 buried")


def test_extract_month_name_beats_hhmm_shaped_year():
    """Bare 2018 is HHMM-shaped; month-name form still supplies the date."""
    assert extract_page_date("2018\nnotes") is None
    assert extract_page_date("Jan 2, 2018.\nnotes") == ApproximateDate(2018, 1, 2)


def test_extract_short_year_ymd_when_dmy_invalid():
    """Dash/dot YY-MM-DD wins when DMY day would be impossible (e.g. 99)."""
    assert extract_page_date("99-01-15\nnotes") == ApproximateDate(1999, 1, 15)
    assert extract_page_date("99.01.15\nnotes") == ApproximateDate(1999, 1, 15)
    # Slash stays DMY even when first token looks year-like.
    assert extract_page_date("18/01/09\nnotes") == ApproximateDate(2009, 1, 18)


def test_find_date_regressions_flags_clear_backsteps():
    pages = [
        ("a", ApproximateDate(2026, 5, 23)),
        ("b", ApproximateDate(2026, 5, 20)),  # regresses
        ("c", None),
        ("d", ApproximateDate(2026, 5, 20)),  # same as prev dated — ok
        ("e", ApproximateDate(2026, 4)),  # clearly before May 20
    ]
    hits = find_date_regressions(pages)
    assert [(h.page_number, h.previous_page_number) for h in hits] == [(2, 1), (5, 4)]
    assert "Page 2: 20/05/2026" in hits[0].format_display()
    help_text = format_approve_all_dates_help(hits)
    assert "2 dates look suspicious" in help_text
    assert "Page 2:" in help_text
    assert "Page 5:" in help_text


def test_find_date_regressions_allows_overlapping_partials():
    pages = [
        ("a", ApproximateDate(2026, 5)),
        ("b", ApproximateDate(2026, 5, 1)),  # within May
        ("c", ApproximateDate(2026, 5, 31)),
        ("d", ApproximateDate(2026)),  # year overlaps
    ]
    assert find_date_regressions(pages) == []
    assert "none look suspicious" in format_approve_all_dates_help([])


def test_extract_yymmdd_with_time():
    text = "260523 1504\nUne beauté pénétrante"
    assert extract_page_date(text) == ApproximateDate(2026, 5, 23)


def test_extract_rejects_impossible_and_malformed():
    assert extract_page_date("260230 at the top") is None
    assert extract_page_date("260523xyz") is None  # no token boundary after


def test_extract_leap_year():
    assert extract_page_date("240229 notes") == ApproximateDate(2024, 2, 29)
    assert extract_page_date("230229 notes") is None


def test_extract_structured_and_ambiguous_dmy():
    assert extract_page_date("Meeting on 23/05/2020 about x") == ApproximateDate(2020, 5, 23)
    assert extract_page_date("2020-05-23 later") == ApproximateDate(2020, 5, 23)


def test_extract_prefers_earliest_then_precision():
    text = "1999\nthen later 23/05/2020 detail"
    # Bare year at start (1999 is not a valid HHMM) vs day later — earliest wins.
    assert extract_page_date(text) == ApproximateDate(1999)
    # Same start: day precision wins over year if both at same offset — use compact.
    assert extract_page_date("260523 and also 2026") == ApproximateDate(2026, 5, 23)


def test_extract_ignores_mid_prose_yymmdd_and_years():
    filler = "word " * 80
    text = filler + "260523 mid page and year 1999 buried"
    assert extract_page_date(text) is None


def test_extract_rejects_implausible_bare_years():
    from datetime import date

    today = date(2026, 8, 10)
    assert extract_page_date("2044\nnotes", today=today) is None
    assert extract_page_date("1899\nnotes", today=today) is None
    # Bare years that are also valid HHMM times are rejected (see timestamps test).
    # 1999 has minute 99 → not a clock time, still accepted as a year.
    assert extract_page_date("1999\nnotes", today=today) == ApproximateDate(1999)
    assert extract_page_date("1960\nnotes", today=today) == ApproximateDate(1960)
    # YYMMDD that expands past the plausible window (44 → 2044).
    assert extract_page_date("440523 notes", today=today) is None


def test_extract_rejects_hhmm_timestamps_as_years():
    """Lone diary times must not become calendar years (inherit instead)."""
    assert extract_page_date("1902\nnotes") is None
    assert extract_page_date("1947\nentry") is None
    assert extract_page_date("2015\nlater") is None  # 20:15
    assert extract_page_date("2024\nnotes") is None  # 20:24
    # Full stamp still wins; optional HHMM is ignored for the date value.
    assert extract_page_date("240506 1902\nnotes") == ApproximateDate(2024, 5, 6)
    assert extract_page_date("260523 15:04\nnotes") == ApproximateDate(2026, 5, 23)
    # Structured calendar forms are not times.
    assert extract_page_date("2024-05-06\nnotes") == ApproximateDate(2024, 5, 6)
    assert extract_page_date("06/05/2024\nnotes") == ApproximateDate(2024, 5, 6)


def test_is_plausible_diary_year():
    from datetime import date

    from transcribe.domain.dates import (
        is_hhmm_shaped_year,
        is_plausible_diary_year,
        looks_like_hhmm,
    )

    today = date(2026, 8, 10)
    assert is_plausible_diary_year(1900, today=today)
    assert is_plausible_diary_year(2026, today=today)
    assert is_plausible_diary_year(2027, today=today)
    assert not is_plausible_diary_year(1899, today=today)
    assert not is_plausible_diary_year(507, today=today)
    assert not is_plausible_diary_year(2405, today=today)
    assert not is_plausible_diary_year(2028, today=today)
    assert looks_like_hhmm("1902")
    assert looks_like_hhmm("1947")
    assert not looks_like_hhmm("1960")
    assert is_hhmm_shaped_year(ApproximateDate(1902))
    assert not is_hhmm_shaped_year(ApproximateDate(2024, 5, 6))
    assert not is_hhmm_shaped_year(ApproximateDate(1960))


def test_canonicalize_invariants():
    assert canonicalize_page_date_state(None, False, None) == (None, True, None)
    d = ApproximateDate(2020, 1, 2)
    assert canonicalize_page_date_state(d, True, None) == (d, True, None)
    assert canonicalize_page_date_state(d, False, "extracted")[2] == "extracted"
    with pytest.raises(ValueError):
        canonicalize_page_date_state(d, True, "extracted")
    with pytest.raises(ValueError):
        canonicalize_page_date_state(d, False, None)
    with pytest.raises(ValueError):
        canonicalize_page_date_state(None, True, "inherited")
