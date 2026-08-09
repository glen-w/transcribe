"""Lightweight Analyse UI contract checks (no Streamlit runtime)."""

from __future__ import annotations

from pathlib import Path


def test_analyse_ui_has_no_per_tab_batch_runners():
    text = Path("src/transcribe/ui/app.py").read_text(encoding="utf-8")
    for forbidden in (
        "Run Overview analysis",
        "Run Themes analysis",
        "Run Mood & tone analysis",
        "Run Moments analysis",
        "Run synthesis & LLM suite",
        "build_cache_identity_object",
    ):
        assert forbidden not in text
    assert "module_freshness" in text
    assert "render_run_analysis_form" in text
