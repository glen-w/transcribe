"""Entity sentiment — hard parents ner + sentiment."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument

MODULE_ID = "entity_sentiment"
MODULE_VERSION = "1.4.0"
PAYLOAD_SCHEMA = "entity_sentiment_payload_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


def entity_sentiment_config() -> dict[str, Any]:
    return {"payload_schema": PAYLOAD_SCHEMA, "algorithm_version": "entity_sentiment_join_v1"}


def provenance_files() -> list[dict[str, str]]:
    return []


class EntitySentimentModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = "Join NER entities to unit-level sentiment chronology; no speakers"

    def cache_config(self) -> dict[str, Any]:
        return entity_sentiment_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        parents = parents or {}
        ner = parents.get("ner") or {}
        sentiment = parents.get("sentiment") or {}
        if not document.units:
            return {"outcome": "insufficient_data", "payload": {}}

        by_unit_sent = {
            row.get("unit_id"): row
            for row in (sentiment.get("units") or [])
            if isinstance(row, dict)
        }
        entities = ner.get("entities") or []
        joined: list[dict[str, Any]] = []
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            unit_id = ent.get("unit_id")
            sent = by_unit_sent.get(unit_id) or {}
            # NER payload uses ``surface``; accept ``text`` for compatibility.
            surface = ent.get("text") if ent.get("text") is not None else ent.get("surface")
            joined.append(
                {
                    "text": surface,
                    "label": ent.get("label"),
                    "unit_id": unit_id,
                    "sentiment": {
                        "compound": sent.get("compound"),
                        "label": sent.get("label"),
                    },
                }
            )
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "entities": joined,
                "n_entities": len(joined),
            },
        }
