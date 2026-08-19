from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import mutation_lock
from transcribe.persistence.schema import require_format
from transcribe.domain.models import Project
from transcribe.services.export import ExportService
from transcribe.services.export_document import build_document
from transcribe.services.export_options import ExportOptions
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths


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
    with mutation_lock(projects.paths.mutation_lock):
        payload = require_format(read_json(projects.paths.manifest), "transcribe.project")
        current = Project.from_dict(payload)
        current.pages[page_index].ignored = True
        write_json_atomic(projects.paths.manifest, current.as_dict())


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
