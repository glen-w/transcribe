"""People / View jumps must open the intended page, not the last Reading resume."""

from __future__ import annotations

from pathlib import Path

from transcribe.ingest import IngestService
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.ui import page_viewer as pv
from transcribe.ui import view_jumps
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def test_remember_reading_page_uses_resolved_root(monkeypatch, tmp_path: Path) -> None:
    class _State(dict):
        pass

    state = _State()
    monkeypatch.setattr(pv.st, "session_state", state)
    root = tmp_path / "nb"
    root.mkdir()
    pv.remember_reading_page(root, "page-a")
    pv.remember_reading_page(str(root / ".." / root.name), "page-b")
    key = str(root.resolve())
    assert state["reading_page_by_root"] == {key: "page-b"}


def test_open_page_context_sets_resume_pointer_and_clears_stale_widgets(
    monkeypatch, tmp_path: Path
) -> None:
    class _State(dict):
        pass

    state = _State()
    state["reading_page_by_root"] = {"/other": "old"}
    state["reading_jump_by_date"] = "stale-page"
    state["viewer_thumbs_mode"] = True
    monkeypatch.setattr(pv.st, "session_state", state)

    root = tmp_path / "nb"
    root.mkdir()
    pv.open_page_context(
        page_id="page-42",
        page_ids=["page-1", "page-42"],
        project_root=root,
        highlight="Alice",
        return_mode="People",
    )

    resolved = str(root.resolve())
    assert state["view_page_id"] == "page-42"
    assert state["show_page_viewer"] is True
    assert state["view_highlight"] == "Alice"
    assert state["page_return_mode"] == "People"
    assert state["reading_page_by_root"][resolved] == "page-42"
    assert state["reading_page_by_root"]["/other"] == "old"
    assert "reading_jump_by_date" not in state
    assert "viewer_thumbs_mode" not in state
    assert state["root"] == resolved
    assert state["pending_notebook_root"] == resolved


def test_jump_person_occurrence_opens_that_page_not_resume(
    monkeypatch, tmp_path: Path
) -> None:
    class _State(dict):
        pass

    state = _State()
    monkeypatch.setattr(pv.st, "session_state", state)
    monkeypatch.setattr(view_jumps.st, "session_state", state)

    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("people-jump")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    project = ingest.import_bytes("b.png", _png_bytes())
    first, second = project.pages[0].page_id, project.pages[1].page_id
    root = str(paths.root)
    state["reading_page_by_root"] = {root: first}
    state["view_page_id"] = first

    view_jumps.jump_person_occurrence(second, root, "Alice")

    assert state["ui_mode"] == "Reading"
    assert state["view_page_id"] == second
    assert state["show_page_viewer"] is True
    assert state["reading_page_by_root"][root] == second
    assert state["view_highlight"] == "Alice"
    assert state["page_return_mode"] == "People"
