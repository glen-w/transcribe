"""Fine-grained emotion — optional heavy extra; never silent lexicon substitute."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument

MODULE_ID = "fine_grained_emotion"
MODULE_VERSION = "1d.0"
PAYLOAD_SCHEMA = "fine_grained_emotion_payload_v1"
ALGORITHM_VERSION = "fine_grained_extra_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


def fine_grained_emotion_config() -> dict[str, Any]:
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
    }


def provenance_files() -> list[dict[str, str]]:
    return []


def _transformer_emotion_available() -> bool:
    try:
        import transformers  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


class FineGrainedEmotionModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = (
        "Optional transformer emotion extra behind unavailable_extra; "
        "does not silently reuse emotion_lexicon_v1 under this module_id"
    )

    def cache_config(self) -> dict[str, Any]:
        return fine_grained_emotion_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = parents, llm_ctx, question_text
        if not document.units or not document.text.strip():
            return {"outcome": "insufficient_data", "payload": {}, "capability_reason": None}
        if not _transformer_emotion_available():
            return {
                "outcome": "skipped_not_applicable",
                "payload": {},
                "capability_reason": "unavailable_extra",
                "warnings": [
                    {
                        "code": "unavailable_extra",
                        "message": "transformers package not installed for fine_grained_emotion",
                    }
                ],
            }
        return {
            "outcome": "skipped_not_applicable",
            "payload": {},
            "capability_reason": "unavailable_extra",
            "warnings": [
                {
                    "code": "unavailable_extra",
                    "message": (
                        "transformers installed but fine-grained emotion "
                        "model runner not configured in this build"
                    ),
                }
            ],
        }
