"""Tests for UI wordcloud rendering (TX-aligned basic + advanced explorer)."""

from __future__ import annotations

import pytest

from transcribe.ui.wordcloud_render import (
    build_wordcloud_explorer_html,
    filter_terms,
    frequencies_from_tokens,
    render_wordcloud_from_payload,
    render_wordcloud_image,
    terms_from_tokens,
    terms_payload_from_analysis,
    wordcloud2_js_available,
    wordcloud_available,
)


def test_frequencies_from_tokens_prefer_count():
    freq = frequencies_from_tokens(
        [
            {"token": "rain", "count": 5, "weight": 1.0},
            {"token": "travel", "count": 2, "weight": 0.4},
            {"token": "", "count": 9},
            {"token": "skip", "count": 0},
        ]
    )
    assert freq == {"rain": 5.0, "travel": 2.0}


def test_frequencies_fall_back_to_weight():
    freq = frequencies_from_tokens([{"token": "alone", "weight": 0.7}])
    assert freq == {"alone": 0.7}


def test_terms_and_filter_mirror_tx_explorer():
    terms = terms_from_tokens(
        [
            {"token": "zebra", "count": 1},
            {"token": "rain", "count": 5},
            {"token": "railway", "count": 3},
        ]
    )
    assert terms[0]["term"] == "rain" and terms[0]["rank"] == 1
    filtered = filter_terms(
        terms, search="rai", top_n=10, min_value=2, sort_mode="value"
    )
    assert [t["term"] for t in filtered] == ["rain", "railway"]
    by_term = filter_terms(terms, sort_mode="term")
    assert [t["term"] for t in by_term] == ["railway", "rain", "zebra"]


@pytest.mark.skipif(not wordcloud_available(), reason="wordcloud optional extra missing")
def test_render_wordcloud_image_returns_pil():
    from PIL import Image

    img = render_wordcloud_image({"notebook": 5.0, "rain": 3.0, "travel": 2.0})
    assert isinstance(img, Image.Image)
    assert img.size[0] >= 200
    assert img.size[1] >= 120


@pytest.mark.skipif(not wordcloud_available(), reason="wordcloud optional extra missing")
def test_render_from_payload_and_determinism():
    payload = {
        "tokens": [
            {"token": "notebook", "count": 8, "weight": 1.0},
            {"token": "diary", "count": 4, "weight": 0.5},
            {"token": "rain", "count": 3, "weight": 0.375},
        ]
    }
    a = render_wordcloud_from_payload(payload, width=400, height=200)
    b = render_wordcloud_from_payload(payload, width=400, height=200)
    assert a is not None and b is not None
    assert list(a.getdata()) == list(b.getdata())


def test_empty_frequencies_return_none():
    assert render_wordcloud_image({}) is None


def test_advanced_explorer_html_contract():
    assert wordcloud2_js_available()
    payload = terms_payload_from_analysis(
        {
            "tokens": [
                {"token": "rain", "count": 5},
                {"token": "travel", "count": 2},
            ]
        }
    )
    html_doc = build_wordcloud_explorer_html("Word themes", payload)
    assert "WordCloud(" in html_doc
    assert 'id="search"' in html_doc
    assert 'id="topN"' in html_doc
    assert 'id="minValue"' in html_doc
    assert 'id="sortMode"' in html_doc
    assert "downloadCsv" in html_doc
    assert "copyTerms" in html_doc
    assert "cdn.jsdelivr.net" not in html_doc  # vendored / offline
    assert "rain" in html_doc
    tiny = build_wordcloud_explorer_html(
        "T",
        payload,
        wordcloud2_js="window.WordCloud=function(){};",
    )
    assert "window.WordCloud=function(){};" in tiny
