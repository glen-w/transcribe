"""Batch OCR selection, resume, and cancel (offline, fake provider)."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.corpus.ocr_run import OcrBatchRunStore, finalize_ocr_batch_status
from transcribe.corpus.paths import CorpusPaths
from transcribe.domain.models import OCRSettings
from transcribe.errors import ValidationError
from transcribe.ingest import IngestService
from transcribe.services.batch_ocr import (
    BatchOcrCoordinator,
    list_candidates,
    select_by_ids,
    select_from_import_run,
    select_pending,
)
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


def _corpus(tmp_path: Path) -> CorpusPaths:
    paths = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    paths.projects_dir.mkdir(parents=True)
    paths.ensure_layout()
    return paths


def _make_notebook(
    corpus: CorpusPaths,
    name: str,
    *,
    clock: FakeClock,
    ids: SequentialIds,
    pages: int = 1,
) -> Path:
    root = corpus.projects_dir / name
    projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
    project = projects.create(name)
    ingest = IngestService(open_project_paths(root), clock=clock, ids=ids)
    for i in range(pages):
        ingest.import_bytes(f"{name}-{i}.png", _png_bytes(color=(i + 1, 20, 30)))
    settings = project.settings
    settings.model_name = "fake-vision"
    projects.save_settings(projects.load(), settings)
    return root


def test_select_pending_skips_fully_transcribed(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("sel")
    _make_notebook(corpus, "pending-nb", clock=clock, ids=ids)
    done_root = _make_notebook(corpus, "done-nb", clock=clock, ids=ids)
    provider = FakeVisionOCRProvider()
    paths = open_project_paths(done_root)
    projects = ProjectService(paths, clock=clock, ids=ids)
    from transcribe.services.job import JobCoordinator

    JobCoordinator(paths, projects, provider, clock=clock, ids=ids).run_blocking()

    candidates = list_candidates(corpus, clock=clock, ids=ids)
    pending = select_pending(candidates)
    assert {c.title for c in pending} == {"pending-nb"}
    by_id = select_by_ids(candidates, [c.notebook_id for c in candidates])
    assert len(by_id) == 2


def test_select_from_import_run_uses_committed_notebooks_only(tmp_path: Path) -> None:
    from transcribe.corpus.import_run import ImportRun, ImportRunItemOutcome, ImportRunStore
    from transcribe.corpus.plan import POLICY_SKIP_EXISTING_V1

    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("imp")
    _make_notebook(corpus, "kept", clock=clock, ids=ids)
    _make_notebook(corpus, "skipped-nb", clock=clock, ids=ids)
    candidates = list_candidates(corpus, clock=clock, ids=ids)
    by_title = {c.title: c for c in candidates}
    run = ImportRun(
        import_run_id="imprun1",
        plan_id="plan1",
        plan_fingerprint="a" * 64,
        import_policy_id=POLICY_SKIP_EXISTING_V1,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        status="complete",
        items=[
            ImportRunItemOutcome(
                item_id="i1",
                state="committed",
                resulting_ids={"notebook_id": by_title["kept"].notebook_id},
            ),
            ImportRunItemOutcome(
                item_id="i2",
                state="skipped",
                resulting_ids={"notebook_id": by_title["skipped-nb"].notebook_id},
            ),
        ],
    )
    ImportRunStore(corpus).save(run)
    selected = select_from_import_run(corpus, "imprun1", candidates)
    assert [c.title for c in selected] == ["kept"]


def test_batch_ocr_runs_two_notebooks_and_skips_on_resume(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("bat")
    _make_notebook(corpus, "alpha", clock=clock, ids=ids, pages=1)
    _make_notebook(corpus, "beta", clock=clock, ids=ids, pages=1)
    provider = FakeVisionOCRProvider()
    coord = BatchOcrCoordinator(corpus, clock=clock, ids=ids, provider=provider)
    selected = select_pending(list_candidates(corpus, clock=clock, ids=ids))
    settings = OCRSettings(model_name="fake-vision")
    run = coord.create_run(selected, settings=settings, force=False)
    progress = coord.run_blocking(run.ocr_run_id)
    assert progress.status == "completed"
    assert provider.calls == 2
    stored = OcrBatchRunStore(corpus).load(run.ocr_run_id)
    assert all(i.state == "completed" for i in stored.items)

    resumed = coord.resume(run.ocr_run_id, blocking=True)
    assert resumed.status == "completed"
    assert provider.calls == 2  # fingerprint skip; no new vision calls


def test_batch_ocr_cancel_does_not_start_next_notebook(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("can")
    _make_notebook(corpus, "first", clock=clock, ids=ids, pages=1)
    _make_notebook(corpus, "second", clock=clock, ids=ids, pages=1)

    coord = BatchOcrCoordinator(corpus, clock=clock, ids=ids)

    class CancelAfterFirst(FakeVisionOCRProvider):
        def transcribe_image(self, **kwargs):
            coord.request_cancel()
            return super().transcribe_image(**kwargs)

    provider = CancelAfterFirst()
    coord.provider = provider
    selected = select_pending(list_candidates(corpus, clock=clock, ids=ids))
    # Stable order by discover_project_roots (sorted folder names): first, second
    run = coord.create_run(
        selected, settings=OCRSettings(model_name="fake-vision"), force=False
    )
    progress = coord.run_blocking(run.ocr_run_id)
    stored = OcrBatchRunStore(corpus).load(run.ocr_run_id)
    states = [i.state for i in stored.items]
    assert "cancelled" in states
    assert states.count("completed") == 1
    assert progress.status in {"cancelled", "partial"}
    assert provider.calls == 1


def test_create_run_requires_model_and_notebooks(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    coord = BatchOcrCoordinator(corpus, clock=FakeClock(), ids=SequentialIds("req"))
    with pytest.raises(ValidationError, match="at least one"):
        coord.create_run([], settings=OCRSettings(model_name="fake-vision"))
    with pytest.raises(ValidationError, match="vision model"):
        clock, ids = FakeClock(), SequentialIds("req2")
        _make_notebook(corpus, "nb", clock=clock, ids=ids)
        selected = list_candidates(corpus, clock=clock, ids=ids)
        coord.create_run(selected, settings=OCRSettings(model_name=""))


def test_finalize_status_partial_when_cancelled_after_success() -> None:
    from transcribe.corpus.ocr_run import OcrBatchItem, OcrBatchRun

    run = OcrBatchRun(
        ocr_run_id="r1",
        created_at="t",
        updated_at="t",
        status="running",
        items=[
            OcrBatchItem(notebook_id="a", state="completed"),
            OcrBatchItem(notebook_id="b", state="cancelled"),
        ],
    )
    assert finalize_ocr_batch_status(run) == "partial"
