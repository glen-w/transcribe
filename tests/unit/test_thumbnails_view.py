"""Unit tests for Reading/Review thumbnails overview helpers."""

from __future__ import annotations

from pathlib import Path

from transcribe.ingest import IngestService
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.ui import thumbnails_view as tv
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def test_clear_thumbs_view_state_removes_keys() -> None:
    session = {
        "viewer_thumbs_mode": True,
        "viewer_thumbs_cols": 7,
        "viewer_thumbs_selected": "page-1",
        "keep": 1,
    }
    tv.clear_thumbs_view_state(session)
    assert "viewer_thumbs_mode" not in session
    assert "viewer_thumbs_cols" not in session
    assert "viewer_thumbs_selected" not in session
    assert session["keep"] == 1


def test_cols_clamped_to_bounds(monkeypatch) -> None:
    class _State(dict):
        pass

    state = _State()
    monkeypatch.setattr(tv.st, "session_state", state)

    state["viewer_thumbs_cols"] = 99
    assert tv._cols() == tv._MAX_COLS
    state["viewer_thumbs_cols"] = 1
    assert tv._cols() == tv._MIN_COLS
    state["viewer_thumbs_cols"] = "nope"
    assert tv._cols() == tv._DEFAULT_COLS
    state["viewer_thumbs_cols"] = 5
    assert tv._cols() == 5


def test_selected_page_id_falls_back(monkeypatch) -> None:
    class _State(dict):
        pass

    state = _State()
    monkeypatch.setattr(tv.st, "session_state", state)
    assert tv._selected_page_id("fallback") == "fallback"
    state["viewer_thumbs_selected"] = "picked"
    assert tv._selected_page_id("fallback") == "picked"


def test_entry_for_page() -> None:
    entries = [
        {"page_id": "a", "project_root": "/r"},
        {"page_id": "b", "project_root": "/r"},
    ]
    assert tv._entry_for_page(entries, "b") == entries[1]
    assert tv._entry_for_page(entries, "z") is None


def test_thumbs_mode_active(monkeypatch) -> None:
    class _State(dict):
        pass

    state = _State()
    monkeypatch.setattr(tv.st, "session_state", state)
    assert tv.thumbs_mode_active() is False
    state["viewer_thumbs_mode"] = True
    assert tv.thumbs_mode_active() is True


def test_clear_page_viewer_state_clears_thumbs() -> None:
    from transcribe.ui.action_menus.nav import clear_page_viewer_state

    session = {
        "show_page_viewer": True,
        "view_page_id": "x",
        "viewer_thumbs_mode": True,
        "viewer_thumbs_cols": 6,
        "viewer_thumbs_selected": "x",
    }
    clear_page_viewer_state(session)
    assert session["show_page_viewer"] is False
    assert "viewer_thumbs_mode" not in session
    assert "viewer_thumbs_selected" not in session


def test_icons_include_grid_and_zoom_out() -> None:
    from transcribe.ui import icons as ic

    assert "grid_view" in ic.GRID_VIEW
    assert "zoom_out" in ic.ZOOM_OUT


def test_reading_and_review_wire_thumbnails_overview() -> None:
    """Acceptance: Reading (read presentation) and Review both host the grid."""
    page_viewer = Path("src/transcribe/ui/page_viewer.py").read_text(encoding="utf-8")
    review = Path("src/transcribe/ui/review_workbench.py").read_text(encoding="utf-8")
    thumbs = Path("src/transcribe/ui/thumbnails_view.py").read_text(encoding="utf-8")

    assert "render_thumbs_toggle_button" in page_viewer
    assert "render_thumbnails_view" in page_viewer
    assert "thumbs_mode_active" in page_viewer
    assert 'if read_only:' in page_viewer
    assert "pv_thumbs_toggle" in page_viewer

    assert "render_thumbs_toggle_button" in review
    assert "render_thumbnails_view" in review
    assert "rw_thumbs_toggle" in review

    assert "Go to page" in thumbs
    assert "ZOOM_OUT" in thumbs and "ZOOM_IN" in thumbs
    assert "tx_thumb_" in thumbs
    assert "_open_entry" in thumbs
    assert "ensure_grid_thumb" in thumbs
    assert '_warm_grid_thumbs' in thumbs
    assert 'help=widget_help("Open this page in the normal view")' in thumbs


def test_shell_css_covers_thumb_overlay_clicks() -> None:
    shell = Path("src/transcribe/ui/shell.py").read_text(encoding="utf-8")
    assert "st-key-tx_thumbwrap_" in shell
    assert "st-key-tx_thumb_" in shell
    assert "pointer-events: none" in shell
    assert "clear_thumbs_view_state" in shell


def test_thumb_cell_uses_keyed_wrap_for_overlay() -> None:
    thumbs = Path("src/transcribe/ui/thumbnails_view.py").read_text(encoding="utf-8")
    assert "tx_thumbwrap_" in thumbs
    assert "key=wrap_key" in thumbs
    assert "reading_page_by_root" in thumbs


def test_open_entry_leaves_thumbs_and_sets_viewer(monkeypatch) -> None:
    class _State(dict):
        pass

    state = _State()
    state["viewer_thumbs_mode"] = True
    state["reading_page_by_root"] = {"/other": "old"}
    monkeypatch.setattr(tv.st, "session_state", state)

    navigated: list[dict[str, str]] = []

    def _fake_nav(entry: dict[str, str]) -> None:
        navigated.append(entry)
        state["view_page_id"] = entry["page_id"]
        state["root"] = entry["project_root"]

    monkeypatch.setattr(
        "transcribe.ui.page_viewer._navigate_to_entry",
        _fake_nav,
    )
    entry = {"page_id": "page-42", "project_root": "/nb"}
    tv._open_entry(entry)

    assert state["viewer_thumbs_mode"] is False
    assert state["viewer_thumbs_selected"] == "page-42"
    assert state["reading_page_by_root"]["/nb"] == "page-42"
    assert state["reading_page_by_root"]["/other"] == "old"
    assert navigated == [entry]


def test_docs_mention_thumbnails_on_reading_and_review() -> None:
    surfaces = Path("docs/public_surfaces.md").read_text(encoding="utf-8")
    guide = Path("docs/user_guide.md").read_text(encoding="utf-8")
    assert "Thumbnails" in surfaces
    assert "click a thumb to open" in surfaces
    assert "Thumbnails" in guide
    assert "click a thumb to open" in guide


def test_notebook_cache_and_page_lookup(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("thumbs-nb")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    project = ingest.import_bytes("b.png", _png_bytes())
    root = str(paths.root)
    entries = [
        {"page_id": project.pages[0].page_id, "project_root": root},
        {"page_id": project.pages[1].page_id, "project_root": root},
        {"page_id": "missing-page", "project_root": root},
        {"page_id": "x", "project_root": str(tmp_path / "gone")},
    ]
    cache = tv._notebook_cache(entries)
    assert root in cache
    assert str(tmp_path / "gone") not in cache

    loaded = tv._page_from_cache(cache, entries[0])
    assert loaded is not None
    assert loaded[3].page_id == project.pages[0].page_id
    assert tv._page_from_cache(cache, entries[2]) is None
    assert tv._page_from_cache(cache, entries[3]) is None


def test_cover_page_id_helper() -> None:
    from types import SimpleNamespace

    with_cover = SimpleNamespace(
        cover_page_id="c2",
        pages=[SimpleNamespace(page_id="c1"), SimpleNamespace(page_id="c2")],
    )
    assert tv._cover_page_id(with_cover) == "c2"  # type: ignore[arg-type]
    fallback = SimpleNamespace(cover_page_id=None, pages=[SimpleNamespace(page_id="only")])
    assert tv._cover_page_id(fallback) == "only"  # type: ignore[arg-type]
    empty = SimpleNamespace(cover_page_id=None, pages=[])
    assert tv._cover_page_id(empty) is None  # type: ignore[arg-type]


def test_zoom_out_means_more_columns() -> None:
    """Product semantics: zoom out → denser grid; zoom in → larger thumbs."""
    assert tv._MIN_COLS < tv._DEFAULT_COLS < tv._MAX_COLS
