"""Reader hides ignored pages by default and agrees with export."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tests.conftest import FakeClock, SequentialIds
from transcribe.domain.dates import ApproximateDate
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes
from transcribe.ingest import IngestService
from transcribe.services.export import ExportService
from transcribe.services.export_document import build_document
from transcribe.services.export_options import ExportOptions
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.ui.action_menus.nav import reader_page_ids


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


def test_reader_page_ids_follow_date_order_and_skip_ignored() -> None:
    pages = [
        SimpleNamespace(page_id="late", date=ApproximateDate(2024, 5, 1), ignored=False),
        SimpleNamespace(page_id="undated", date=None, ignored=False),
        SimpleNamespace(page_id="early", date=ApproximateDate(2024, 1, 1), ignored=False),
        SimpleNamespace(page_id="skip", date=ApproximateDate(2024, 3, 1), ignored=True),
    ]
    project = SimpleNamespace(pages=pages)
    assert reader_page_ids(project, hide_ignored=True) == ["early", "late", "undated"]
    assert reader_page_ids(project, hide_ignored=False) == ["early", "skip", "late", "undated"]


def test_reader_hides_ignored_pages_by_default(tmp_path: Path):
    paths, projects = _two_page_notebook(tmp_path)
    project = projects.load()
    kept_id, hidden_id = project.pages[0].page_id, project.pages[1].page_id
    project = projects.update_page_metadata(hidden_id, ignored=True)

    hidden = reader_page_ids(project, hide_ignored=True)
    shown = reader_page_ids(project, hide_ignored=False)
    assert hidden == [kept_id]
    assert shown == [kept_id, hidden_id]

    reloaded = projects.load(reconcile=False)
    assert reloaded.pages[1].ignored is True
    assert "ignored" not in reloaded.pages[0].as_dict()


def test_reader_and_export_agree_on_ignored_pages(tmp_path: Path):
    paths, projects = _two_page_notebook(tmp_path)
    project = projects.update_page_metadata(projects.load().pages[1].page_id, ignored=True)

    snap = ExportService(paths, projects).capture_snapshot()
    excluded = build_document([snap], ExportOptions(exclude_ignored_pages=True))
    included = build_document([snap], ExportOptions(exclude_ignored_pages=False))

    assert reader_page_ids(project, hide_ignored=True) == [
        section.page_id for section in excluded.parts[0].sections
    ]
    assert reader_page_ids(project, hide_ignored=False) == [
        section.page_id for section in included.parts[0].sections
    ]


def test_reader_empty_when_every_page_is_ignored(tmp_path: Path):
    _paths, projects = _two_page_notebook(tmp_path)
    project = projects.load()
    for page in project.pages:
        project = projects.update_page_metadata(page.page_id, ignored=True)
    assert reader_page_ids(project, hide_ignored=True) == []
    assert reader_page_ids(project, hide_ignored=False) == [p.page_id for p in project.pages]
