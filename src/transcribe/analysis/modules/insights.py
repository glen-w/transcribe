"""Insights — hard parents highlights + topic_modeling; eligibility required."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument

MODULE_ID = "insights"
MODULE_VERSION = "1e.1.0"
PAYLOAD_SCHEMA = "insights_payload_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


def insights_config() -> dict[str, Any]:
    return {"payload_schema": PAYLOAD_SCHEMA, "algorithm_version": "insights_compose_v1"}


def provenance_files() -> list[dict[str, str]]:
    return []


class InsightsModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = "Compose themes from highlights + topics; notebook_eligibility_v1 replaces insight_eligibility"

    def cache_config(self) -> dict[str, Any]:
        return insights_config()

    def run(self, document: AnalysisDocument, *, parents: dict | None = None) -> dict[str, Any]:
        parents = parents or {}
        highlights = parents.get("highlights") or {}
        topics = parents.get("topic_modeling") or {}
        quotes = highlights.get("quotes") or []
        topic_rows = topics.get("topics") or []
        if not quotes and not topic_rows:
            return {"outcome": "insufficient_data", "payload": {}}

        theme_items = []
        for t in topic_rows[:8]:
            theme_items.append(
                {
                    "label": t.get("label"),
                    "terms": t.get("terms") or [],
                    "topic_id": t.get("topic_id"),
                }
            )
        notable = [
            {"quote_id": q.get("quote_id"), "text": q.get("text")}
            for q in quotes[:6]
        ]
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "themes": theme_items,
                "notable_quotes": notable,
                "n_eligible_units": len(document.units),
            },
        }
