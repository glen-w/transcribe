from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes
from transcribe.ingest import IngestService
from transcribe.services.export import ExportService
from transcribe.services.export_document import build_document
from transcribe.services.export_options import ExportOptions
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.ui.action_menus.nav import chronological_page_ids


def _two_page_notebook(tmp_path: Path) -> tuple:
    paths = open_project_paths(tmp_path / "nb")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("Two pages")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("a.png", _png_bytes())
    ingest.import_bytes("b.png", _png_bytes())
    project = projects.load()
    settings = project.settings
    settings.model_name = "fake-vision"
    project = projects.save_settings(project, settings)
    coord = JobCoordinator(paths, projects, FakeVisionOCRProvider(), clock=clock, ids=ids)
    coord.run_blocking()
    return paths, projects


def _mark_page_ignored(projects: ProjectService, page_index: int) -> None:
    page_id = projects.load().pages[page_index].page_id
    projects.set_page_ignored(page_id, True)


def test_export_excludes_ignored_pages_from_reading_formats(tmp_path: Path):
    paths, projects = _two_page_notebook(tmp_path)
    _mark_page_ignored(projects, 1)

    export = ExportService(paths, projects)
    snap = export.capture_snapshot()
    with_exclude = build_document([snap], ExportOptions(exclude_ignored_pages=True))
    with_include = build_document([snap], ExportOptions(exclude_ignored_pages=False))

    assert len(with_exclude.parts[0].sections) == 1
    assert len(with_include.parts[0].sections) == 2


def test_export_json_keeps_ignored_flag(tmp_path: Path):
    paths, projects = _two_page_notebook(tmp_path)
    _mark_page_ignored(projects, 0)

    export = ExportService(paths, projects)
    notebook = export.build_notebook(export.capture_snapshot())
    assert len(notebook["pages"]) == 2
    assert notebook["pages"][0].get("ignored") is True
    assert "ignored" not in notebook["pages"][1]


def test_set_page_ignored_round_trip_and_reading_filter(tmp_path: Path):
    _paths, projects = _two_page_notebook(tmp_path)
    project = projects.load()
    page_id = project.pages[1].page_id
    projects.set_page_ignored(page_id, True)
    project = projects.load()
    assert project.pages[1].ignored is True
    all_ids = chronological_page_ids(project, include_ignored=True)
    visible = chronological_page_ids(project, include_ignored=False)
    assert page_id in all_ids
    assert page_id not in visible
    assert len(visible) == 1
    projects.set_page_ignored(page_id, False)
    assert projects.load().pages[1].ignored is False
