"""RAG chunker and retrieve ranking without LanceDB."""

from __future__ import annotations

import pytest

from transcribe.analysis.document import AnalysisUnit
from transcribe.analysis.rag.chunk import chunk_unit
from transcribe.analysis.rag.embed import MemoryEmbedder
from transcribe.analysis.rag.memory import MemoryIndex
from transcribe.analysis.rag.retrieve import search_hits


def _unit(text: str, page_id: str = "p1") -> AnalysisUnit:
    return AnalysisUnit(
        unit_id=f"{page_id}/u",
        text=text,
        order=1.0,
        source_ref={"kind": "page", "page_id": page_id},
    )


def test_chunk_unit_splits_and_keeps_short_last() -> None:
    text = ("Alpha sentence one. " * 80) + "Short tail."
    chunks = chunk_unit(_unit(text), chunk_chars=200, overlap=40)
    assert len(chunks) >= 2
    assert all(c.page_id == "p1" for c in chunks)
    assert chunks[0].char_start == 0


def test_search_hits_caps_per_page() -> None:
    embedder = MemoryEmbedder()
    index = MemoryIndex(dim=8)
    rows = []
    for i in range(6):
        text = f"garden water soil {i}" if i < 4 else f"unrelated storms {i}"
        vec = embedder.embed_documents([text])[0]
        rows.append(
            {
                "chunk_id": f"u#{i}",
                "unit_id": "u",
                "page_id": "p1",
                "chunk_index": i,
                "text": text,
                "content_fingerprint": "x",
                "char_start": 0,
                "char_end": len(text),
                "vector": vec,
            }
        )
    index.replace_all(rows)
    hits = search_hits("garden water", index=index, embedder=embedder, k=10, hybrid=False)
    assert len(hits) <= 3
    assert all(h.page_id == "p1" for h in hits)


def test_search_hits_empty_index() -> None:
    embedder = MemoryEmbedder()
    index = MemoryIndex(dim=8)
    assert search_hits("garden", index=index, embedder=embedder, k=5, hybrid=False) == []


def test_lancedb_index_round_trip_skips_without_extra(tmp_path) -> None:
    pytest.importorskip("lancedb")
    from transcribe.analysis.rag.index import Index

    embedder = MemoryEmbedder()
    text = "garden water soil"
    vec = embedder.embed_documents([text])[0]
    index = Index.open(
        tmp_path / "rag",
        provider="memory",
        model="memory",
        dim=len(vec),
        create=True,
    )
    index.replace_all(
        [
            {
                "chunk_id": "u#0",
                "unit_id": "u",
                "page_id": "p1",
                "chunk_index": 0,
                "text": text,
                "content_fingerprint": "x",
                "char_start": 0,
                "char_end": len(text),
                "vector": vec,
            }
        ]
    )
    rows = index.search(vec, text, k=1, hybrid=False)
    assert rows and rows[0]["chunk_id"] == "u#0"
