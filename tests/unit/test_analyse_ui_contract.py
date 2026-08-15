"""Lightweight Analyse UI contract checks (no Streamlit runtime).

Launcher is Workflow → Analyse. Product views live on View pages.
"""

from __future__ import annotations

from pathlib import Path

APP = Path("src/transcribe/ui/app.py").read_text(encoding="utf-8")
RUN = Path("src/transcribe/ui/run_analysis.py").read_text(encoding="utf-8")
HEALTH = Path("src/transcribe/ui/analysis_health_view.py").read_text(encoding="utf-8")
PRODUCT = Path("src/transcribe/ui/analysis_product_views.py").read_text(encoding="utf-8")
VIEWS = Path("src/transcribe/ui/notebook_views.py").read_text(encoding="utf-8")
WRAP = Path("src/transcribe/ui/notebook_view_page.py").read_text(encoding="utf-8")
JUMPS = Path("src/transcribe/ui/view_jumps.py").read_text(encoding="utf-8")


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
        assert forbidden not in VIEWS
    assert "module_freshness" in VIEWS
    assert "derive_analysis_health" in VIEWS
    assert "scope_analysis_health" in VIEWS
    assert "render_run_analysis_form" in APP
    assert "get_analysis_coordinator" in APP
    assert 'st.tabs([' not in RUN
    assert "Published results" not in RUN
    assert "_render_analysis_result_tabs" not in APP


def test_run_analysis_uses_coordinator_not_blocking_runner_loop():
    assert "AnalysisCoordinator" in RUN
    assert "build_analysis_run_plan" in RUN
    assert "coord.start" in RUN or "coord.start(" in RUN
    assert "plan_hash" in RUN
    assert "AnalysisRunPlan.from_dict" in RUN
    assert "runner.run_module" not in RUN
    assert "_execute_pending_launch" not in RUN
    assert "Include Ask notebook question" in RUN
    assert 'pending.get("plan")' in RUN


def test_run_analysis_freezes_plan_before_start():
    assert "verify_plan_hash" in RUN
    assert "PlanHashMismatchError" in RUN


def test_phase6_shared_status_strip_is_sole_default_health_chrome():
    assert "render_status_strip" in WRAP
    assert "render_status_strip" in HEALTH
    assert "render_aggregate_caption(" not in APP
    assert "render_aggregate_caption(" not in VIEWS
    assert "render_module_health_banner(" not in APP
    assert "render_module_health_banner(" not in VIEWS


def test_phase6_product_views_live_on_view_pages():
    assert "render_overview_product" in VIEWS
    assert "render_themes_product" in VIEWS
    assert "render_mood_product" in VIEWS
    assert "render_moments_product" in VIEWS
    assert "render_summaries_product" in VIEWS
    assert "render_ask_product" in VIEWS
    assert "analysis_product_views" in VIEWS
    assert "render_notebook_view_page" in VIEWS
    assert 'f"{mid} payload"' not in APP
    assert "moments payload" not in APP
    assert "Raw payload" not in APP
    assert "capability=`" not in APP
    assert "outcome=`" not in APP
    assert "Needs a text model" in HEALTH
    assert "product_capability_label" in HEALTH
    assert "render_advanced_payload" in PRODUCT
    assert 'f"Advanced · {label}"' in HEALTH or "Advanced ·" in HEALTH


def test_product_views_read_real_payload_shapes():
    """Overview/Summaries must use nested module payload keys, not mythical top-level ones."""
    assert "extract_foundations_display" in PRODUCT
    assert 'payload.get("quotes")' in PRODUCT
    assert 'payload.get("overview")' in PRODUCT
    assert 'payload.get("themes")' in PRODUCT
    assert 'payload.get("notable_quotes")' in PRODUCT
    assert '"type_token_ratio"' not in PRODUCT
    assert "render_module_compare_charts" in PRODUCT
    assert "projects_dir" in PRODUCT
    assert "emotion_label_totals" in PRODUCT or "render_entity_sentiment_section" in PRODUCT
    assert "group_action_items" in PRODUCT
    assert "topic_weight_rows" in PRODUCT
    assert "contextual_label_counts" in PRODUCT
    assert "render_entity_sentiment_section" in PRODUCT


def test_overview_renders_real_wordcloud_when_available():
    assert "render_wordcloud_section" in PRODUCT
    path = Path("src/transcribe/ui/wordcloud_render.py")
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "generate_from_frequencies" in text
    assert "to_image" in text
    assert "build_wordcloud_explorer_html" in text
    assert '"Basic"' in text and '"Advanced"' in text
    assert Path("src/transcribe/ui/assets/wordcloud2.js").is_file()
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    core = pyproject.split("[project.optional-dependencies]", 1)[0]
    assert "wordcloud>=" in core


def test_analyse_wires_corpus_compare_into_overview_and_mood():
    assert "projects_dir=runtime.projects_dir" in VIEWS
    assert "project_id=project.id" in VIEWS
    assert Path("src/transcribe/services/analysis_compare.py").is_file()
    assert Path("src/transcribe/ui/analysis_compare_view.py").is_file()
    assert "load_module_baseline" in Path("src/transcribe/services/analysis_compare.py").read_text(
        encoding="utf-8"
    )
    assert "render_module_compare_charts" in Path(
        "src/transcribe/ui/analysis_compare_view.py"
    ).read_text(encoding="utf-8")


def test_entity_sentiment_is_on_people_places_batch():
    assert "entity_sentiment" in VIEWS
    assert "entity_sentiment_health" in VIEWS
    places = Path("src/transcribe/ui/places_map.py").read_text(encoding="utf-8")
    assert "entity_sentiment_health" in places
    assert "render_entity_sentiment_section" in places
    assert "Entity tone" in places or "entity tone" in places.lower()
    helpers = Path("src/transcribe/ui/analysis_display_helpers.py").read_text(encoding="utf-8")
    assert "aggregate_entity_sentiment" in helpers


def test_moments_jump_opens_reading_via_page_viewer():
    """Jump to page must set Reading, not Review, via the shared helper."""
    assert "jump_to_reading" in VIEWS
    assert "open_page_context" in JUMPS
    assert 'st.session_state["ui_mode"] = "Reading"' in JUMPS
    assert 'st.session_state["ui_mode"] = "Review"' not in VIEWS
    assert 'st.session_state["ui_mode"] = "Review"' not in APP
    assert '["review_page_id"]' not in APP
    assert '["nav_section"]' not in APP
    assert "_page_id_for_moment" in PRODUCT


def test_page_series_charts_are_clickable_and_wired_to_jump():
    """Within-notebook page-order charts jump via Reading, not Review."""
    charts = Path("src/transcribe/ui/page_series_charts.py").read_text(encoding="utf-8")
    selection = Path("src/transcribe/ui/page_series_selection.py").read_text(encoding="utf-8")
    metrics = Path("src/transcribe/ui/page_metrics_view.py").read_text(encoding="utf-8")
    assert "render_clickable_page_series" in charts
    assert "on_select" in charts
    assert "PAGE_SELECT" in selection
    assert "selected_page_id" in selection
    assert "render_clickable_page_series" in PRODUCT
    assert "maybe_jump" in PRODUCT
    assert "on_jump" in PRODUCT
    assert "unit_series_rows" in PRODUCT
    assert "topic_shift_series_rows" in PRODUCT
    assert "epistemic_page_series_rows" in PRODUCT
    assert "_on_jump" in VIEWS
    assert VIEWS.count("return_mode=") >= 4
    assert 'return_mode="Overview"' in VIEWS
    assert 'return_mode="Themes"' in VIEWS
    assert 'return_mode="Mood"' in VIEWS
    assert 'return_mode="Moments"' in VIEWS
    assert "on_jump" in metrics
    assert "render_clickable_page_series" in metrics


def test_this_notebook_complete_navigates_to_overview():
    assert 'normalize_ui_mode("Overview")' in RUN
    assert 'progress.status == "completed"' in RUN


def test_phase6_ocr_advanced_groups_power_controls():
    tx = Path("src/transcribe/ui/run_transcribe.py").read_text(encoding="utf-8")
    assert "Vision model" in tx
    assert "Start transcription" in tx
    assert "Clean OCR with text model" in tx
    assert 'st.expander("Advanced"' in tx
    adv_idx = tx.index('st.expander("Advanced"')
    assert tx.index("Workers", adv_idx) > adv_idx
    assert tx.index("Force re-run", adv_idx) > adv_idx
    assert tx.index("Cleanup mode", adv_idx) > adv_idx
    remote_idx = tx.index("I understand and want to use this remote host")
    assert remote_idx < adv_idx


def test_ocr_model_information_expander_at_pickers():
    tx = Path("src/transcribe/ui/run_transcribe.py").read_text(encoding="utf-8")
    info = Path("src/transcribe/ui/components/model_info.py").read_text(encoding="utf-8")
    assert 'st.expander("Model information"' in info
    assert "render_model_information" in tx
    assert "warn_if_first_compare_model_is_general_vlm" in tx
    assert "Clean OCR during compare" in tx
    assert "render_model_information" in RUN


def test_compare_starts_in_background_not_spinner():
    tx = Path("src/transcribe/ui/run_transcribe.py").read_text(encoding="utf-8")
    assert 'st.spinner("Running multipass' not in tx
    assert "multi.start(" in tx
    assert "coord.start" in tx


def test_phase6_last_run_is_product_summary():
    assert "last_run_product_summary" in RUN
    assert "Advanced · per-module outcomes" in RUN
    assert "outcome=`" not in RUN


def test_analyse_batch_target_and_progress_wiring():
    from transcribe.persistence.schema import SUPPORTED
    from transcribe.ui.shell import is_open_notebook_workflow

    batch = Path("src/transcribe/ui/run_analysis_batch.py").read_text(encoding="utf-8")
    nav = Path("src/transcribe/ui/navigation.py").read_text(encoding="utf-8")
    targets = Path("src/transcribe/ui/targets.py").read_text(encoding="utf-8")
    panel = Path("src/transcribe/ui/components/progress_panel.py").read_text(
        encoding="utf-8"
    )
    assert "render_analyse_workspace" in APP
    assert "get_batch_analysis_coordinator" in APP
    assert "ANALYSE_TARGET_KEY" in APP
    assert "ANALYSE_TARGET_KEY" in targets
    assert "ANALYSE_BATCH_SOURCE_KEY" in targets
    assert not is_open_notebook_workflow("Analyse")
    assert is_open_notebook_workflow("Review")
    assert 'id="Analyse"' in nav
    assert "Notebooks needing analysis" in batch
    assert "From an import run" in batch
    assert "Pick notebooks" in batch
    assert "list_candidates_light" in batch
    assert "Refresh list" in batch
    assert "invalidate_batch_analyse_caches" in batch
    assert "@st.fragment" in batch
    assert 'st.session_state["ax_batch_source"] = "pick"' in batch
    assert "Select notebooks" in batch
    assert "_render_batch_notebook_source" in batch
    assert "_render_batch_preset_and_launch" in batch
    assert 'unit_label="notebooks"' in batch
    assert "modules in this notebook" in batch
    assert "Stop after current notebook" in batch
    assert "Start batch analysis" in batch
    assert "Text model for this batch" in batch
    assert "text_model_name=" in batch
    assert "configured on each notebook" not in batch
    assert "unavailable_model" not in batch
    assert "Retry failed" in batch
    assert "render_progress_panel" in batch
    assert "BatchAnalysisCoordinator" in batch
    assert "runner.run_module" not in batch
    assert SUPPORTED.get("transcribe.analysis-batch-run") == 1
    assert "Current {detail_noun}" in panel or "Current module" in panel
    assert "detail_unit" in panel
    assert 'set_ui_mode("Library")' in batch
    overview_assigns = [
        line
        for line in batch.splitlines()
        if "Overview" in line and "ui_mode" in line
    ]
    assert overview_assigns
    assert "notebook_has_published_analysis" in batch
    assert 'set_ui_mode("Overview")' not in batch
    assert 'set_ui_mode("Library")' in batch


def test_run_analysis_polls_via_fragment_not_sleep_rerun():
    assert "@st.fragment" in RUN
    assert "run_every" in RUN
    assert "time.sleep" not in RUN
    assert "analysis_status_panel" in RUN
    assert "config_fragment" in RUN
