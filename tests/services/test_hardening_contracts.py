"""Deepened contract tests for ownership hardening surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.domain.models import AttemptError, OCRAttempt, PageResult
from transcribe.domain.validation import validate_page_result
from transcribe.errors import IngestError, ValidationError
from transcribe.ingest import IngestService
from transcribe.services.doctor import DoctorService
from transcribe.services.export import ExportService
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


def test_validate_page_result_rejects_illegal_status():
    attempt = OCRAttempt(
        attempt_id="a1",
        status="bogus",
        input_fingerprint="x",
        fingerprint_payload={},
        raw_text=None,
        provenance=None,
        provider_metadata={},
        started_at="2026-01-01T00:00:00.000Z",
        error=AttemptError(code="x", message="y"),
    )
    result = PageResult(page_id="p1", active_attempt_id="a1", attempts=[attempt])
    with pytest.raises(ValidationError, match="illegal attempt status"):
        validate_page_result(result, expected_page_id="p1")


def test_validate_page_result_rejects_page_id_mismatch():
    result = PageResult(page_id="p1")
    with pytest.raises(ValidationError, match="expected"):
        validate_page_result(result, expected_page_id="other")


def test_doctor_deep_detects_hash_mismatch(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    render = project.renders[project.pages[0].active_render_id]
    paths.resolve_contained(render.image_relpath).write_bytes(_png_bytes(color=(9, 9, 9)))
    report = DoctorService(paths, projects).run(deep=True)
    assert not report.ok
    assert any(f.code == "project_invalid" for f in report.findings)


def test_doctor_warns_on_unexplained_file(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("a.png", _png_bytes())
    orphan = paths.sources_dir / "orphan.bin"
    orphan.write_bytes(b"nope")
    report = DoctorService(paths, projects).run(deep=False)
    assert report.ok  # warnings only
    assert any(f.code == "unexplained_file" for f in report.findings)


def test_export_formats_share_snapshot(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("Notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    settings = project.settings
    settings.model_name = "fake-vision"
    projects.save_settings(project, settings)
    JobCoordinator(
        paths, projects, FakeVisionOCRProvider(default_text="snap-text"), clock=clock, ids=ids
    ).run_blocking()
    export = ExportService(paths, projects)
    snap = export.capture_snapshot()
    nb = export.build_notebook(snap)
    md = export.build_markdown(snap)
    txt = export.build_plaintext(snap)
    assert "snap-text" in nb["pages"][0]["text"]
    assert "snap-text" in md
    assert "snap-text" in txt
    written = export.export_all(dest_dir=tmp_path / "out")
    assert written["manifest"].exists()
    assert written["notebook"].exists()


def test_rendered_byte_budget_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from transcribe import ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "MAX_RENDERED_BYTES", 50)
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    with pytest.raises(IngestError, match="rendered output exceeds"):
        ingest.import_bytes("a.png", _png_bytes())


def test_cli_doctor_ok(tmp_path: Path):
    from transcribe.__main__ import main

    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    IngestService(paths, clock=clock, ids=ids).import_bytes("a.png", _png_bytes())
    assert main(["doctor", str(paths.root)]) == 0
    assert main(["doctor", "--deep", str(paths.root)]) == 0
