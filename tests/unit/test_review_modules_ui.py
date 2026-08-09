"""Contracts for Review modules grouping + remove-from-run flow."""

from __future__ import annotations

from pathlib import Path

from transcribe.ui.module_ui_groups import TECHNICAL_OTHER_TITLE, group_modules_for_ui
from transcribe.ui.run_analysis import (
    apply_pending_review_module_removal,
    apply_review_module_removal,
)


def test_group_modules_for_ui_uses_tx_families() -> None:
    groups = group_modules_for_ui(
        ["wordclouds", "stats", "sentiment", "moments", "llm_summary", "zzz_unknown"]
    )
    titles = [t for t, _ in groups]
    assert titles == [
        "Summary & Synthesis",
        "Foundations",
        "Language & Meaning",
        "Dynamics & Flow",
        "Visualisations",
        TECHNICAL_OTHER_TITLE,
    ]
    by_title = dict(groups)
    assert by_title["Foundations"] == ["stats"]
    assert by_title["Language & Meaning"] == ["sentiment"]
    assert by_title["Visualisations"] == ["wordclouds"]
    assert by_title[TECHNICAL_OTHER_TITLE] == ["zzz_unknown"]


def test_shell_defines_review_module_remove_hover_css() -> None:
    source = Path("src/transcribe/ui/shell.py").read_text(encoding="utf-8")
    assert "_review_rm_" in source
    assert "opacity: 0" in source


def test_run_analysis_review_uses_grouped_rows_and_remove_keys() -> None:
    source = Path("src/transcribe/ui/run_analysis.py").read_text(encoding="utf-8")
    assert "group_modules_for_ui" in source
    assert "_review_rm_" in source
    assert "apply_review_module_removal" in source


def test_review_module_removal_queues_custom_remainder() -> None:
    ss: dict = {"run_analysis_preset": "Balanced"}
    ok = apply_review_module_removal(
        ss,
        module_ids=["stats", "sentiment", "ner"],
        remove_id="sentiment",
    )
    assert ok is True
    assert ss["run_analysis_review_modules_keep_open"] is True
    assert "run_analysis_pending_review_removal" in ss
    assert ss["run_analysis_preset"] == "Balanced"

    apply_pending_review_module_removal(ss)
    assert ss["run_analysis_preset"] == "Custom"
    assert ss["run_analysis_custom_modules"] == ["stats", "ner"]
    assert "run_analysis_custom_modules_widget" not in ss
    assert "run_analysis_pending_review_removal" not in ss


def test_review_module_removal_clears_ask_notebook() -> None:
    ss: dict = {
        "run_analysis_qa_enable": True,
        "run_analysis_qa_text": "What themes?",
    }
    ok = apply_review_module_removal(
        ss,
        module_ids=["stats", "llm_custom_qa"],
        remove_id="llm_custom_qa",
    )
    assert ok is True
    apply_pending_review_module_removal(ss)
    assert ss["run_analysis_custom_modules"] == ["stats"]
    assert ss["run_analysis_qa_enable"] is False
    assert ss["run_analysis_qa_text"] == ""


def test_review_module_removal_refuses_empty_plan() -> None:
    ss: dict = {}
    assert (
        apply_review_module_removal(
            ss,
            module_ids=["stats"],
            remove_id="stats",
        )
        is False
    )
    assert "run_analysis_pending_review_removal" not in ss
