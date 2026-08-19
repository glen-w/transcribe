from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes
from transcribe.ingest import IngestService
from transcribe.services.export_document import build_document
from transcribe.services.export import ExportService
from transcribe.services.export_html import build_html
from transcribe.services.export_options import ExportOptions
from transcribe.services.export_pdf import build_pdf
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths


def _notebook_with_page(tmp_path: Path) -> tuple:
    paths = open_project_paths(tmp_path / "nb")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("Cover book")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("a.png", _png_bytes())
    project = projects.load()
    settings = project.settings
    settings.model_name = "fake-vision"
    project = projects.save_settings(project, settings)
    coord = JobCoordinator(paths, projects, FakeVisionOCRProvider(), clock=clock, ids=ids)
    coord.run_blocking()
    return paths, projects


def test_export_cover_image_in_html_and_pdf(tmp_path: Path):
    paths, projects = _notebook_with_page(tmp_path)
    export = ExportService(paths, projects)
    snap = export.capture_snapshot()
    assert snap.cover_image_path is not None
    assert snap.cover_image_path.is_file()

    document = build_document([snap], ExportOptions(cover_image=True, title_page=False))

    html = build_html(document, ExportOptions(cover_image=True, title_page=False))
    assert 'class="cover-image"' in html
    assert "data:image/" in html

    pdf = build_pdf(document, ExportOptions(cover_image=True, title_page=False))
    assert pdf[:4] == b"%PDF"

    without = build_html(document, ExportOptions(cover_image=False, title_page=False))
    assert 'class="cover-image"' not in without
