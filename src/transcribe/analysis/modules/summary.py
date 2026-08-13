"""Summary — hard parent highlights."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument

MODULE_ID = "summary"
MODULE_VERSION = "1e.1.0"
PAYLOAD_SCHEMA = "summary_payload_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


def summary_config() -> dict[str, Any]:
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "algorithm_version": "summary_from_highlights_v1",
    }


def provenance_files() -> list[dict[str, str]]:
    return []


class SummaryModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = "Executive brief from highlights quotes; no speakers"

    def cache_config(self) -> dict[str, Any]:
        return summary_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        parents = parents or {}
        highlights = parents.get("highlights") or {}
        quotes = highlights.get("quotes") or []
        if not quotes:
            return {
                "outcome": "insufficient_data",
                "payload": {},
                "warnings": [
                    {
                        "code": "no_highlights",
                        "message": "highlights produced no quotes",
                    }
                ],
            }
        bullets = [str(q.get("text") or "").strip() for q in quotes[:8] if q.get("text")]
        overview = " ".join(bullets[:3])[:800]
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "overview": overview,
                "bullets": bullets,
                "n_units": len(document.units),
                "source_quote_ids": [q.get("quote_id") for q in quotes[:8]],
            },
        }
