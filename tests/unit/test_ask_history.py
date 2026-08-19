"""Tests for Ask notebook history."""

from __future__ import annotations

from pathlib import Path

from transcribe.analysis.ask_history import (
    entry_from_envelope,
    format_ask_timestamp,
    list_ask_history,
    summarize_ask_label,
)
from transcribe.analysis.envelope import build_envelope
from transcribe.analysis.modules.llm_custom_qa import LLMCustomQAModule
from transcribe.analysis.runner import _module_provenance
from transcribe.analysis.storage import AnalysisStorage
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import write_json_atomic


def _sample_envelope(
    *,
    attempt_id: str = "att-1",
    question: str = "What themes appear?",
    model: str = "llama3",
    answer: str = "Garden imagery.",
    recorded_at: str = "2026-08-19T12:30:00+00:00",
) -> dict:
    return build_envelope(
        project_id="nb-1",
        module_id="llm_custom_qa",
        module_version=LLMCustomQAModule.module_version,
        cache_identity="abc123",
        content_fingerprint="content-fp",
        attempt_state="succeeded",
        outcome="success",
        payload={
            "schema": "llm_custom_qa_payload_v1",
            "question": question,
            "answer": answer,
            "model": model,
            "honesty_label": "llm_generated",
        },
        provenance=_module_provenance(LLMCustomQAModule()),
        config_fingerprint="cfg-fp",
        attempt_id=attempt_id,
        llm={
            "question_text": question,
            "model_name": model,
            "prompt_or_template_version": "v1",
            "generation_settings": {},
            "grounding_strategy_id": "ground_doc_chunks_v1",
            "chunking_policy_id": "notebook_chunks_units_v1",
            "reduction_policy_id": "notebook_map_reduce_v1",
            "token_estimator_id": "whitespace_tokens_v1",
            "input_fingerprint": "in-fp",
        },
        recorded_at=recorded_at,
    )


def test_entry_from_envelope_extracts_metadata():
    env = _sample_envelope()
    entry = entry_from_envelope(env)
    assert entry is not None
    assert entry.question == "What themes appear?"
    assert entry.model == "llama3"
    assert entry.answer == "Garden imagery."
    assert entry.recorded_at == "2026-08-19T12:30:00+00:00"


def test_entry_from_envelope_skips_running():
    env = _sample_envelope()
    env["attempt_state"] = "running"
    assert entry_from_envelope(env) is None


def test_list_ask_history_newest_first(tmp_path: Path):
    paths = ProjectPaths(tmp_path / "proj")
    paths.analysis_dir.mkdir(parents=True)
    storage = AnalysisStorage(paths)
    older = _sample_envelope(
        attempt_id="att-old",
        question="Older question?",
        recorded_at="2026-08-18T10:00:00+00:00",
    )
    newer = _sample_envelope(
        attempt_id="att-new",
        question="Newer question?",
        recorded_at="2026-08-19T14:00:00+00:00",
    )
    write_json_atomic(storage.attempt_path("llm_custom_qa", "att-old"), older)
    write_json_atomic(storage.attempt_path("llm_custom_qa", "att-new"), newer)

    entries = list_ask_history(storage)
    assert [e.attempt_id for e in entries] == ["att-new", "att-old"]


def test_summarize_ask_label_truncates_long_questions():
    entry = entry_from_envelope(
        _sample_envelope(question="Q" * 100),
    )
    assert entry is not None
    label = summarize_ask_label(entry, max_question_chars=20)
    assert "…" in label
    assert "llama3" in label


def test_format_ask_timestamp():
    assert "Aug 2026" in format_ask_timestamp("2026-08-19T12:30:00+00:00")
