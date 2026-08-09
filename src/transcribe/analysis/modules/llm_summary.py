"""llm_summary — optional local text LLM abstractive summary."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules._llm_common import (
    GENERATION_SETTINGS,
    GROUND_DOC_CHUNKS_V1,
    PROMPT_VERSION,
    chunk_context,
    llm_preflight,
    parse_json_object,
)

MODULE_ID = "llm_summary"
MODULE_VERSION = "1e.2.0"
PAYLOAD_SCHEMA = "llm_summary_payload_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"
SYSTEM = (
    "Summarize notebook OCR text. Reply with JSON only: "
    '{"summary":"...","bullets":["..."]}.'
)


def llm_summary_config() -> dict[str, Any]:
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "prompt_version": PROMPT_VERSION,
        "grounding_strategy_id": GROUND_DOC_CHUNKS_V1,
    }


def provenance_files() -> list[dict[str, str]]:
    return []


class LLMSummaryModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = "Optional Ollama abstractive summary over chunked AnalysisDocument"

    def cache_config(self) -> dict[str, Any]:
        return llm_summary_config()

    def run(self, document: AnalysisDocument, *, parents: dict | None = None) -> dict[str, Any]:
        _ = parents
        if not document.units or not document.text.strip():
            return {"outcome": "insufficient_data", "payload": {}}
        pre = llm_preflight()
        if not pre["ok"]:
            return pre["result"]
        client = pre["client"]
        model = pre["model"]
        context = chunk_context(document)
        prompt = f"Notebook text:\n{context}\n\nProduce the JSON summary."
        try:
            raw = client.generate(
                model=model,
                prompt=prompt,
                system=SYSTEM,
                options=GENERATION_SETTINGS,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "outcome": "failed",
                "payload": {"error": {"code": "llm_generate", "message": str(exc)}},
            }
        parsed = parse_json_object(raw)
        if not parsed or not parsed.get("summary"):
            return {
                "outcome": "skipped_not_applicable",
                "payload": {"raw": raw[:2000]},
                "warnings": [
                    {
                        "code": "abstain_unparseable",
                        "message": "model output abstained / unparseable",
                    }
                ],
            }
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "summary": str(parsed.get("summary")),
                "bullets": list(parsed.get("bullets") or [])[:12],
                "honesty_label": "llm_generated",
                "model": model,
            },
        }
