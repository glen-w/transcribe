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


def test_batch_ocr_resumes_multipage_partial_notebook(tmp_path: Path) -> None:
    """Batch OCR completes remaining pages after a partial single-notebook job."""
    from transcribe.services.job import JobCoordinator

    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("mpart")
    root = corpus.projects_dir / "multi"
    projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
    projects.create("multi")
    ingest = IngestService(open_project_paths(root), clock=clock, ids=ids)
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "mini_multipage.pdf"
    ingest.import_path(fixture, render_dpi=72)
    paths = open_project_paths(root)
    projects = ProjectService(paths, clock=clock, ids=ids)
    settings = OCRSettings(model_name="fake-vision")
    projects.save_settings(projects.load(), settings)
    inner = JobCoordinator(paths, projects, FakeVisionOCRProvider(), clock=clock, ids=ids)

    class CancelAfterFirst(FakeVisionOCRProvider):
        def transcribe_image(self, **kwargs):
            result = super().transcribe_image(**kwargs)
            if self.calls == 1:
                inner.request_cancel()
            return result

    inner.provider = CancelAfterFirst()
    inner.run_blocking()
    project = projects.load()
    succeeded = sum(
        1
        for page in project.pages
        if (result := projects.load_page_result(page.page_id))
        and result.status == "succeeded"
    )
    assert 1 <= succeeded < len(project.pages)

    batch_provider = FakeVisionOCRProvider()
    coord = BatchOcrCoordinator(corpus, clock=clock, ids=ids, provider=batch_provider)
    selected = select_by_ids(list_candidates(corpus, clock=clock, ids=ids), [project.id])
    run = coord.create_run(selected, settings=settings, force=False)
    progress = coord.run_blocking(run.ocr_run_id)
    assert progress.status == "completed"
    assert batch_provider.calls == len(project.pages) - succeeded
    for page in project.pages:
        result = projects.load_page_result(page.page_id)
        assert result is not None
        assert result.status == "succeeded"


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


def test_create_run_multipass_validation(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("mpv")
    _make_notebook(corpus, "nb", clock=clock, ids=ids)
    coord = BatchOcrCoordinator(corpus, clock=clock, ids=ids)
    selected = list_candidates(corpus, clock=clock, ids=ids)
    with pytest.raises(ValidationError, match="at least two"):
        coord.create_run(
            selected,
            settings=OCRSettings(
                model_name="a", text_model_name="text-rank", cleanup_model_name="text-rank"
            ),
            mode="multipass",
            vision_model_names=["only-one"],
        )
    with pytest.raises(ValidationError, match="text/cleanup"):
        coord.create_run(
            selected,
            settings=OCRSettings(model_name="a"),
            mode="multipass",
            vision_model_names=["a", "b"],
        )


def test_ocr_batch_run_multipass_round_trip(tmp_path: Path) -> None:
    from transcribe.corpus.ocr_run import OcrBatchItem, OcrBatchRun
    from transcribe.services.batch_ocr import settings_fingerprint

    corpus = _corpus(tmp_path)
    settings = OCRSettings(
        model_name="vision-a",
        text_model_name="text-rank",
        cleanup_model_name="text-rank",
    )
    fp = settings_fingerprint(
        settings,
        force=True,
        mode="multipass",
        vision_model_names=["vision-a", "vision-b"],
        multipass_cleanup_enabled=True,
    )
    run = OcrBatchRun(
        ocr_run_id="r-mp",
        created_at="t",
        updated_at="t",
        status="pending",
        force=True,
        settings=settings.as_dict(),
        settings_fingerprint=fp,
        mode="multipass",
        vision_model_names=["vision-a", "vision-b"],
        multipass_cleanup_enabled=True,
        items=[
            OcrBatchItem(notebook_id="a", state="pending", pass_id="pass-1"),
        ],
    )
    store = OcrBatchRunStore(corpus)
    store.save(run)
    loaded = store.load("r-mp")
    assert loaded.mode == "multipass"
    assert loaded.vision_model_names == ["vision-a", "vision-b"]
    assert loaded.multipass_cleanup_enabled is True
    assert loaded.items[0].pass_id == "pass-1"
    assert loaded.settings_fingerprint == fp
    legacy = {
        "format": "transcribe.ocr-batch-run",
        "schema_version": 1,
        "ocr_run_id": "legacy",
        "created_at": "t",
        "updated_at": "t",
        "status": "pending",
        "force": False,
        "settings": {"model_name": "x"},
        "settings_fingerprint": "abc",
        "items": [{"notebook_id": "n1", "state": "pending"}],
    }
    from transcribe.persistence.atomic import write_json_atomic

    write_json_atomic(corpus.ocr_run_path("legacy"), legacy)
    back = store.load("legacy")
    assert back.mode == "single"
    assert back.vision_model_names == []


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
