"""Rank notebook passages for a question. No chat model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

_OVERFETCH = 3
MAX_CHUNKS_PER_PAGE = 3


class _Index(Protocol):
    def search(
        self,
        vector: list[float],
        text: str,
        *,
        k: int,
        hybrid: bool = True,
    ) -> list[dict[str, Any]]: ...


class _Embedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    unit_id: str
    page_id: str
    chunk_index: int
    text: str
    score: float
    content_fingerprint: str
    char_start: int
    char_end: int


def search_hits(
    query: str,
    *,
    index: _Index,
    embedder: _Embedder,
    k: int = 10,
    hybrid: bool = True,
) -> list[Hit]:
    if not query.strip() or k < 1:
        return []
    rows = index.search(
        embedder.embed_query(query),
        query,
        k=k * _OVERFETCH,
        hybrid=hybrid,
    )
    hits: list[Hit] = []
    per_page: dict[str, int] = {}
    for row in rows:
        page_id = str(row.get("page_id") or "")
        if per_page.get(page_id, 0) >= MAX_CHUNKS_PER_PAGE:
            continue
        per_page[page_id] = per_page.get(page_id, 0) + 1
        hits.append(
            Hit(
                chunk_id=str(row.get("chunk_id") or ""),
                unit_id=str(row.get("unit_id") or ""),
                page_id=page_id,
                chunk_index=int(row.get("chunk_index") or 0),
                text=str(row.get("text") or ""),
                score=float(row.get("score") or 0.0),
                content_fingerprint=str(row.get("content_fingerprint") or ""),
                char_start=int(row.get("char_start") or 0),
                char_end=int(row.get("char_end") or 0),
            )
        )
        if len(hits) >= k:
            break
    return hits


def pack_hits(hits: list[Hit], *, max_chars: int) -> list[Hit]:
    selected: list[Hit] = []
    used = 0
    for hit in hits:
        cost = len(hit.text)
        if selected and used + cost > max_chars:
            break
        selected.append(hit)
        used += cost
    return selected


def format_hit_excerpts(hits: list[Hit]) -> str:
    parts: list[str] = []
    for i, hit in enumerate(hits, start=1):
        parts.append(
            f"[S{i} unit_id={hit.unit_id} page={hit.page_id}]\n{hit.text}"
        )
    return "\n\n".join(parts)
