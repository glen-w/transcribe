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
    assert "derive_analysis_health" in text
    assert "scope_analysis_health" in text
    assert "render_module_health_banner" in text
    assert "render_run_analysis_form" in text
    assert "get_analysis_coordinator" in text


def test_run_analysis_uses_coordinator_not_blocking_runner_loop():
    text = Path("src/transcribe/ui/run_analysis.py").read_text(encoding="utf-8")
    assert "AnalysisCoordinator" in text
    assert "build_analysis_run_plan" in text
    assert "coord.start" in text or "coord.start(" in text
    assert "plan_hash" in text
    assert "AnalysisRunPlan.from_dict" in text
    # Blocking per-module UI loop must not remain the launch authority.
    assert "runner.run_module" not in text
    assert "_execute_pending_launch" not in text
    # Ask notebook stays outside this durable batch path (ad-hoc in app tabs).
    assert "Include Ask notebook question" in text
    # Freeze happens at launch click; start must not rebuild the plan.
    assert "pending.get(\"plan\")" in text or 'pending.get("plan")' in text


def test_run_analysis_freezes_plan_before_start():
    text = Path("src/transcribe/ui/run_analysis.py").read_text(encoding="utf-8")
    assert "verify_plan_hash" in text
    assert "PlanHashMismatchError" in text
