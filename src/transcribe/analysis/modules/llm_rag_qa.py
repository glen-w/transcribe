"""llm_rag_qa — retrieve-then-generate Ask with unit evidence."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.chunking import GROUND_RAG_HITS_V1, REDUCTION_RAG_PACK_V1, resolve_span_quote
from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.llm_runtime import TextLLMContext
from transcribe.analysis.modules._llm_common import (
    PROMPT_VERSION,
    as_bool,
    as_str_list,
    generation_settings,
    parse_json_object,
    require_llm_ctx,
)
from transcribe.analysis.rag.exceptions import IndexMismatch, IndexMissing, RagUnavailable
from transcribe.analysis.rag.ingest import RagRunContext, ensure_index
from transcribe.analysis.rag.retrieve import format_hit_excerpts, pack_hits, search_hits
from transcribe.config.facade import require_operation_config
from transcribe.config.models import RagConfig

MODULE_ID = "llm_rag_qa"
MODULE_VERSION = "1.0.0"
PAYLOAD_SCHEMA = "llm_rag_qa_payload_v1"
TX_COMMIT = "n/a"
SYSTEM = (
    "Answer only from the retrieved notebook excerpts. JSON only: "
    '{"answer":"...","unit_ids":["..."],"abstain":false}. '
    "If unsupported, set abstain true and empty answer. "
    "unit_ids must be unit ids from the excerpts."
)


def _rag_cfg() -> RagConfig:
    try:
        return require_operation_config().analysis.rag
    except Exception:  # noqa: BLE001
        return RagConfig()


def llm_rag_qa_config(*, question_text: str = "") -> dict[str, Any]:
    rag = _rag_cfg()
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "prompt_version": PROMPT_VERSION,
        "grounding_strategy_id": GROUND_RAG_HITS_V1,
        "reduction_policy_id": REDUCTION_RAG_PACK_V1,
        "question_text": question_text,
        **rag.fingerprint_dict(),
    }


def provenance_files() -> list[dict[str, str]]:
    return []


class LLMRagQAModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = (
        "Paperful-shaped RAG Ask: hybrid retrieve then JSON abstain/cite; "
        "optional extra behind unavailable_extra"
    )

    def __init__(self, question_text: str = "") -> None:
        self.question_text = question_text

    def cache_config(self) -> dict[str, Any]:
        return llm_rag_qa_config(question_text=self.question_text)

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: TextLLMContext | None = None,
        question_text: str | None = None,
        rag_ctx: RagRunContext | None = None,
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
                "warnings": [{"code": "missing_question", "message": "question_text required"}],
            }
        rag = _rag_cfg()
        if not rag.enabled:
            return {
                "outcome": "skipped_not_applicable",
                "payload": {},
                "warnings": [
                    {
                        "code": "rag_disabled",
                        "message": "Ask RAG is off — enable it under Settings → Analysis.",
                    }
                ],
            }
        if rag_ctx is None:
            return {
                "outcome": "insufficient_data",
                "payload": {},
                "capability_reason": "unavailable_dependency",
                "warnings": [
                    {
                        "code": "rag_ctx_missing",
                        "message": "RAG index path was not supplied",
                    }
                ],
            }
        ctx = require_llm_ctx(llm_ctx)
        if not isinstance(ctx, TextLLMContext):
            return ctx
        try:
            index, embedder, ingest = ensure_index(document, rag, rag_ctx)
        except RagUnavailable as exc:
            return {
                "outcome": "skipped_not_applicable",
                "payload": {},
                "capability_reason": "unavailable_extra",
                "warnings": [{"code": "unavailable_extra", "message": str(exc)}],
            }
        except (IndexMissing, IndexMismatch) as exc:
            return {
                "outcome": "failed",
                "payload": {"error": {"code": "rag_index", "message": str(exc)}},
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "outcome": "failed",
                "payload": {"error": {"code": "rag_ingest", "message": str(exc)}},
            }

        hits = search_hits(
            question,
            index=index,
            embedder=embedder,
            k=rag.top_k,
            hybrid=rag.hybrid,
        )
        packed = pack_hits(hits, max_chars=rag.max_context_chars)
        retrieved = [
            {
                "chunk_id": h.chunk_id,
                "unit_id": h.unit_id,
                "page_id": h.page_id,
                "score": h.score,
                "text": h.text,
            }
            for h in packed
        ]
        if not packed:
            return {
                "outcome": "insufficient_data",
                "payload": {
                    "schema": PAYLOAD_SCHEMA,
                    "question": question,
                    "abstain": True,
                    "retrieved": [],
                    "ingest_rebuilt": ingest.rebuilt,
                },
                "warnings": [
                    {
                        "code": "rag_no_hits",
                        "message": "Nothing in the index matches that question.",
                    }
                ],
            }

        allowed = {h.unit_id for h in packed}
        prompt = (
            f"Question: {question}\n\nExcerpts:\n{format_hit_excerpts(packed)}\n\n"
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
        result = self._validate_answer(document, question, raw, allowed, ctx.model_name)
        payload = dict(result.get("payload") or {})
        payload["retrieved"] = retrieved
        payload["ingest_rebuilt"] = ingest.rebuilt
        result["payload"] = payload
        return result

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
            return _abstain(question, "abstain_unparseable", "model output abstained / failed schema validation", raw)
        abstain = as_bool(parsed.get("abstain"))
        if abstain is None and "abstain" in parsed:
            return _abstain(question, "abstain_unparseable", "abstain must be a JSON boolean", raw)
        if abstain is True:
            return _abstain(
                question,
                "abstain_unsupported",
                "question unsupported by notebook text",
                None,
                answer=None,
            )
        unit_ids = as_str_list(parsed.get("unit_ids"), max_items=32)
        if unit_ids is None:
            return _abstain(question, "abstain_unparseable", "unit_ids must be a JSON array of strings", raw)
        grounded = [u for u in unit_ids if u in allowed]
        answer = parsed.get("answer")
        if not isinstance(answer, str) or not answer.strip() or not grounded:
            return _abstain(
                question,
                "abstain_ungrounded",
                "refused: missing grounded unit evidence from excerpts",
                None,
            )
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
            return _abstain(
                question,
                "abstain_ungrounded",
                "refused: citations unresolved against current document",
                None,
            )
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


def _abstain(
    question: str,
    code: str,
    message: str,
    raw: str | None,
    *,
    answer: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "outcome": "skipped_not_applicable",
        "payload": {
            "schema": PAYLOAD_SCHEMA,
            "abstain": True,
            "question": question,
            "answer": answer,
        },
        "warnings": [{"code": code, "message": message}],
    }
    if raw:
        out["diagnostics"] = {"raw_bounded": (raw or "")[:2000]}
    return out
