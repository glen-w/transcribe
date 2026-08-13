"""Progress labels and callbacks for long-running user-facing jobs."""

from __future__ import annotations

from pathlib import Path

from transcribe.corpus import CorpusPaths, ImportOrchestrator
from transcribe.corpus.adapters import plan_from_folder
from transcribe.domain.models import (
    OCRSettings,
    PageIndex,
    Project,
    SourceDocument,
    page_label,
)
from transcribe.ingest import IngestService
from transcribe.services.batch_ocr import (
    BatchOcrCoordinator,
    BatchOcrProgress,
    list_candidates,
    select_pending,
)
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.ui.run_transcribe import _batch_progress_to_snapshot
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


def test_page_label_uses_filename_and_pdf_index() -> None:
    settings = OCRSettings()
    image = SourceDocument(
        source_id="s1",
        original_filename="scan.png",
        stored_relpath="sources/s1-scan.png",
        media_type="image/png",
        sha256="a" * 64,
        page_count=1,
        imported_at="t",
        render_dpi=200,
    )
    pdf = SourceDocument(
        source_id="s2",
        original_filename="notes.pdf",
        stored_relpath="sources/s2-notes.pdf",
        media_type="application/pdf",
        sha256="b" * 64,
        page_count=3,
        imported_at="t",
        render_dpi=200,
    )
    pages = [
        PageIndex(
            page_id="p-img",
            source_id="s1",
            page_index=0,
            active_render_id="r1",
            width=10,
            height=10,
        ),
        PageIndex(
            page_id="p-pdf",
            source_id="s2",
            page_index=2,
            active_render_id="r2",
            width=10,
            height=10,
        ),
    ]
    project = Project(
        id="nb",
        title="nb",
        created_at="t",
        updated_at="t",
        settings=settings,
        sources=[image, pdf],
        pages=pages,
    )
    assert page_label(project, "p-img") == "scan.png"
    assert page_label(project, "p-pdf") == "notes.pdf · p.3"
    assert page_label(project, "missing").startswith("missing")


def test_job_progress_names_current_page(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("job")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("named")
    IngestService(paths, clock=clock, ids=ids).import_bytes(
        "cover.png", _png_bytes(color=(1, 2, 3))
    )
    project = projects.load()
    settings = project.settings
    settings.model_name = "fake-vision"
    projects.save_settings(project, settings)

    seen: list[str] = []

    class Recording(FakeVisionOCRProvider):
        def transcribe_image(self, **kwargs):
            seen.extend(coord.get_progress().current_labels)
            seen.append(coord.get_progress().message)
            return super().transcribe_image(**kwargs)

    provider = Recording()
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    progress = coord.run_blocking(force=True)
    assert progress.status == "completed"
    blob = " ".join(seen)
    assert "cover.png" in blob


def test_commit_run_emits_progress_per_item(tmp_path: Path) -> None:
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    corpus.ensure_layout()
    folder = tmp_path / "scans"
    folder.mkdir()
    (folder / "a.png").write_bytes(_png_bytes(color=(1, 1, 1)))
    (folder / "b.png").write_bytes(_png_bytes(color=(2, 2, 2)))

    plan = plan_from_folder(folder, ids=SequentialIds("plan"), title="Prog")
    orch = ImportOrchestrator(corpus, clock=FakeClock(), ids=SequentialIds("run"))
    run = orch.create_run_from_plan(plan)

    events: list[tuple[int, int, str]] = []
    completed = orch.commit_run(
        run.import_run_id,
        on_progress=lambda done, total, message: events.append((done, total, message)),
    )

    assert completed.status == "complete"
    assert events[0] == (0, len(plan.items), "Starting…")
    assert events[-1][0] == len(plan.items)
    assert events[-1][1] == len(plan.items)
    assert "Finished" in events[-1][2]
    dones = [e[0] for e in events]
    assert dones == sorted(dones)
    assert max(dones) == len(plan.items)
    assert any("a.png" in msg or "b.png" in msg for _, _, msg in events)


def test_batch_ocr_progress_names_notebook_and_page(tmp_path: Path) -> None:
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    corpus.ensure_layout()
    clock, ids = FakeClock(), SequentialIds("bat")
    root = corpus.projects_dir / "alpha"
    projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
    projects.create("alpha")
    IngestService(open_project_paths(root), clock=clock, ids=ids).import_bytes(
        "alpha-0.png", _png_bytes(color=(3, 4, 5))
    )
    settings = projects.load().settings
    settings.model_name = "fake-vision"
    projects.save_settings(projects.load(), settings)

    coord = BatchOcrCoordinator(corpus, clock=clock, ids=ids)
    seen: list[str] = []

    class Recording(FakeVisionOCRProvider):
        def transcribe_image(self, **kwargs):
            live = coord.get_progress()
            seen.append(live.current_item)
            seen.append(live.current_page_label)
            seen.append(live.message)
            return super().transcribe_image(**kwargs)

    coord.provider = Recording()
    selected = select_pending(list_candidates(corpus, clock=clock, ids=ids))
    run = coord.create_run(
        selected, settings=OCRSettings(model_name="fake-vision"), force=True
    )
    progress = coord.run_blocking(run.ocr_run_id)
    assert progress.status == "completed"
    blob = " ".join(seen)
    assert "alpha" in blob
    assert "alpha-0.png" in blob

    snap = _batch_progress_to_snapshot(
        BatchOcrProgress(
            ocr_run_id="x",
            status="running",
            total=2,
            completed=0,
            current_item="1/2 · alpha",
            current_page_label="alpha-0.png",
            pages_completed=1,
            pages_total=4,
            pages_failed=0,
            pages_skipped=0,
            message="Waiting on Ollama for alpha-0.png (1/4)…",
        )
    )
    assert snap["detail_current"] == "alpha-0.png"
    assert snap["detail_total"] == 4
    assert snap["current_item"] == "1/2 · alpha"
    assert 0 < snap["pct"] < 50
