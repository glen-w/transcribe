"""llm_custom_qa — grounded Ask notebook with unit evidence."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.chunking import format_chunk_excerpts, resolve_span_quote
from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.llm_runtime import TextLLMContext
from transcribe.analysis.modules._llm_common import (
    generation_settings,
    GROUND_DOC_CHUNKS_V1,
    PROMPT_VERSION,
    as_bool,
    as_str_list,
    parse_json_object,
    prepared_excerpts,
    require_llm_ctx,
)

MODULE_ID = "llm_custom_qa"
MODULE_VERSION = "1e.2.1"
PAYLOAD_SCHEMA = "llm_custom_qa_payload_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"
SYSTEM = (
    "Answer only from the notebook excerpts. JSON only: "
    '{"answer":"...","unit_ids":["..."],"abstain":false}. '
    "If unsupported, set abstain true and empty answer. "
    "unit_ids must be cite ids from the excerpts."
)


def llm_custom_qa_config(*, question_text: str = "") -> dict[str, Any]:
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "prompt_version": PROMPT_VERSION,
        "grounding_strategy_id": GROUND_DOC_CHUNKS_V1,
        "question_text": question_text,
    }


def provenance_files() -> list[dict[str, str]]:
    return []


class LLMCustomQAModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = "Grounded QA with unit citations; refuses unsupported answers"

    def __init__(self, question_text: str = "") -> None:
        self.question_text = question_text

    def cache_config(self) -> dict[str, Any]:
        return llm_custom_qa_config(question_text=self.question_text)

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: TextLLMContext | None = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = parents
        if not document.units or not document.text.strip():
            return {"outcome": "insufficient_data", "payload": {}}
        question = (
            question_text if question_text is not None else self.question_text or ""
        ).strip()
        if not question:
            return {
                "outcome": "insufficient_data",
                "payload": {},
                "warnings": [
                    {"code": "missing_question", "message": "question_text required"}
                ],
            }
        ctx = require_llm_ctx(llm_ctx)
        if not isinstance(ctx, TextLLMContext):
            return ctx

        meta = prepared_excerpts(document)
        if meta["needs_map_reduce"]:
            return self._map_reduce_qa(document, ctx, question, meta)

        allowed = meta["cite_ids"]
        prompt = (
            f"Question: {question}\n\nExcerpts:\n{meta['excerpt_text']}\n\n"
            "Answer JSON with unit_ids drawn only from the excerpts."
        )
        try:
            raw = ctx.client.generate(
                model=ctx.model_name,
                prompt=prompt,
                system=SYSTEM,
                options=generation_settings(),
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "outcome": "failed",
                "payload": {"error": {"code": "llm_generate", "message": str(exc)}},
            }
        return self._validate_answer(document, question, raw, allowed, ctx.model_name)

    def _map_reduce_qa(
        self,
        document: AnalysisDocument,
        ctx: TextLLMContext,
        question: str,
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        last_raw = ""
        for ch in meta["all_chunks"]:
            allowed = set(ch.get("cite_ids") or []) | set(ch.get("unit_ids") or [])
            prompt = (
                f"Question: {question}\n\nExcerpts:\n{format_chunk_excerpts([ch])}\n\n"
                "Answer JSON with unit_ids drawn only from the excerpts."
            )
            try:
                raw = ctx.client.generate(
                    model=ctx.model_name,
                    prompt=prompt,
                    system=SYSTEM,
                    options=generation_settings(),
                )
            except Exception as exc:  # noqa: BLE001
                return {
                    "outcome": "failed",
                    "payload": {"error": {"code": "llm_generate", "message": str(exc)}},
                }
            last_raw = raw
            result = self._validate_answer(
                document, question, raw, allowed, ctx.model_name
            )
            if result["outcome"] == "success":
                return result
        return self._validate_answer(
            document, question, last_raw, meta["cite_ids"], ctx.model_name
        )

    def _validate_answer(
        self,
        document: AnalysisDocument,
        question: str,
        raw: str,
        allowed: set[str],
        model: str,
    ) -> dict[str, Any]:
        parsed = parse_json_object(raw)
        if not parsed:
            return {
                "outcome": "skipped_not_applicable",
                "payload": {
                    "schema": PAYLOAD_SCHEMA,
                    "abstain": True,
                    "question": question,
                },
                "warnings": [
                    {
                        "code": "abstain_unparseable",
                        "message": "model output abstained / failed schema validation",
                    }
                ],
                "diagnostics": {"raw_bounded": (raw or "")[:2000]},
            }
        abstain = as_bool(parsed.get("abstain"))
        if abstain is None and "abstain" in parsed:
            return {
                "outcome": "skipped_not_applicable",
                "payload": {
                    "schema": PAYLOAD_SCHEMA,
                    "abstain": True,
                    "question": question,
                },
                "warnings": [
                    {
                        "code": "abstain_unparseable",
                        "message": "abstain must be a JSON boolean",
                    }
                ],
                "diagnostics": {"raw_bounded": (raw or "")[:2000]},
            }
        if abstain is True:
            return {
                "outcome": "skipped_not_applicable",
                "payload": {
                    "schema": PAYLOAD_SCHEMA,
                    "answer": None,
                    "abstain": True,
                    "question": question,
                },
                "warnings": [
                    {
                        "code": "abstain_unsupported",
                        "message": "question unsupported by notebook text",
                    }
                ],
            }
        unit_ids = as_str_list(parsed.get("unit_ids"), max_items=32)
        if unit_ids is None:
            return {
                "outcome": "skipped_not_applicable",
                "payload": {
                    "schema": PAYLOAD_SCHEMA,
                    "abstain": True,
                    "question": question,
                },
                "warnings": [
                    {
                        "code": "abstain_unparseable",
                        "message": "unit_ids must be a JSON array of strings",
                    }
                ],
                "diagnostics": {"raw_bounded": (raw or "")[:2000]},
            }
        grounded = [u for u in unit_ids if u in allowed]
        answer = parsed.get("answer")
        if not isinstance(answer, str) or not answer.strip() or not grounded:
            return {
                "outcome": "skipped_not_applicable",
                "payload": {
                    "schema": PAYLOAD_SCHEMA,
                    "answer": None,
                    "abstain": True,
                    "question": question,
                },
                "warnings": [
                    {
                        "code": "abstain_ungrounded",
                        "message": "refused: missing grounded unit evidence from excerpts",
                    }
                ],
            }
        evidence = []
        for cid in grounded:
            resolved = resolve_span_quote(document, cid)
            if resolved is None:
                continue
            evidence.append(
                {
                    "unit_id": resolved["unit_id"],
                    "cite_id": resolved["cite_id"],
                    "source_ref": resolved["source_ref"],
                    "quote": resolved["quote"],
                    "content_fingerprint": resolved["content_fingerprint"],
                    "char_start": resolved["char_start"],
                    "char_end": resolved["char_end"],
                    "question": question,
                }
            )
        if not evidence:
            return {
                "outcome": "skipped_not_applicable",
                "payload": {
                    "schema": PAYLOAD_SCHEMA,
                    "answer": None,
                    "abstain": True,
                    "question": question,
                },
                "warnings": [
                    {
                        "code": "abstain_ungrounded",
                        "message": "refused: citations unresolved against current document",
                    }
                ],
            }
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "question": question,
                "answer": answer.strip(),
                "unit_ids": [e["cite_id"] for e in evidence],
                "honesty_label": "llm_generated",
                "model": model,
            },
            "evidence": evidence,
        }
