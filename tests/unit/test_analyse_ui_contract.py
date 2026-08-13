"""Lightweight Analyse UI contract checks (no Streamlit runtime).

Phase 1–2: one launcher, coordinator, plan-hash.
Phase 6: product views, shared status strip, OCR Advanced.
"""

from __future__ import annotations

from pathlib import Path

APP = Path("src/transcribe/ui/app.py").read_text(encoding="utf-8")
RUN = Path("src/transcribe/ui/run_analysis.py").read_text(encoding="utf-8")
HEALTH = Path("src/transcribe/ui/analysis_health_view.py").read_text(encoding="utf-8")
PRODUCT = Path("src/transcribe/ui/analysis_product_views.py").read_text(encoding="utf-8")


def test_analyse_ui_has_no_per_tab_batch_runners():
    for forbidden in (
        "Run Overview analysis",
        "Run Themes analysis",
        "Run Mood & tone analysis",
        "Run Moments analysis",
        "Run synthesis & LLM suite",
        "build_cache_identity_object",
    ):
        assert forbidden not in APP
    assert "module_freshness" in APP
    assert "derive_analysis_health" in APP
    assert "scope_analysis_health" in APP
    assert "render_run_analysis_form" in APP
    assert "get_analysis_coordinator" in APP


def test_run_analysis_uses_coordinator_not_blocking_runner_loop():
    assert "AnalysisCoordinator" in RUN
    assert "build_analysis_run_plan" in RUN
    assert "coord.start" in RUN or "coord.start(" in RUN
    assert "plan_hash" in RUN
    assert "AnalysisRunPlan.from_dict" in RUN
    assert "runner.run_module" not in RUN
    assert "_execute_pending_launch" not in RUN
    assert "Include Ask notebook question" in RUN
    assert "pending.get(\"plan\")" in RUN or 'pending.get("plan")' in RUN


def test_run_analysis_freezes_plan_before_start():
    assert "verify_plan_hash" in RUN
    assert "PlanHashMismatchError" in RUN


def test_phase6_shared_status_strip_is_sole_default_health_chrome():
    assert "render_status_strip" in APP
    assert "render_status_strip" in HEALTH
    # Per-tab aggregate captions must not remain the default path.
    assert "render_aggregate_caption(" not in APP
    # Module capability banners are not the default Analyse chrome.
    assert "render_module_health_banner(" not in APP


def test_phase6_product_views_demote_json_and_enums():
    assert "render_overview_product" in APP
    assert "render_themes_product" in APP
    assert "render_mood_product" in APP
    assert "render_moments_product" in APP
    assert "render_summaries_product" in APP
    assert "render_ask_product" in APP
    assert "analysis_product_views" in APP
    # Default path uses Advanced expanders, not bare payload dumps as section titles.
    assert 'f"{mid} payload"' not in APP
    assert "moments payload" not in APP
    assert "Raw payload" not in APP
    assert "capability=`" not in APP
    assert "outcome=`" not in APP
    # Product language helpers exist.
    assert "Needs a text model" in HEALTH
    assert "product_capability_label" in HEALTH
    assert "render_advanced_payload" in PRODUCT
    assert 'f"Advanced · {label}"' in HEALTH or "Advanced ·" in HEALTH


def test_phase6_ocr_advanced_groups_power_controls():
    tx = Path("src/transcribe/ui/run_transcribe.py").read_text(encoding="utf-8")
    # Primary controls remain outside Advanced.
    assert "Vision model" in tx
    assert "Start transcription" in tx
    assert "Clean OCR with text model" in tx
    # Power controls live under Advanced expander.
    assert 'st.expander("Advanced"' in tx
    # Workers / force / cleanup detail appear only after Advanced marker in source.
    adv_idx = tx.index('st.expander("Advanced"')
    assert tx.index("Workers", adv_idx) > adv_idx
    assert tx.index("Force re-run", adv_idx) > adv_idx
    assert tx.index("Cleanup mode", adv_idx) > adv_idx
    # Privacy acknowledgement stays on the primary path (before Advanced).
    remote_idx = tx.index("I understand and want to use this remote host")
    assert remote_idx < adv_idx


def test_phase6_last_run_is_product_summary():
    assert "last_run_product_summary" in RUN
    assert "Advanced · per-module outcomes" in RUN
    assert "outcome=`" not in RUN
