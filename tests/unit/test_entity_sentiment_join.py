"""Entity sentiment join preserves NER surface forms offline."""

from __future__ import annotations

from transcribe.analysis.document import AnalysisDocument, AnalysisUnit
from transcribe.analysis.modules.entity_sentiment import EntitySentimentModule


def test_entity_sentiment_joins_ner_surface_field():
    doc = AnalysisDocument(
        document_id="d",
        text="Alice was happy.",
        units=[
            AnalysisUnit(
                unit_id="u0",
                text="Alice was happy.",
                order=0.0,
                source_ref={"kind": "page", "page_id": "p0"},
            )
        ],
    )
    parents = {
        "ner": {
            "entities": [
                {"surface": "Alice", "label": "PERSON", "unit_id": "u0"},
            ]
        },
        "sentiment": {
            "units": [{"unit_id": "u0", "compound": 0.5, "label": "positive"}],
        },
    }
    result = EntitySentimentModule().run(doc, parents=parents)
    assert result["outcome"] == "success"
    assert result["payload"]["n_entities"] == 1
    row = result["payload"]["entities"][0]
    assert row["text"] == "Alice"
    assert row["label"] == "PERSON"
    assert row["sentiment"]["label"] == "positive"


def test_entity_sentiment_accepts_text_alias():
    doc = AnalysisDocument(
        document_id="d",
        text="Bob",
        units=[
            AnalysisUnit(
                unit_id="u0",
                text="Bob",
                order=0.0,
                source_ref={"kind": "page", "page_id": "p0"},
            )
        ],
    )
    result = EntitySentimentModule().run(
        doc,
        parents={
            "ner": {"entities": [{"text": "Bob", "label": "PERSON", "unit_id": "u0"}]},
            "sentiment": {"units": []},
        },
    )
    assert result["payload"]["entities"][0]["text"] == "Bob"
