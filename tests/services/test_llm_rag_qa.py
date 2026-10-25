"""llm_rag_qa grounding with in-memory index (no LanceDB)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from transcribe.analysis.adapter import build_page_v1_document
from transcribe.analysis.llm_runtime import (
    RecordedDoubleClient,
    bind_text_llm_context,
    set_text_llm_client,
)
from transcribe.analysis.modules.llm_rag_qa import LLMRagQAModule
from transcribe.analysis.rag.embed import MemoryEmbedder
from transcribe.analysis.rag.ingest import RagRunContext, ensure_index
from transcribe.analysis.rag.memory import MemoryIndex
from transcribe.config.facade import bind_operation_config
from transcribe.config.models import EffectiveConfig, RagConfig
from tests.services.test_analysis_wave1e import TEXTS, _project_with_pages


def _cfg() -> EffectiveConfig:
    base = EffectiveConfig()
    return replace(base, analysis=replace(base.analysis, rag=RagConfig(enabled=True)))


def test_llm_rag_qa_unavailable_extra_without_index(tmp_path: Path) -> None:
    projects, _ = _project_with_pages(tmp_path, TEXTS)
    doc = build_page_v1_document(projects.load(), projects)
    with bind_operation_config(_cfg()):
        result = LLMRagQAModule().run(doc, question_text="What needs water?")
    assert result.get("capability_reason") in {"unavailable_dependency", "unavailable_extra"}


def test_llm_rag_qa_grounding_with_memory_index(tmp_path: Path) -> None:
    projects, _ = _project_with_pages(tmp_path, TEXTS)
    doc = build_page_v1_document(projects.load(), projects)
    unit_id = doc.units[0].unit_id
    embedder = MemoryEmbedder()
    index = MemoryIndex(dim=8)
    rag = RagConfig(enabled=True, hybrid=False)
    ctx = RagRunContext(
        rag_root=tmp_path / "rag",
        embedder=embedder,
        index=index,
    )
    cfg = replace(EffectiveConfig(), analysis=replace(EffectiveConfig().analysis, rag=rag))
    set_text_llm_client(
        RecordedDoubleClient(
            responses={
                "default": (
                    f'{{"answer":"They need water.","unit_ids":["{unit_id}"],"abstain":false}}'
                )
            }
        )
    )
    try:
        with bind_operation_config(cfg):
            ensure_index(doc, rag, ctx)
            llm_ctx = bind_text_llm_context(text_model_name="recorded-double:v1")
            result = LLMRagQAModule().run(
                doc,
                llm_ctx=llm_ctx,
                question_text="What do gardens need?",
                rag_ctx=ctx,
            )
        assert result["outcome"] == "success"
        assert result["payload"]["unit_ids"] == [unit_id]
        assert result["payload"]["retrieved"]
        assert result.get("evidence")
    finally:
        set_text_llm_client(None)


def test_llm_rag_qa_no_hits_does_not_call_llm(tmp_path: Path, monkeypatch) -> None:
    projects, _ = _project_with_pages(tmp_path, TEXTS)
    doc = build_page_v1_document(projects.load(), projects)
    rag = RagConfig(enabled=True, hybrid=False)
    ctx = RagRunContext(
        rag_root=tmp_path / "rag",
        embedder=MemoryEmbedder(),
        index=MemoryIndex(dim=8),
    )
    cfg = replace(EffectiveConfig(), analysis=replace(EffectiveConfig().analysis, rag=rag))
    called = {"n": 0}

    def _boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("LLM must not run when retrieval is empty")

    monkeypatch.setattr("transcribe.analysis.modules.llm_rag_qa.search_hits", lambda *a, **k: [])
    monkeypatch.setattr("transcribe.analysis.modules.llm_rag_qa.pack_hits", lambda *a, **k: [])
    set_text_llm_client(RecordedDoubleClient(responses={"default": '{"answer":"x","unit_ids":[],"abstain":false}'}))
    try:
        with bind_operation_config(cfg):
            llm_ctx = bind_text_llm_context(text_model_name="recorded-double:v1")
            monkeypatch.setattr(llm_ctx.client, "generate", _boom)
            result = LLMRagQAModule().run(
                doc,
                llm_ctx=llm_ctx,
                question_text="zzzz unmatched query",
                rag_ctx=ctx,
            )
        assert result["outcome"] == "insufficient_data"
        assert any(w["code"] == "rag_no_hits" for w in result["warnings"])
        assert called["n"] == 0
    finally:
        set_text_llm_client(None)


def test_llm_rag_qa_disabled() -> None:
    from transcribe.analysis.document import AnalysisDocument, AnalysisUnit

    doc = AnalysisDocument(
        document_id="n",
        text="hello gardens",
        units=[
            AnalysisUnit(
                unit_id="p1",
                text="hello gardens",
                order=1.0,
                source_ref={"kind": "page", "page_id": "p1"},
            )
        ],
    )
    with bind_operation_config(EffectiveConfig()):
        result = LLMRagQAModule().run(doc, question_text="hi")
    assert result["outcome"] == "skipped_not_applicable"
    assert any(w["code"] == "rag_disabled" for w in result["warnings"])
