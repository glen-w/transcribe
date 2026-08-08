"""Additional ownership-hardening coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transcribe.domain.validation import validate_project
from transcribe.errors import ValidationError
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import write_json_atomic
from transcribe.services.doctor import DoctorService
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


def test_ingest_reloads_under_lock(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    # Concurrent-style metadata write then ingest must not lose tags.
    projects.update_notebook_metadata(tags=["kept"])
    project = ingest.import_bytes("a.png", _png_bytes())
    assert project.tags == ["kept"]
    assert len(project.pages) == 1


def test_ingest_recovers_manifest_pending_journal(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    source = project.sources[0]
    page = project.pages[0]
    render = project.renders[page.active_render_id]

    from transcribe.domain.models import Project

    bare_project = Project.from_dict(
        {
            **project.as_dict(),
            "sources": [],
            "pages": [],
            "renders": {},
        }
    )
    journal = {
        "format": "transcribe.ingest-journal",
        "schema_version": 1,
        "attempt_id": "recover-me",
        "state": "manifest_pending",
        "source": {
            "source_id": source.source_id,
            "original_filename": source.original_filename,
            "media_type": source.media_type,
            "sha256": source.sha256,
            "page_count": 1,
            "imported_at": source.imported_at,
            "render_dpi": source.render_dpi,
            "staged_rel": ".staging/x",
            "final_rel": source.stored_relpath,
        },
        "pages": [
            {
                "page_id": page.page_id,
                "page_index": 0,
                "render_id": render.render_id,
                "width": page.width,
                "height": page.height,
                "png_sha": render.rendered_image_sha256,
                "pdf_page_index": None,
                "staged_rel": ".staging/y",
                "final_rel": render.image_relpath,
                "renderer": render.renderer,
                "renderer_version": render.renderer_version,
                "source_sha256": render.source_sha256,
                "render_dpi": render.render_dpi,
            }
        ],
    }
    write_json_atomic(paths.ingest_journal, journal)
    write_json_atomic(paths.manifest, bare_project.as_dict())
    assert paths.resolve_contained(source.stored_relpath).exists()

    ingest.recover_incomplete_ingest()
    recovered = projects.load()
    assert len(recovered.sources) == 1
    assert recovered.sources[0].source_id == source.source_id
    assert not paths.ingest_journal.exists()


def test_load_rolls_back_staged_only_journal(tmp_path: Path):
    """Crash after journal write, before any promote → load clears journal, no orphans."""
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    staging = paths.staging_attempt_dir("crash-staged")
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "note.png").write_bytes(_png_bytes())
    write_json_atomic(
        paths.ingest_journal,
        {
            "format": "transcribe.ingest-journal",
            "schema_version": 1,
            "attempt_id": "crash-staged",
            "state": "staged",
            "source": {
                "source_id": "src-orph",
                "original_filename": "note.png",
                "media_type": "image/png",
                "sha256": "a" * 64,
                "page_count": 1,
                "imported_at": "2026-01-01T00:00:00.000Z",
                "render_dpi": 200,
                "staged_rel": ".staging/crash-staged/note.png",
                "final_rel": "sources/src-orph-note.png",
            },
            "pages": [],
        },
    )
    project = projects.load()
    assert project.sources == []
    assert not paths.ingest_journal.exists()
    assert not staging.exists()


def test_load_rolls_back_promoting_orphans(tmp_path: Path):
    """Crash mid-promote: finals exist but not in manifest → load deletes orphans."""
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    final_source = paths.sources_dir / "src-orph-note.png"
    final_source.write_bytes(_png_bytes())
    final_png = paths.page_render_path("src-orph", 0, "rnd-orph")
    final_png.parent.mkdir(parents=True, exist_ok=True)
    final_png.write_bytes(_png_bytes())
    write_json_atomic(
        paths.ingest_journal,
        {
            "format": "transcribe.ingest-journal",
            "schema_version": 1,
            "attempt_id": "crash-promoting",
            "state": "promoting",
            "source": {
                "source_id": "src-orph",
                "original_filename": "note.png",
                "media_type": "image/png",
                "sha256": "b" * 64,
                "page_count": 1,
                "imported_at": "2026-01-01T00:00:00.000Z",
                "render_dpi": 200,
                "staged_rel": ".staging/crash-promoting/note.png",
                "final_rel": "sources/src-orph-note.png",
            },
            "pages": [
                {
                    "page_id": "pg-orph",
                    "page_index": 0,
                    "render_id": "rnd-orph",
                    "width": 10,
                    "height": 10,
                    "png_sha": "c" * 64,
                    "pdf_page_index": None,
                    "staged_rel": ".staging/crash-promoting/0000-rnd-orph.png",
                    "final_rel": paths.relativize(final_png),
                    "renderer": "pillow",
                    "renderer_version": "1",
                    "source_sha256": "b" * 64,
                    "render_dpi": 200,
                }
            ],
        },
    )
    project = projects.load()
    assert project.sources == []
    assert not final_source.exists()
    assert not final_png.exists()
    assert not paths.ingest_journal.exists()


def test_job_plan_ignores_live_provider_swap(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    settings = project.settings
    settings.model_name = "fake-vision"
    projects.save_settings(project, settings)
    provider_a = FakeVisionOCRProvider(default_text="from-a")
    provider_b = FakeVisionOCRProvider(default_text="from-b")
    coord = JobCoordinator(paths, projects, provider_a, clock=clock, ids=ids)

    original_build = coord._build_plan

    def build_and_swap(*args, **kwargs):
        plan = original_build(*args, **kwargs)
        coord.provider = provider_b
        return plan

    coord._build_plan = build_and_swap  # type: ignore[method-assign]
    progress = coord.run_blocking()
    assert progress.status == "completed"
    result = projects.load_page_result(project.pages[0].page_id)
    assert result is not None
    text = result.active_attempt().raw_text  # type: ignore[union-attr]
    assert text is not None and text.startswith("from-a")
    assert provider_a.calls == 1
    assert provider_b.calls == 0


def test_unverified_model_identity_never_skips(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    settings = project.settings
    settings.model_name = "manual-override"
    projects.save_settings(project, settings)
    provider = FakeVisionOCRProvider(digest=None, verified=False, models=[])
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    first = coord.run_blocking()
    assert first.status == "completed"
    assert provider.calls == 1
    second = coord.run_blocking()
    assert second.skipped == 0
    assert provider.calls == 2


def test_progress_get_returns_snapshot(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    settings = project.settings
    settings.model_name = "fake-vision"
    projects.save_settings(project, settings)
    coord = JobCoordinator(
        paths, projects, FakeVisionOCRProvider(), clock=clock, ids=ids
    )
    coord.run_blocking()
    snap = coord.get_progress()
    snap.completed = 999
    assert coord.get_progress().completed != 999


def test_job_record_persisted(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    settings = project.settings
    settings.model_name = "fake-vision"
    projects.save_settings(project, settings)
    coord = JobCoordinator(
        paths, projects, FakeVisionOCRProvider(), clock=clock, ids=ids
    )
    progress = coord.run_blocking()
    records = list(paths.jobs_dir.glob("*.json"))
    assert len(records) == 1
    payload = json.loads(records[0].read_text())
    assert payload["job_id"] == progress.job_id
    assert payload["status"] == "completed"


def test_doctor_reports_ok(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("a.png", _png_bytes())
    report = DoctorService(paths, projects).run(deep=True)
    assert report.ok


def test_validate_rejects_bad_workers(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("t")
    project.settings.max_workers = 9
    with pytest.raises(ValidationError):
        validate_project(project)
