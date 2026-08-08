from __future__ import annotations

from pathlib import Path

from transcribe.ingest import IngestService
from transcribe.services.export import ExportService
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


def test_export_portable_no_absolute_paths(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("Notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    settings = project.settings
    settings.model_name = "fake-vision"
    project = projects.save_settings(project, settings)
    coord = JobCoordinator(
        paths, projects, FakeVisionOCRProvider(), clock=clock, ids=ids
    )
    coord.run_blocking()
    projects.save_user_edit(project.pages[0].page_id, "edited page")
    export = ExportService(paths, projects)
    written = export.export_all(dest_dir=tmp_path / "out")
    assert written["manifest"].exists()
    notebook = export.build_notebook(projects.load())
    assert notebook["format"] == "transcribe.notebook"
    blob = str(notebook)
    assert str(paths.root) not in blob
    assert notebook["pages"][0]["edited"] is True
    assert notebook["pages"][0]["text"] == "edited page"
