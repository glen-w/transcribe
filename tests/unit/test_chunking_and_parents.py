"""Offline unit tests for chunking reduction and parent snapshot helpers."""

from __future__ import annotations

from transcribe.analysis.chunking import (
    cite_ids_from_chunks,
    estimate_tokens,
    pack_units_v1,
    select_chunks_for_prompt,
)
from transcribe.analysis.document import (
    GRANULARITY_PAGE_V1,
    SPLIT_PAGE,
    AnalysisDocument,
    AnalysisUnit,
)
from transcribe.analysis.modules._llm_common import prepared_excerpts
from transcribe.analysis.parents import parent_payloads, parents_for_identity


def _doc_with_texts(texts: list[str]) -> AnalysisDocument:
    units = [
        AnalysisUnit(
            unit_id=f"u{i}",
            order=i,
            text=text,
            source_ref={"kind": "page", "page_id": f"p{i}"},
            date=None,
        )
        for i, text in enumerate(texts)
    ]
    return AnalysisDocument(
        document_id="d1",
        text="\n".join(texts),
        units=units,
        granularity_version=GRANULARITY_PAGE_V1,
        split_profile=SPLIT_PAGE,
    )


def test_estimate_tokens_whitespace_v1():
    assert estimate_tokens("") == 0
    assert estimate_tokens("one two three") == 3


def test_select_chunks_for_prompt_leaves_remainder():
    chunks = [
        {"chunk_index": 0, "text": "a b c", "token_estimate": 3, "unit_ids": ["u0"], "cite_ids": ["u0"]},
        {"chunk_index": 1, "text": "d e f", "token_estimate": 3, "unit_ids": ["u1"], "cite_ids": ["u1"]},
        {"chunk_index": 2, "text": "g h i", "token_estimate": 3, "unit_ids": ["u2"], "cite_ids": ["u2"]},
    ]
    selected, remainder = select_chunks_for_prompt(chunks, total_token_budget=5)
    # First chunk always admitted; second would exceed remaining budget.
    assert [c["chunk_index"] for c in selected] == [0]
    assert [c["chunk_index"] for c in remainder] == [1, 2]


def test_prepared_excerpts_marks_map_reduce_and_fingerprint():
    # Units large enough that each packs alone under DEFAULT_MAX_TOKENS.
    big = " ".join(f"tok{i}" for i in range(1600))
    doc = _doc_with_texts([big, big, big])
    meta = prepared_excerpts(doc, total_token_budget=2000)
    assert len(meta["all_chunks"]) >= 2
    assert meta["needs_map_reduce"] is True
    assert meta["remainder"]
    assert meta["input_fingerprint"]
    assert cite_ids_from_chunks(meta["all_chunks"])


def test_pack_units_never_truncates_oversized_unit():
    words = " ".join(f"w{i}" for i in range(40))
    doc = _doc_with_texts([words])
    chunks = pack_units_v1(doc, max_tokens=8)
    assert len(chunks) >= 2
    joined = " ".join(c["text"] for c in chunks)
    for token in words.split()[:15]:
        assert token in joined
    assert any("#s" in cid for c in chunks for cid in (c.get("cite_ids") or []))


def test_parents_for_identity_strips_payload():
    rows = [
        {
            "module_id": "summary",
            "cache_identity": "abc",
            "outcome": "success",
            "payload": {"overview": "secret"},
        }
    ]
    ident = parents_for_identity(rows)
    assert ident == [
        {"module_id": "summary", "cache_identity": "abc", "outcome": "success"}
    ]
    assert "payload" not in ident[0]
    payloads = parent_payloads(rows)
    assert payloads["summary"]["overview"] == "secret"
