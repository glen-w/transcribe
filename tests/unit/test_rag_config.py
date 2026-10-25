"""Workspace RAG config clamps and Ask mode fold-in."""

from __future__ import annotations

from dataclasses import replace

from transcribe.analysis.cache_identity import config_fingerprint
from transcribe.analysis.modules.llm_rag_qa import llm_rag_qa_config
from transcribe.analysis.presets import ask_execution_flags, compute_effective_modules, resolve_analysis_preset
from transcribe.config.facade import bind_operation_config
from transcribe.config.models import EffectiveConfig, RagConfig


def test_rag_defaults_off() -> None:
    rag = RagConfig()
    assert rag.enabled is False
    assert rag.ask_mode == "grounded"
    assert rag.embed_model == "nomic-embed-text"
    assert rag.hybrid is True
    assert rag.top_k == 10


def test_rag_from_dict_clamps() -> None:
    rag = RagConfig.from_dict(
        {
            "enabled": True,
            "chunk_chars": 10,
            "chunk_overlap": 9999,
            "top_k": 0,
            "max_context_chars": 5,
            "embed_batch_size": 0,
            "ask_mode": "nope",
            "embed_provider": "litellm",
            "embed_model": "  ",
        }
    )
    assert rag.enabled is True
    assert rag.chunk_chars == 200
    assert rag.chunk_overlap == 100
    assert rag.top_k == 1
    assert rag.max_context_chars == 1000
    assert rag.embed_batch_size == 1
    assert rag.ask_mode == "grounded"
    assert rag.embed_provider == "ollama"
    assert rag.embed_model == "nomic-embed-text"


def test_ask_execution_flags() -> None:
    assert ask_execution_flags("both", has_question=False, rag_enabled=True) == (False, False)
    assert ask_execution_flags("rag", has_question=True, rag_enabled=False) == (True, False)
    assert ask_execution_flags("rag", has_question=True, rag_enabled=True) == (False, True)
    assert ask_execution_flags("both", has_question=True, rag_enabled=True) == (True, True)
    assert ask_execution_flags("grounded", has_question=True, rag_enabled=True) == (True, False)


def test_rag_qa_fold_in() -> None:
    resolved = resolve_analysis_preset("quick")
    plan = compute_effective_modules(
        resolved, custom_qa_execution=False, rag_qa_execution=True
    )
    assert "llm_rag_qa" in plan.module_ids
    assert "llm_custom_qa" not in plan.module_ids
    both = compute_effective_modules(
        resolved, custom_qa_execution=True, rag_qa_execution=True
    )
    assert "llm_custom_qa" in both.module_ids
    assert "llm_rag_qa" in both.module_ids


def test_rag_cache_identity_changes_with_top_k_embed_and_question() -> None:
    def fingerprint(rag: RagConfig, question: str) -> str:
        cfg = replace(EffectiveConfig(), analysis=replace(EffectiveConfig().analysis, rag=rag))
        with bind_operation_config(cfg):
            return config_fingerprint(llm_rag_qa_config(question_text=question))

    base = RagConfig(enabled=True)
    a = fingerprint(base, "What needs water?")
    b = fingerprint(replace(base, top_k=3), "What needs water?")
    c = fingerprint(replace(base, embed_model="other-embed"), "What needs water?")
    d = fingerprint(base, "A different question")
    assert len({a, b, c, d}) == 4
