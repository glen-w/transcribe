"""Named LLM chunking / grounding policy ids (contract freeze for Wave 1e)."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument, AnalysisUnit

# --- Frozen policy ids (analysis-run-storage `llm.chunking_policy_id`) ---
CHUNKING_UNITS_V1 = "notebook_chunks_units_v1"
GROUND_DOC_CHUNKS_V1 = "ground_doc_chunks_v1"
GROUND_HIGHLIGHTS_SUMMARY_V1 = "ground_highlights_summary_v1"

DEFAULT_MAX_CHARS = 6000


def pack_units_v1(
    document: AnalysisDocument,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[dict[str, Any]]:
    """Deterministic pack of units by ``order`` up to ``max_chars`` per chunk.

    Policy id: ``notebook_chunks_units_v1``.
    """
    chunks: list[dict[str, Any]] = []
    current_texts: list[str] = []
    current_ids: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current_texts, current_ids, current_len
        if not current_texts:
            return
        chunks.append(
            {
                "chunk_index": len(chunks),
                "unit_ids": list(current_ids),
                "text": "\n".join(current_texts),
            }
        )
        current_texts, current_ids, current_len = [], [], 0

    for unit in sorted(document.units, key=lambda u: (u.order, u.unit_id)):
        piece = unit.text
        add = len(piece) + (1 if current_texts else 0)
        if current_texts and current_len + add > max_chars:
            flush()
            add = len(piece)
        # Oversized single unit: emit alone (still bounded by one unit).
        if not current_texts and len(piece) > max_chars:
            chunks.append(
                {
                    "chunk_index": len(chunks),
                    "unit_ids": [unit.unit_id],
                    "text": piece[:max_chars],
                }
            )
            continue
        current_texts.append(piece)
        current_ids.append(unit.unit_id)
        current_len += add
    flush()
    return chunks


def chunks_fingerprint(chunks: list[dict[str, Any]]) -> str:
    from hashlib import sha256

    from transcribe.domain.fingerprint import canonical_json_bytes

    return sha256(canonical_json_bytes(chunks)).hexdigest()


def filter_units_by_ids(
    document: AnalysisDocument, eligible_ids: list[str]
) -> list[AnalysisUnit]:
    allow = set(eligible_ids)
    return [u for u in document.units if u.unit_id in allow]


__all__ = [
    "CHUNKING_UNITS_V1",
    "GROUND_DOC_CHUNKS_V1",
    "GROUND_HIGHLIGHTS_SUMMARY_V1",
    "DEFAULT_MAX_CHARS",
    "pack_units_v1",
    "chunks_fingerprint",
    "filter_units_by_ids",
]
