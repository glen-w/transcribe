"""Named LLM chunking / grounding / reduction policy ids (core LLM contract)."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument, AnalysisUnit

CHUNKING_UNITS_V1 = "notebook_chunks_units_v1"
REDUCTION_MAP_REDUCE_V1 = "notebook_map_reduce_v1"
TOKEN_ESTIMATOR_V1 = "whitespace_tokens_v1"
GROUND_DOC_CHUNKS_V1 = "ground_doc_chunks_v1"
GROUND_HIGHLIGHTS_SUMMARY_V1 = "ground_highlights_summary_v1"

DEFAULT_MAX_TOKENS = 1500
DEFAULT_TOTAL_PROMPT_TOKENS = 6000


def estimate_tokens(text: str) -> int:
    """Pinned ``whitespace_tokens_v1`` estimator (deterministic, dependency-free)."""
    parts = (text or "").split()
    return max(len(parts), 1 if (text or "").strip() else 0)


def _sub_split_unit(unit: AnalysisUnit, *, max_tokens: int) -> list[dict[str, Any]]:
    text = unit.text
    if estimate_tokens(text) <= max_tokens:
        cite_id = unit.unit_id
        return [
            {
                "unit_ids": [unit.unit_id],
                "cite_ids": [cite_id],
                "spans": [
                    {
                        "unit_id": unit.unit_id,
                        "cite_id": cite_id,
                        "char_start": 0,
                        "char_end": len(text),
                    }
                ],
                "text": text,
            }
        ]

    words = text.split()
    pieces: list[dict[str, Any]] = []
    search_from = 0
    buf_words: list[str] = []
    buf_start: int | None = None
    sub_idx = 0

    def flush() -> None:
        nonlocal buf_words, buf_start, sub_idx, search_from
        if not buf_words or buf_start is None:
            return
        piece_text = " ".join(buf_words)
        end = buf_start + len(piece_text)
        if text[buf_start:end] != piece_text:
            end = min(len(text), buf_start + len(piece_text))
            piece_text = text[buf_start:end]
        cite_id = f"{unit.unit_id}#s{sub_idx}"
        pieces.append(
            {
                "unit_ids": [unit.unit_id],
                "cite_ids": [cite_id],
                "spans": [
                    {
                        "unit_id": unit.unit_id,
                        "cite_id": cite_id,
                        "char_start": buf_start,
                        "char_end": end,
                    }
                ],
                "text": piece_text,
            }
        )
        sub_idx += 1
        buf_words, buf_start = [], None

    for word in words:
        idx = text.find(word, search_from)
        if idx < 0:
            idx = search_from
        if not buf_words:
            buf_start = idx
        candidate = buf_words + [word]
        if buf_words and estimate_tokens(" ".join(candidate)) > max_tokens:
            flush()
            buf_start = idx
            buf_words = [word]
        else:
            buf_words = candidate
        search_from = idx + len(word)
    flush()
    return pieces


def pack_units_v1(
    document: AnalysisDocument,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[dict[str, Any]]:
    """Pack units by ``order`` up to a token budget; sub-split oversized units.

    Policy id: ``notebook_chunks_units_v1``. Never silently truncates.
    """
    chunks: list[dict[str, Any]] = []
    current_texts: list[str] = []
    current_ids: list[str] = []
    current_cites: list[str] = []
    current_spans: list[dict[str, Any]] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current_texts, current_ids, current_cites, current_spans, current_tokens
        if not current_texts:
            return
        chunks.append(
            {
                "chunk_index": len(chunks),
                "unit_ids": list(current_ids),
                "cite_ids": list(current_cites),
                "spans": list(current_spans),
                "text": "\n".join(current_texts),
                "token_estimate": current_tokens,
            }
        )
        current_texts, current_ids, current_cites, current_spans = [], [], [], []
        current_tokens = 0

    for unit in sorted(document.units, key=lambda u: (u.order, u.unit_id)):
        pieces = _sub_split_unit(unit, max_tokens=max_tokens)
        for piece in pieces:
            piece_tokens = estimate_tokens(piece["text"])
            add = piece_tokens + (1 if current_texts else 0)
            if current_texts and current_tokens + add > max_tokens:
                flush()
                add = piece_tokens
            current_texts.append(piece["text"])
            for uid in piece["unit_ids"]:
                if uid not in current_ids:
                    current_ids.append(uid)
            current_cites.extend(piece["cite_ids"])
            current_spans.extend(piece["spans"])
            current_tokens += add
    flush()
    return chunks


def select_chunks_for_prompt(
    chunks: list[dict[str, Any]],
    *,
    total_token_budget: int = DEFAULT_TOTAL_PROMPT_TOKENS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    used = 0
    for ch in chunks:
        cost = int(ch.get("token_estimate") or estimate_tokens(ch["text"]))
        if selected and used + cost > total_token_budget:
            return selected, chunks[len(selected) :]
        selected.append(ch)
        used += cost
    return selected, []


def format_chunk_excerpts(chunks: list[dict[str, Any]]) -> str:
    parts = []
    for ch in chunks:
        cites = ",".join(ch.get("cite_ids") or ch.get("unit_ids") or [])
        parts.append(f"[chunk {ch['chunk_index']} cites={cites}]\n{ch['text']}")
    return "\n\n".join(parts)


def cite_ids_from_chunks(chunks: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for ch in chunks:
        for cid in ch.get("cite_ids") or []:
            out.add(str(cid))
        for uid in ch.get("unit_ids") or []:
            out.add(str(uid))
    return out


def chunks_fingerprint(chunks: list[dict[str, Any]]) -> str:
    from hashlib import sha256
    from transcribe.domain.fingerprint import canonical_json_bytes
    return sha256(canonical_json_bytes(chunks)).hexdigest()


def filter_units_by_ids(
    document: AnalysisDocument, eligible_ids: list[str]
) -> list[AnalysisUnit]:
    allow = set(eligible_ids)
    return [u for u in document.units if u.unit_id in allow]


def resolve_span_quote(
    document: AnalysisDocument, cite_id: str
) -> dict[str, Any] | None:
    from hashlib import sha256
    unit_id = cite_id.split("#", 1)[0]
    by_id = {u.unit_id: u for u in document.units}
    unit = by_id.get(unit_id)
    if unit is None:
        return None
    char_start, char_end = 0, len(unit.text)
    if "#" in cite_id and cite_id.rsplit("#", 1)[-1].startswith("s"):
        for piece in _sub_split_unit(unit, max_tokens=DEFAULT_MAX_TOKENS):
            for span in piece["spans"]:
                if span["cite_id"] == cite_id:
                    char_start = int(span["char_start"])
                    char_end = int(span["char_end"])
                    break
    quote = unit.text[char_start:char_end]
    return {
        "unit_id": unit_id,
        "cite_id": cite_id,
        "char_start": char_start,
        "char_end": char_end,
        "quote": quote,
        "content_fingerprint": sha256(quote.encode("utf-8")).hexdigest(),
        "source_ref": dict(unit.source_ref),
    }


__all__ = [
    "CHUNKING_UNITS_V1",
    "REDUCTION_MAP_REDUCE_V1",
    "TOKEN_ESTIMATOR_V1",
    "GROUND_DOC_CHUNKS_V1",
    "GROUND_HIGHLIGHTS_SUMMARY_V1",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_TOTAL_PROMPT_TOKENS",
    "estimate_tokens",
    "pack_units_v1",
    "select_chunks_for_prompt",
    "format_chunk_excerpts",
    "cite_ids_from_chunks",
    "chunks_fingerprint",
    "filter_units_by_ids",
    "resolve_span_quote",
]
