"""Poetry and custom response validation tests."""

from __future__ import annotations

from transcribe.prompt_engine.validate import (
    validate_custom_finding_v1,
    validate_poetry_window_response_v1,
)


def test_poetry_valid():
    obj = {
        "detected": True,
        "confidence": 0.9,
        "starts_on_this_window": True,
        "continues_before": False,
        "continues_after": True,
        "boundaries": {"start_page_hint": "mid", "end_page_hint": None},
        "title": "Spring",
        "reason": "ragged lines",
    }
    out = validate_poetry_window_response_v1(obj)
    assert out is not None
    assert out["detected"] is True
    assert out["title"] == "Spring"


def test_poetry_malformed_returns_none():
    assert validate_poetry_window_response_v1({"detected": "maybe"}) is None
    assert validate_poetry_window_response_v1({}) is None


def test_custom_valid():
    obj = {
        "detected": False,
        "confidence": 0.1,
        "starts_on_this_window": False,
        "continues_before": False,
        "continues_after": False,
        "reason": "none",
    }
    out = validate_custom_finding_v1(obj)
    assert out is not None
    assert out["detected"] is False
