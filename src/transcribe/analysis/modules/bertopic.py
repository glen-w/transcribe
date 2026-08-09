"""BERTopic — optional extra; never silently substitute another algorithm."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument

MODULE_ID = "bertopic"
MODULE_VERSION = "1c.0"
PAYLOAD_SCHEMA = "bertopic_payload_v1"
ALGORITHM_VERSION = "bertopic_extra_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


def bertopic_config() -> dict[str, Any]:
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
        "enrichment_mode": "baseline",
    }


def provenance_files() -> list[dict[str, str]]:
    return []


def _bertopic_available() -> bool:
    try:
        import bertopic  # noqa: F401

        return True
    except Exception:  # noqa: BLE001 — missing optional extra is expected
        return False


class BertopicModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = (
        "Optional BERTopic extra behind unavailable_extra; "
        "no silent LDA/seed-bucket substitute under this module_id"
    )

    def cache_config(self) -> dict[str, Any]:
        return bertopic_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = llm_ctx, question_text
        _ = parents
        if not document.units or not document.text.strip():
            return {
                "outcome": "insufficient_data",
                "payload": {},
                "capability_reason": None,
            }
        if not _bertopic_available():
            return {
                "outcome": "skipped_not_applicable",
                "payload": {},
                "capability_reason": "unavailable_extra",
                "warnings": [
                    {
                        "code": "unavailable_extra",
                        "message": "bertopic package not installed",
                    }
                ],
            }
        # Extra present but full BERTopic path is not wired yet —
        # still refuse silent substitute algorithms under this module_id.
        return {
            "outcome": "skipped_not_applicable",
            "payload": {},
            "capability_reason": "unavailable_extra",
            "warnings": [
                {
                    "code": "unavailable_extra",
                    "message": (
                        "bertopic installed but notebook BERTopic runner "
                        "not configured in this build"
                    ),
                }
            ],
        }
