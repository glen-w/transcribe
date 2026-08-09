"""Shared helpers for optional LLM analysis modules."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.chunking import (
    CHUNKING_UNITS_V1,
    GROUND_DOC_CHUNKS_V1,
    GROUND_HIGHLIGHTS_SUMMARY_V1,
    chunks_fingerprint,
    pack_units_v1,
)
from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.llm_runtime import (
    get_text_llm_client,
    parse_json_object,
)

PROMPT_VERSION = "1e.0"
GENERATION_SETTINGS = {"temperature": 0.0, "num_predict": 1024}


def llm_preflight(*, preferred_model: str | None = None) -> dict[str, Any]:
    """Return resolved model info or an unavailable_model skip result."""
    client = get_text_llm_client()
    if not client.healthcheck():
        return {
            "ok": False,
            "result": {
                "outcome": "skipped_not_applicable",
                "payload": {},
                "capability_reason": "unavailable_model",
                "warnings": [
                    {
                        "code": "unavailable_model",
                        "message": "text LLM runtime unavailable",
                    }
                ],
            },
        }
    model = client.resolve_model(preferred_model)
    if not model:
        return {
            "ok": False,
            "result": {
                "outcome": "skipped_not_applicable",
                "payload": {},
                "capability_reason": "unavailable_model",
                "warnings": [
                    {
                        "code": "unavailable_model",
                        "message": "no text model resolved",
                    }
                ],
            },
        }
    return {
        "ok": True,
        "model": model,
        "digest": client.model_digest(model),
        "client": client,
    }


def build_llm_identity_fields(
    *,
    document: AnalysisDocument,
    grounding_strategy_id: str,
    question_text: str | None = None,
    model: str,
    digest: str,
) -> dict[str, Any]:
    chunks = pack_units_v1(document)
    return {
        "resolved_model_digest": digest,
        "llm": {
            "prompt_or_template_version": PROMPT_VERSION,
            "generation_settings": dict(GENERATION_SETTINGS),
            "grounding_strategy_id": grounding_strategy_id,
            "chunking_policy_id": CHUNKING_UNITS_V1,
            "question_text": question_text,
            "resolved_model_digest": digest,
            "input_fingerprint": chunks_fingerprint(chunks),
            "model_name": model,
        },
    }


def chunk_context(document: AnalysisDocument) -> str:
    chunks = pack_units_v1(document)
    parts = []
    for ch in chunks:
        parts.append(f"[chunk {ch['chunk_index']} units={','.join(ch['unit_ids'])}]\n{ch['text']}")
    return "\n\n".join(parts)


def grounded_unit_ids(document: AnalysisDocument) -> set[str]:
    return {u.unit_id for u in document.units}


__all__ = [
    "PROMPT_VERSION",
    "GENERATION_SETTINGS",
    "CHUNKING_UNITS_V1",
    "GROUND_DOC_CHUNKS_V1",
    "GROUND_HIGHLIGHTS_SUMMARY_V1",
    "llm_preflight",
    "build_llm_identity_fields",
    "chunk_context",
    "grounded_unit_ids",
    "parse_json_object",
]
