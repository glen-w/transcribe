"""Beer labels response validation tests."""

from __future__ import annotations

from transcribe.prompt_engine.validate import validate_beer_labels_window_response_v1


def test_beer_labels_valid():
    out = validate_beer_labels_window_response_v1(
        {
            "detected": True,
            "confidence": 0.92,
            "starts_on_this_window": True,
            "continues_before": False,
            "continues_after": False,
            "label_kind": "bottle_label",
            "beer_name": "Northern Lights",
            "brewery_or_brand": "Whiplash",
            "style_hint": "Micro IPA",
            "sample_text": "WHIPLASH NORTHERN LIGHTS MICRO IPA",
            "reason": "brand block with style line",
        }
    )
    assert out is not None
    assert out["label_kind"] == "bottle_label"
    assert out["beer_name"] == "Northern Lights"
    assert out["brewery_or_brand"] == "Whiplash"
    assert out["style_hint"] == "Micro IPA"


def test_beer_labels_unknown_kind_falls_back():
    out = validate_beer_labels_window_response_v1(
        {
            "detected": True,
            "confidence": 0.8,
            "starts_on_this_window": True,
            "continues_before": False,
            "continues_after": False,
            "label_kind": "poster",
            "sample_text": "stout 6.5%",
            "reason": "abv line",
        }
    )
    assert out is not None
    assert out["label_kind"] == "other"


def test_beer_labels_malformed_returns_none():
    assert validate_beer_labels_window_response_v1({"detected": "maybe"}) is None
    assert validate_beer_labels_window_response_v1({}) is None
