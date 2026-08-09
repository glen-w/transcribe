"""Shared helpers for optional LLM analysis modules."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.chunking import (
    CHUNKING_UNITS_V1,
    DEFAULT_TOTAL_PROMPT_TOKENS,
    GROUND_DOC_CHUNKS_V1,
    GROUND_HIGHLIGHTS_SUMMARY_V1,
    REDUCTION_MAP_REDUCE_V1,
    TOKEN_ESTIMATOR_V1,
    chunks_fingerprint,
    cite_ids_from_chunks,
    format_chunk_excerpts,
    pack_units_v1,
    select_chunks_for_prompt,
)
from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.llm_runtime import (
    TextLLMContext,
    parse_json_object,
    unavailable_model_result,
)

PROMPT_VERSION = "1e.0"
GENERATION_SETTINGS = {"temperature": 0.0, "num_predict": 1024}


def require_llm_ctx(llm_ctx: TextLLMContext | None) -> dict[str, Any] | TextLLMContext:
    if llm_ctx is None:
        return unavailable_model_result()
    return llm_ctx


def prepared_excerpts(
    document: AnalysisDocument,
    *,
    total_token_budget: int = DEFAULT_TOTAL_PROMPT_TOKENS,
) -> dict[str, Any]:
    """Pack + select excerpts actually supplied to the model (map-reduce aware)."""
    all_chunks = pack_units_v1(document)
    selected, remainder = select_chunks_for_prompt(
        all_chunks, total_token_budget=total_token_budget
    )
    used = all_chunks if remainder else selected
    return {
        "all_chunks": all_chunks,
        "selected": selected,
        "remainder": remainder,
        "needs_map_reduce": bool(remainder),
        "excerpt_text": format_chunk_excerpts(selected),
        "cite_ids": cite_ids_from_chunks(used),
        "input_fingerprint": chunks_fingerprint(
            [
                {
                    "reduction_policy_id": REDUCTION_MAP_REDUCE_V1,
                    "mode": "map_reduce" if remainder else "single",
                    "chunk_indexes": [c["chunk_index"] for c in used],
                },
                *used,
            ]
        ),
    }


def build_llm_object(
    *,
    grounding_strategy_id: str,
    model: str | None,
    digest: str | None,
    input_fingerprint: str,
    question_text: str | None = None,
    reduction_policy_id: str = REDUCTION_MAP_REDUCE_V1,
) -> dict[str, Any]:
    return {
        "prompt_or_template_version": PROMPT_VERSION,
        "generation_settings": dict(GENERATION_SETTINGS),
        "grounding_strategy_id": grounding_strategy_id,
        "chunking_policy_id": CHUNKING_UNITS_V1,
        "reduction_policy_id": reduction_policy_id,
        "token_estimator_id": TOKEN_ESTIMATOR_V1,
        "question_text": question_text,
        "resolved_model_digest": digest,
        "input_fingerprint": input_fingerprint,
        "model_name": model,
    }


def map_reduce_generate(
    *,
    llm_ctx: TextLLMContext,
    document: AnalysisDocument,
    system: str,
    user_suffix: str,
    parse_partial: Any,
    reduce_partials: Any,
) -> tuple[Any | None, str | None, dict[str, Any]]:
    meta = prepared_excerpts(document)
    client = llm_ctx.client
    model = llm_ctx.model_name
    options = GENERATION_SETTINGS

    if not meta["needs_map_reduce"]:
        prompt = f"{meta['excerpt_text']}\n\n{user_suffix}"
        raw = client.generate(model=model, prompt=prompt, system=system, options=options)
        return parse_partial(raw), raw[:2000], meta

    partials: list[Any] = []
    raws: list[str] = []
    for ch in meta["all_chunks"]:
        excerpt = format_chunk_excerpts([ch])
        prompt = f"{excerpt}\n\n{user_suffix}"
        raw = client.generate(model=model, prompt=prompt, system=system, options=options)
        raws.append(raw[:500])
        partial = parse_partial(raw)
        if partial is not None:
            partials.append(partial)
    if not partials:
        return None, " | ".join(raws)[:2000], meta
    reduced = reduce_partials(partials)
    return reduced, " | ".join(raws)[:2000], meta


def as_str_list(value: Any, *, max_items: int = 12) -> list[str] | None:
    if not isinstance(value, list):
        return None
    out: list[str] = []
    for item in value[:max_items]:
        if not isinstance(item, str):
            return None
        text = item.strip()
        if text:
            out.append(text)
    return out


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


__all__ = [
    "PROMPT_VERSION",
    "GENERATION_SETTINGS",
    "CHUNKING_UNITS_V1",
    "REDUCTION_MAP_REDUCE_V1",
    "GROUND_DOC_CHUNKS_V1",
    "GROUND_HIGHLIGHTS_SUMMARY_V1",
    "require_llm_ctx",
    "prepared_excerpts",
    "build_llm_object",
    "map_reduce_generate",
    "as_str_list",
    "as_bool",
    "parse_json_object",
    "unavailable_model_result",
]
