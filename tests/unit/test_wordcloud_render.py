"""Tests for UI wordcloud rendering (TX-aligned generate_from_frequencies)."""

from __future__ import annotations

import pytest

from transcribe.ui.wordcloud_render import (
    frequencies_from_tokens,
    render_wordcloud_from_payload,
    render_wordcloud_image,
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
