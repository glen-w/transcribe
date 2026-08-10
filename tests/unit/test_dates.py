"""Unit tests for ApproximateDate parsing and extraction."""

from __future__ import annotations

import pytest

from transcribe.domain.dates import (
    ApproximateDate,
    canonicalize_page_date_state,
    expand_yy,
    extract_page_date,
    fill_bin_series,
    inclusive_day_span,
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
    assert parse_date_input("260523") == ApproximateDate(2026, 5, 23)
    assert parse_date_input("260523 1504") == ApproximateDate(2026, 5, 23)
    assert parse_date_input("260523 15:04") == ApproximateDate(2026, 5, 23)
    with pytest.raises(ValueError):
        parse_date_input("not-a-date")
    with pytest.raises(ValueError):
        parse_date_input("260230")  # impossible day


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
    text = "2020\nthen later 23/05/2020 detail"
    # Year at start vs day later — earliest wins (year at offset 0).
    assert extract_page_date(text) == ApproximateDate(2020)
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
    assert extract_page_date("2026\nnotes", today=today) == ApproximateDate(2026)
    assert extract_page_date("2027\nnotes", today=today) == ApproximateDate(2027)
    assert extract_page_date("2028\nnotes", today=today) is None
    # YYMMDD that expands past the plausible window (44 → 2044).
    assert extract_page_date("440523 notes", today=today) is None


def test_is_plausible_diary_year():
    from datetime import date

    from transcribe.domain.dates import is_plausible_diary_year

    today = date(2026, 8, 10)
    assert is_plausible_diary_year(1900, today=today)
    assert is_plausible_diary_year(2026, today=today)
    assert is_plausible_diary_year(2027, today=today)
    assert not is_plausible_diary_year(1899, today=today)
    assert not is_plausible_diary_year(507, today=today)
    assert not is_plausible_diary_year(2405, today=today)
    assert not is_plausible_diary_year(2028, today=today)

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
