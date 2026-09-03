"""PageSpec table, aliases, stay-don’t-bounce gating, published.json helper."""

from __future__ import annotations

from pathlib import Path

from transcribe.ui.navigation import (
    CONTEXT_BAR_HIDDEN_MODES,
    NAV_HELP_ANALYSE_FIRST,
    NAV_HELP_SELECT_NOTEBOOK,
    PAGE_SPECS,
    PAGE_SPECS_BY_ID,
    PRIMARY_MODES,
    SYSTEM_MODES,
    VIEW_MODES,
    VIEW_PAGE_PANELS,
    VIEW_PANEL_PENDING_KEY,
    WIDE_LAYOUT_MODES,
    WORKFLOW_MODES,
    apply_destination_to_session,
    destination_for_mode,
    hide_context_bar,
    is_open_notebook_workflow,
    is_view_mode,
    is_workflow_mode,
    nav_disabled_help,
    nav_enabled,
    notebook_has_detection_results,
    notebook_has_published_analysis,
    normalize_ui_mode,
    page_spec_for,
    use_wide_layout,
    view_panel_for,
)


def test_page_spec_table_and_sections() -> None:
    assert PRIMARY_MODES == ("Home", "Library", "Search")
    assert WORKFLOW_MODES == (
        "New notebook",
        "Import",
        "Transcribe",
        "Review",
        "Analyse",
        "Detect",
        "Export",
    )
    assert VIEW_MODES == (
        "Reading",
        "Overview",
        "Summaries",
        "Ask",
        "Themes",
        "Mood",
        "Places",
    )
    assert SYSTEM_MODES == ("Settings", "Diagnostics")
    assert len(PAGE_SPECS) == len(PAGE_SPECS_BY_ID)
    assert tuple(s.id for s in PAGE_SPECS) == PRIMARY_MODES + WORKFLOW_MODES + VIEW_MODES + SYSTEM_MODES


def test_analyse_is_workflow_none_overview_is_view_notebook() -> None:
    analyse = page_spec_for("Analyse")
    overview = page_spec_for("Overview")
    themes = page_spec_for("Themes")
    assert analyse is not None
    assert analyse.section == "workflow"
    assert analyse.required_context == "none"
    assert analyse.allowed_fallback == "stay"
    assert overview is not None
    assert overview.section == "view"
    assert overview.required_context == "notebook"
    assert overview.allowed_fallback == "stay"
    assert themes is not None
    assert themes.required_context == "notebook_published"
    assert themes.allowed_fallback == "stay"
    assert not any(hasattr(s, "run_id") for s in PAGE_SPECS)


def test_nav_labels_short_titles_long() -> None:
    assert page_spec_for("Reading").nav_label == "Read"
    assert page_spec_for("Mood").nav_label == "Mood"
    assert page_spec_for("Mood").title == "Mood & tone"
    assert page_spec_for("Themes").nav_label == "Themes"
    assert page_spec_for("Summaries").nav_label == "Summaries"
    assert page_spec_for("Summaries").required_context == "notebook"
    assert page_spec_for("Ask").nav_label == "Ask"
    assert page_spec_for("Ask").title == "Ask notebook"
    assert page_spec_for("Ask").required_context == "notebook"
    places = page_spec_for("Places")
    assert places is not None
    assert places.section == "view"
    assert places.nav_label == "People & Places"
    assert places.title == "People & Places"
    assert places.required_context == "none"
    people = view_panel_for("Places", "people")
    notebook_places = view_panel_for("Places", "places")
    moments = view_panel_for("Mood", "moments")
    assert people is not None
    assert people.label == "People"
    assert people.title == "People"
    assert notebook_places is not None
    assert notebook_places.label == "Places"
    assert notebook_places.title == "Places"
    assert {p.id for p in VIEW_PAGE_PANELS["Places"]} == {"people", "places"}
    assert moments is not None
    assert moments.label == "Moments"


def test_view_panel_aliases_open_parent_section() -> None:
    assert normalize_ui_mode("Moments") == "Mood"
    assert normalize_ui_mode("People") == "Places"
    assert normalize_ui_mode("Ask") == "Ask"
    assert page_spec_for("People") is page_spec_for("Places")
    assert destination_for_mode("Moments") == ("Mood", "moments")
    assert destination_for_mode("People") == ("Places", "people")
    assert destination_for_mode("NotebookPlaces") == ("Places", "places")
    assert destination_for_mode("Ask") == ("Ask", None)
    assert destination_for_mode("Themes") == ("Themes", None)
    assert set(VIEW_PAGE_PANELS) == {"Mood", "Places"}
    session: dict = {}
    assert apply_destination_to_session(session, "People") == "Places"
    assert session["ui_mode"] == "Places"
    assert session[VIEW_PANEL_PENDING_KEY] == "people"
    apply_destination_to_session(session, "Mood")
    assert session["ui_mode"] == "Mood"
    assert session[VIEW_PANEL_PENDING_KEY] == "people"


def test_legacy_aliases() -> None:
    assert normalize_ui_mode("View") == "Library"
    assert normalize_ui_mode("Notebooks") == "Library"
    assert normalize_ui_mode("Archive") == "Library"
    assert normalize_ui_mode("Published results") == "Overview"
    assert normalize_ui_mode("Run Analysis") == "Analyse"
    assert normalize_ui_mode("App") == "Settings"
    assert normalize_ui_mode("Inbox") == "Import"
    assert normalize_ui_mode("Create") == "New notebook"
    assert normalize_ui_mode("Analyze") == "Analyse"


def test_unknown_and_none_normalise_to_library() -> None:
    assert normalize_ui_mode(None) == "Library"
    assert normalize_ui_mode("bogus") == "Library"
    assert normalize_ui_mode("") == "Library"


def test_reading_is_view_not_workflow() -> None:
    assert normalize_ui_mode("Reading") == "Reading"
    assert is_view_mode("Reading")
    assert not is_workflow_mode("Reading")
    assert not is_open_notebook_workflow("Reading")
    assert is_open_notebook_workflow("Review")
    assert is_open_notebook_workflow("Detect")
    assert is_open_notebook_workflow("Export")
    assert not is_open_notebook_workflow("Analyse")


def test_nav_enabled_and_disabled_help() -> None:
    overview = page_spec_for("Overview")
    themes = page_spec_for("Themes")
    home = page_spec_for("Home")
    assert nav_enabled(home, has_notebook=False, has_published=False)
    assert not nav_enabled(overview, has_notebook=False, has_published=False)
    assert nav_enabled(overview, has_notebook=True, has_published=False)
    assert not nav_enabled(themes, has_notebook=True, has_published=False)
    assert nav_enabled(themes, has_notebook=True, has_published=True)
    summaries = page_spec_for("Summaries")
    ask = page_spec_for("Ask")
    assert nav_enabled(summaries, has_notebook=True, has_published=False)
    assert not nav_enabled(summaries, has_notebook=False, has_published=False)
    assert nav_enabled(ask, has_notebook=True, has_published=False)
    assert not nav_enabled(ask, has_notebook=False, has_published=False)
    assert nav_disabled_help(themes, has_notebook=False) == NAV_HELP_SELECT_NOTEBOOK
    assert nav_disabled_help(themes, has_notebook=True) == NAV_HELP_ANALYSE_FIRST
    assert nav_disabled_help(overview, has_notebook=False) == NAV_HELP_SELECT_NOTEBOOK


def test_context_bar_and_wide_layout() -> None:
    for mode in (
        "Home",
        "New notebook",
        "Import",
        "Transcribe",
        "Analyse",
        "Settings",
        "Diagnostics",
    ):
        assert hide_context_bar(mode)
        assert mode in CONTEXT_BAR_HIDDEN_MODES
    assert not hide_context_bar("Library")
    assert not hide_context_bar("Overview")
    assert not hide_context_bar("Reading")
    assert use_wide_layout("Places")
    assert use_wide_layout("Home")
    assert use_wide_layout("Reading")
    assert use_wide_layout("Review")
    assert use_wide_layout("Library")
    assert use_wide_layout("Archive")
    assert not use_wide_layout("Themes")
    assert use_wide_layout("People")
    assert not use_wide_layout("Overview")
    assert "Places" in WIDE_LAYOUT_MODES
    assert "Library" in WIDE_LAYOUT_MODES
    assert "Archive" not in WIDE_LAYOUT_MODES
    assert "Themes" not in WIDE_LAYOUT_MODES
    assert "People" not in WIDE_LAYOUT_MODES


def test_notebook_published_is_any_module_json_not_runs(tmp_path: Path) -> None:
    root = tmp_path / "nb"
    analysis = root / "analysis"
    (analysis / "runs" / "r1").mkdir(parents=True)
    (analysis / "runs" / "r1" / "published.json").write_text("{}", encoding="utf-8")
    assert notebook_has_published_analysis(root) is False
    stale = analysis / "stats"
    stale.mkdir()
    (stale / "published.json").write_text("{}", encoding="utf-8")
    assert notebook_has_published_analysis(root) is True
    assert notebook_has_published_analysis(None) is False
    assert notebook_has_published_analysis(tmp_path / "missing") is False


def test_notebook_detection_results(tmp_path: Path) -> None:
    root = tmp_path / "nb"
    detection = root / "detection" / "poetry"
    detection.mkdir(parents=True)
    assert notebook_has_detection_results(root) is False
    (detection / "published.json").write_text("{}", encoding="utf-8")
    assert notebook_has_detection_results(root) is True
