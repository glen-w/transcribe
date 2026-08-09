"""llm_summary — optional local text LLM abstractive summary."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.llm_runtime import TextLLMContext
from transcribe.analysis.modules._llm_common import (
    GROUND_DOC_CHUNKS_V1,
    PROMPT_VERSION,
    as_str_list,
    map_reduce_generate,
    parse_json_object,
    require_llm_ctx,
)

MODULE_ID = "llm_summary"
MODULE_VERSION = "1e.2.1"
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


def _parse_summary(raw: str) -> dict[str, Any] | None:
    parsed = parse_json_object(raw)
    if not parsed:
        return None
    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None
    bullets = as_str_list(parsed.get("bullets"), max_items=12)
    if bullets is None:
        if "bullets" in parsed and parsed.get("bullets") is not None:
            return None
        bullets = []
    return {"summary": summary.strip(), "bullets": bullets}


def _reduce_summaries(partials: list[dict[str, Any]]) -> dict[str, Any]:
    summaries = [p["summary"] for p in partials if p.get("summary")]
    bullets: list[str] = []
    for p in partials:
        for b in p.get("bullets") or []:
            if b not in bullets:
                bullets.append(b)
    return {"summary": " ".join(summaries)[:4000], "bullets": bullets[:12]}


class LLMSummaryModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = "Optional Ollama abstractive summary over chunked AnalysisDocument"

    def cache_config(self) -> dict[str, Any]:
        return llm_summary_config()

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
                user_suffix="Produce the JSON summary.",
                parse_partial=_parse_summary,
                reduce_partials=_reduce_summaries,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "outcome": "failed",
                "payload": {"error": {"code": "llm_generate", "message": str(exc)}},
            }
        if not reduced or not reduced.get("summary"):
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
                "summary": reduced["summary"],
                "bullets": reduced.get("bullets") or [],
                "honesty_label": "llm_generated",
                "model": ctx.model_name,
            },
        }
