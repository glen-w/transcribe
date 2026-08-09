"""llm_action_items — optional local LLM tasks/decisions/open questions."""

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

MODULE_ID = "llm_action_items"
MODULE_VERSION = "1e.2.0"
PAYLOAD_SCHEMA = "llm_action_items_payload_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"
SYSTEM = (
    "Extract notebook action items. JSON only: "
    '{"items":[{"record_type":"action_item|decision|open_question","text":"..."}]}.'
)


def llm_action_items_config() -> dict[str, Any]:
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "prompt_version": PROMPT_VERSION,
        "grounding_strategy_id": GROUND_DOC_CHUNKS_V1,
    }


def provenance_files() -> list[dict[str, str]]:
    return []


class LLMActionItemsModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = "Optional Ollama action/decision/open-question extraction for notebooks"

    def cache_config(self) -> dict[str, Any]:
        return llm_action_items_config()

    def run(self, document: AnalysisDocument, *, parents: dict | None = None) -> dict[str, Any]:
        _ = parents
        if not document.units or not document.text.strip():
            return {"outcome": "insufficient_data", "payload": {}}
        pre = llm_preflight()
        if not pre["ok"]:
            return pre["result"]
        client = pre["client"]
        model = pre["model"]
        prompt = f"Notebook text:\n{chunk_context(document)}\n\nExtract items JSON."
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
        items = (parsed or {}).get("items") if parsed else None
        if not isinstance(items, list):
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
        clean = []
        for row in items[:40]:
            if not isinstance(row, dict) or not row.get("text"):
                continue
            clean.append(
                {
                    "record_type": str(row.get("record_type") or "action_item"),
                    "text": str(row["text"])[:500],
                }
            )
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "items": clean,
                "n_items": len(clean),
                "honesty_label": "llm_generated",
                "model": model,
            },
        }
