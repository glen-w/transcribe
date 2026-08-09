"""llm_action_items — optional local LLM tasks/decisions/open questions."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.llm_runtime import TextLLMContext
from transcribe.analysis.modules._llm_common import (
    GROUND_DOC_CHUNKS_V1,
    PROMPT_VERSION,
    map_reduce_generate,
    parse_json_object,
    require_llm_ctx,
)

MODULE_ID = "llm_action_items"
MODULE_VERSION = "1e.2.1"
PAYLOAD_SCHEMA = "llm_action_items_payload_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"
_ALLOWED_TYPES = frozenset({"action_item", "decision", "open_question"})
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


def _parse_items(raw: str) -> list[dict[str, str]] | None:
    parsed = parse_json_object(raw)
    if not parsed:
        return None
    items = parsed.get("items")
    if not isinstance(items, list):
        return None
    clean: list[dict[str, str]] = []
    for row in items[:40]:
        if not isinstance(row, dict):
            return None
        text = row.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        rtype = row.get("record_type", "action_item")
        if not isinstance(rtype, str) or rtype not in _ALLOWED_TYPES:
            return None
        clean.append({"record_type": rtype, "text": text.strip()[:500]})
    return clean


def _reduce_items(partials: list[list[dict[str, str]]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for group in partials:
        for row in group:
            key = f"{row['record_type']}:{row['text']}"
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
            if len(out) >= 40:
                return out
    return out


class LLMActionItemsModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = "Optional Ollama action/decision/open-question extraction for notebooks"

    def cache_config(self) -> dict[str, Any]:
        return llm_action_items_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: TextLLMContext | None = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = parents, question_text
        if not document.units or not document.text.strip():
            return {"outcome": "insufficient_data", "payload": {}}
        ctx = require_llm_ctx(llm_ctx)
        if not isinstance(ctx, TextLLMContext):
            return ctx
        try:
            reduced, raw_diag, _meta = map_reduce_generate(
                llm_ctx=ctx,
                document=document,
                system=SYSTEM,
                user_suffix="Extract items JSON.",
                parse_partial=_parse_items,
                reduce_partials=_reduce_items,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "outcome": "failed",
                "payload": {"error": {"code": "llm_generate", "message": str(exc)}},
            }
        if reduced is None:
            return {
                "outcome": "skipped_not_applicable",
                "payload": {"schema": PAYLOAD_SCHEMA, "abstain": True},
                "warnings": [
                    {
                        "code": "abstain_unparseable",
                        "message": "model output abstained / failed schema validation",
                    }
                ],
                "diagnostics": {"raw_bounded": raw_diag},
            }
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "items": reduced,
                "n_items": len(reduced),
                "honesty_label": "llm_generated",
                "model": ctx.model_name,
            },
        }
