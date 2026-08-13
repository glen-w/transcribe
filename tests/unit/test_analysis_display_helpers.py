"""Unit tests for Analyse product display helpers (no Streamlit)."""

from __future__ import annotations

from transcribe.ui.analysis_display_helpers import (
    aggregate_entity_sentiment,
    contextual_label_counts,
    emotion_label_totals,
    group_action_items,
    motif_rows,
    topic_weight_rows,
    unit_series,
    wordcloud_rows,
)


def test_unit_series_skips_missing():
    orders, vals = unit_series(
        [{"order": 1, "ttr": 0.4}, {"order": 2}, {"order": 3, "ttr": 0.5}],
        "ttr",
    )
    assert orders == [1, 3]
    assert vals == [0.4, 0.5]


def test_wordcloud_and_topic_rows():
    wc = wordcloud_rows(
        {"tokens": [{"token": "rain", "weight": 2.0, "count": 5}]},
        limit=10,
    )
    assert wc[0]["token"] == "rain"
    topics = topic_weight_rows(
        {
            "topics": [
                {"label": "weather", "terms": ["rain", "cloud"], "weight": 3, "unit_ids": [1, 2, 3]},
                {"label": "travel", "terms": ["train"], "unit_ids": [4]},
            ]
        }
    )
    assert topics[0]["label"] == "weather"
    assert topics[0]["weight"] == 3.0


def test_aggregate_entity_sentiment():
    rows = aggregate_entity_sentiment(
        {
            "entities": [
                {
                    "text": "Paris",
                    "label": "GPE",
                    "sentiment": {"compound": 0.4, "label": "positive"},
                },
                {
                    "text": "paris",
                    "label": "GPE",
                    "sentiment": {"compound": 0.2, "label": "positive"},
                },
                {
                    "text": "Berlin",
                    "label": "GPE",
                    "sentiment": {"compound": -0.3, "label": "negative"},
                },
            ]
        }
    )
    paris = next(r for r in rows if r["entity"].casefold() == "paris")
    assert paris["mentions"] == 2
    assert abs(paris["mean_sentiment"] - 0.3) < 1e-6
    assert paris["polarity"] == "positive"


def test_contextual_and_emotion_aggregates():
    assert emotion_label_totals(
        {"global_stats": {"label_totals": {"joy": 2.0, "anger": 1.0}}}
    )[0][0] == "joy"
    counts = contextual_label_counts(
        {
            "units": [
                {"top_label": "joy"},
                {"top_label": "joy"},
                {"top_label": "sadness"},
            ]
        }
    )
    assert counts[0] == ("joy", 2.0)


def test_group_action_items_and_motifs():
    groups = group_action_items(
        {
            "items": [
                {"record_type": "decision", "text": "Ship v1"},
                {"record_type": "action_item", "text": "Write tests"},
                {"record_type": "open_question", "text": "Budget?"},
            ]
        }
    )
    assert list(groups.keys()) == ["action_item", "decision", "open_question"]
    motifs = motif_rows(
        {
            "motifs": [
                {"unit_id_a": "u1", "unit_id_b": "u2", "similarity": 0.9},
            ]
        }
    )
    assert motifs[0]["similarity"] == 0.9
