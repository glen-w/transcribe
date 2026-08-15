"""GUI alignment copy, chrome, widget keys, and launcher vs View contracts."""

from __future__ import annotations

from pathlib import Path

from transcribe.ui.action_menus.ids import SECTION_LABELS, SECTION_ORDER, ActionId, SectionId
from transcribe.ui.navigation import CONTEXT_BAR_HIDDEN_MODES, WIDE_LAYOUT_MODES

UI_ROOT = Path("src/transcribe/ui")

_FORBIDDEN_COPY = (
    "form above",
    "Published results below",
    "Analyse → Detect",
    "App → Settings",
)


def _ui_py_files() -> list[Path]:
    return sorted(p for p in UI_ROOT.rglob("*.py") if p.name != "navigation.py")


def test_product_ui_copy_has_no_stale_analyse_tabs_language() -> None:
    for path in _ui_py_files():
        text = path.read_text(encoding="utf-8")
        for phrase in _FORBIDDEN_COPY:
            assert phrase not in text, f"{path}: found {phrase!r}"


def test_view_pages_go_through_wrapper_with_analyse_cta() -> None:
    views = (UI_ROOT / "notebook_views.py").read_text(encoding="utf-8")
    wrap = (UI_ROOT / "notebook_view_page.py").read_text(encoding="utf-8")
    assert "render_notebook_view_page" in views
    assert "show_analyse_cta" in views
    assert "Analyse this notebook" in wrap
    assert 'set_ui_mode("Analyse")' in wrap


def test_widget_keys_include_project_id() -> None:
    product = (UI_ROOT / "analysis_product_views.py").read_text(encoding="utf-8")
    views = (UI_ROOT / "notebook_views.py").read_text(encoding="utf-8")
    metrics = (UI_ROOT / "page_metrics_view.py").read_text(encoding="utf-8")
    detect = (UI_ROOT / "run_detection.py").read_text(encoding="utf-8")
    assert "def _ns(project_id" in product
    assert '_ns(project_id, "overview")' in product
    assert '_ns(project_id, "overview_wc")' in product
    assert '_ns(project_id, "mood")' in product
    assert "ask_notebook_question_{project.id}" in views
    assert "page_metrics_refresh_{project.id}" in metrics
    assert "overview_ink_{project.id}" in metrics
    assert "detect_run_detectors_{project_id}" in detect
    assert "moment_jump_{project_id" in product


def test_overview_hub_deep_links() -> None:
    product = (UI_ROOT / "analysis_product_views.py").read_text(encoding="utf-8")
    assert 'Open Themes"' in product or "Open Themes" in product
    assert "Open Mood" in product
    assert "Open People" in product
    assert "visible_cards" in product


def test_context_bar_hidden_on_ingest_home_system() -> None:
    assert CONTEXT_BAR_HIDDEN_MODES == frozenset(
        {
            "Home",
            "New notebook",
            "Import",
            "Transcribe",
            "Analyse",
            "Settings",
            "Diagnostics",
        }
    )
    bar = (UI_ROOT / "components" / "context_bar.py").read_text(encoding="utf-8")
    assert "Notebook ·" in bar
    assert "hide_context_bar" in bar


def test_wide_layout_includes_places() -> None:
    assert "Places" in WIDE_LAYOUT_MODES
    layout = (UI_ROOT / "layout.py").read_text(encoding="utf-8")
    assert "use_wide_layout" in layout


def test_settings_interface_lists_additive_sections() -> None:
    iface = (UI_ROOT / "settings_interface.py").read_text(encoding="utf-8")
    hub = (UI_ROOT / "settings_hub.py").read_text(encoding="utf-8")
    assert "SECTION_ORDER" in iface
    assert "SECTION_LABELS" in iface
    assert SectionId.IMPORT_SUCCESS in SECTION_ORDER
    assert SectionId.TRANSCRIBE_COMPLETE in SECTION_ORDER
    assert SectionId.ANALYSE_COMPLETE in SECTION_ORDER
    assert ActionId.OVERVIEW.value == "overview"
    assert ActionId.REVIEW.value == "review"
    assert SECTION_LABELS[SectionId.VIEW_NOTEBOOK] == "Library — notebook row"
    assert "overview_cards" in hub
    assert "Save overview cards" in hub


def test_settings_hub_tab_labels_and_order() -> None:
    from transcribe.ui.settings_interface import SETTINGS_TABS

    assert SETTINGS_TABS == (
        "Configuration",
        "Analysis",
        "Detection",
        "Prompts",
        "Interface",
        "Models",
        "Profiles",
        "Export",
    )
    iface = (UI_ROOT / "settings_interface.py").read_text(encoding="utf-8")
    assert "st.tabs(list(SETTINGS_TABS))" in iface
    hub = (UI_ROOT / "settings_hub.py").read_text(encoding="utf-8")
    assert "ollama_health_line" in hub
    assert "settings_ocr_preprocess_profile" in hub
    assert "Select a notebook to apply." in hub
    assert "model_info" not in hub
    assert "render_model_information" not in hub


def test_select_heavy_settings_panels_use_fragments() -> None:
    """Knob/select Settings surfaces isolate reruns via @st.fragment."""
    iface = (UI_ROOT / "settings_interface.py").read_text(encoding="utf-8")
    hub = (UI_ROOT / "settings_hub.py").read_text(encoding="utf-8")
    analysis = (UI_ROOT / "settings_analysis.py").read_text(encoding="utf-8")
    detection = (UI_ROOT / "settings_detection.py").read_text(encoding="utf-8")
    prompts = (UI_ROOT / "settings_prompts.py").read_text(encoding="utf-8")
    assert "@st.fragment" in iface
    assert hub.count("@st.fragment") >= 3
    assert "@st.fragment" in analysis
    assert "@st.fragment" in detection
    assert "@st.fragment" in prompts


def test_detect_viewer_returns_to_detect() -> None:
    detect = (UI_ROOT / "run_detection.py").read_text(encoding="utf-8")
    views = (UI_ROOT / "notebook_views.py").read_text(encoding="utf-8")
    assert 'return_mode="Detect"' in detect
    assert 'st.session_state["ui_mode"] = "Detect"' in detect
    assert "Back to Detect" in views


def test_search_and_library_open_reading() -> None:
    archive = (UI_ROOT / "archive_views.py").read_text(encoding="utf-8")
    nav = (UI_ROOT / "action_menus" / "nav.py").read_text(encoding="utf-8")
    assert 'st.session_state["ui_mode"] = "Reading"' in archive
    assert 'return_mode="Search"' in archive
    assert 'state["ui_mode"] = "Reading"' in nav
    assert "listing_return_mode" in nav


def test_this_notebook_analyse_goes_overview_batch_stays() -> None:
    run = (UI_ROOT / "run_analysis.py").read_text(encoding="utf-8")
    batch = (UI_ROOT / "run_analysis_batch.py").read_text(encoding="utf-8")
    # Suite complete: Overview when modules ran; Detect when detector-only.
    assert 'dest = "Overview" if has_modules else "Detect"' in run
    assert "normalize_ui_mode(dest)" in run
    assert "ANALYSE_COMPLETE" in run
    assert 'set_ui_mode("Library")' in batch
    assert 'set_ui_mode("Overview")' not in batch
    assert "IMPORT_SUCCESS" in (UI_ROOT / "run_import.py").read_text(encoding="utf-8")
    assert "TRANSCRIBE_COMPLETE" in (UI_ROOT / "run_transcribe.py").read_text(encoding="utf-8")


def test_empty_state_taxonomy() -> None:
    empty = (UI_ROOT / "components" / "empty_state.py").read_text(encoding="utf-8")
    for kind in (
        "missing_prerequisite",
        "no_results_yet",
        "filtered_to_zero",
        "error_degraded",
    ):
        assert kind in empty
    assert "[:2]" in empty


def test_overview_does_not_gate_on_published_analysis() -> None:
    views = (UI_ROOT / "notebook_views.py").read_text(encoding="utf-8")
    start = views.index("def render_view_overview")
    end = views.index("def render_view_themes")
    overview = views[start:end]
    assert "notebook_has_published_analysis" not in overview
    assert "show_analyse_cta" not in overview
    assert "empty_kind" not in overview
    assert "render_overview_page_metrics" in overview
    assert "body=_body" in overview


def test_published_view_pages_use_analyse_cta_when_unpublished() -> None:
    views = (UI_ROOT / "notebook_views.py").read_text(encoding="utf-8")
    wrap = (UI_ROOT / "notebook_view_page.py").read_text(encoding="utf-8")
    for name in (
        "render_view_themes",
        "render_view_mood",
        "render_view_summaries",
    ):
        assert f"def {name}" in views
    assert "def render_view_moments" not in views
    assert "def render_view_people" not in views
    assert "def render_view_ask" not in views
    assert views.count("show_analyse_cta=not published") == 2
    assert "render_analyse_cta" in views
    assert "select_view_panel" in views
    assert "st.segmented_control" in wrap
    assert "render_moments_product" in views
    assert "render_notebook_places_tab" in views
    assert "render_ask_product" in views
    assert 'empty_kind=None if published else "no_results_yet"' in views


def test_detect_empty_uses_detection_storage_not_published() -> None:
    views = (UI_ROOT / "notebook_views.py").read_text(encoding="utf-8")
    start = views.index("def render_view_detect")
    detect = views[start:]
    assert "notebook_has_detection_results" in detect
    assert "notebook_has_published_analysis" not in detect
    assert "No detection findings yet" in detect


def test_docs_have_no_stale_ia_copy() -> None:
    roots = [Path("docs"), Path("README.md")]
    forbidden = (
        "Published results",
        "form above",
        "Analyse → Detect",
        "App → Settings",
    )
    skip_names = {"INTEGRATION_SEAM.md"}
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        else:
            files.extend(p for p in root.rglob("*.md") if p.name not in skip_names)
    for path in files:
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, f"{path}: found {phrase!r}"
        for i, line in enumerate(text.splitlines(), 1):
            if "Jump to page" in line and "Review" in line:
                assert "Reading" in line or "not Review" in line, (
                    f"{path}:{i} still sends Jump to page to Review"
                )
    surfaces = Path("docs/public_surfaces.md").read_text(encoding="utf-8")
    assert "Reading · Overview · Themes · Mood · Summaries · Detect" in surfaces
    assert "Themes · Mood · Moments · People · Summaries · Ask · Detect" not in surfaces
