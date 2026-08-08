"""Deepened tests proposed for plan gaps (offline)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from transcribe.domain.models import AttemptError, OCRAttempt, PageResult
from transcribe.ingest import IngestService
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_ingest_fixture_png_and_pdf(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_path(FIXTURES / "mini_page.png")
    assert len(project.pages) == 1
    render = project.renders[project.pages[0].active_render_id]
    # Versioned render path: pages/<source_id>/<page_index>/<render_id>.png
    assert render.image_relpath.startswith("pages/")
    parts = render.image_relpath.split("/")
    assert len(parts) == 4
    assert parts[2] == "0000"
    assert parts[3].endswith(".png")

    project = ingest.import_path(FIXTURES / "mini_notebook.pdf", render_dpi=100)
    assert len(project.pages) == 1 + 3
    assert project.sources[-1].page_count == 3


def test_status_derived_from_active_attempt_not_payload():
    attempt = OCRAttempt(
        attempt_id="a1",
        status="failed",
        input_fingerprint="x",
        fingerprint_payload={},
        raw_text=None,
        provenance=None,
        provider_metadata={},
        started_at="2026-01-01T00:00:00.000Z",
        error=AttemptError(code="x", message="y", retriable=True),
    )
    result = PageResult.from_dict(
        {
            "format": "transcribe.page-result",
            "schema_version": 1,
            "page_id": "p1",
            "active_attempt_id": "a1",
            "edited_text": None,
            "attempts": [attempt.as_dict()],
            "status": "succeeded",  # lying top-level
            "updated_at": "2026-01-01T00:00:00.000Z",
        }
    )
    assert result.status == "failed"
    assert result.as_dict()["status"] == "failed"


def test_core_modules_do_not_import_streamlit():
    root = Path(__file__).resolve().parents[2] / "src" / "transcribe"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if "ui" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "streamlit" or alias.name.startswith("streamlit."):
                        offenders.append(str(path))
            elif isinstance(node, ast.ImportFrom):
                if node.module and (
                    node.module == "streamlit" or node.module.startswith("streamlit.")
                ):
                    offenders.append(str(path))
    assert offenders == []


def test_cooperative_cancel_stops_scheduling(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_path(FIXTURES / "mini_notebook.pdf", render_dpi=72)
    settings = project.settings
    settings.model_name = "fake-vision"
    settings.max_workers = 1
    projects.save_settings(project, settings)

    provider = FakeVisionOCRProvider()
    # Slow-ish fake: cancel after first page starts by hooking
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)

    original = provider.transcribe_image

    def wrapping(**kwargs):
        # Request cancel as soon as first page is being processed
        coord.request_cancel()
        return original(**kwargs)

    provider.transcribe_image = wrapping  # type: ignore[method-assign]
    progress = coord.run_blocking()
    assert progress.status == "cancelled"
    # At most one page should have been transcribed (workers=1)
    assert provider.calls <= 1
    assert progress.message.lower().startswith("stop")


def test_digest_missing_still_allows_generation(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_path(FIXTURES / "mini_page.png")
    settings = project.settings
    settings.model_name = "manual-override"
    projects.save_settings(project, settings)
    provider = FakeVisionOCRProvider(digest=None, verified=False, models=[])
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    progress = coord.run_blocking()
    assert progress.status == "completed"
    result = projects.load_page_result(project.pages[0].page_id)
    assert result is not None
    attempt = result.active_attempt()
    assert attempt is not None
    assert attempt.provenance is not None
    assert attempt.provenance.model_identity_verified is False
    assert attempt.fingerprint_payload["model_identity_verified"] is False


def test_versioned_render_paths_stable_across_sources(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_path(FIXTURES / "mini_page.png")
    project = ingest.import_path(FIXTURES / "mini_page.jpg")
    rels = [project.renders[p.active_render_id].image_relpath for p in project.pages]
    assert all("/0000/" in r for r in rels)
    assert rels[0] != rels[1]
    # global_index is presentation order only — pages list order
    assert [p.page_index for p in project.pages] == [0, 0]
