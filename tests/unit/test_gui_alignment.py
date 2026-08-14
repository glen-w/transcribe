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
    assert "set_ui_mode(\"Analyse\")" in wrap


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
    assert 'normalize_ui_mode("Overview")' in run
    assert "ANALYSE_COMPLETE" in run
    assert 'set_ui_mode("Library")' in batch
    assert 'set_ui_mode("Overview")' not in batch
    assert "IMPORT_SUCCESS" in (UI_ROOT / "run_import.py").read_text(encoding="utf-8")
    assert "TRANSCRIBE_COMPLETE" in (UI_ROOT / "run_transcribe.py").read_text(
        encoding="utf-8"
    )


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
