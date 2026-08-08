"""Unit tests for ApproximateDate."""

from __future__ import annotations

import pytest

from transcribe.domain.dates import (
    ApproximateDate,
    fill_bin_series,
    inclusive_day_span,
    normalize_tags,
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
