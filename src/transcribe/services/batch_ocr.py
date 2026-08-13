"""Sequential multi-notebook OCR using per-notebook JobCoordinator."""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from transcribe.corpus.index import CorpusIndexStore
from transcribe.corpus.import_run import ImportRunStore, committed_notebook_ids
from transcribe.corpus.ocr_run import (
    OcrBatchItem,
    OcrBatchRun,
    OcrBatchRunStore,
    finalize_ocr_batch_status,
)
from transcribe.corpus.paths import CorpusPaths
from transcribe.domain.fingerprint import canonical_json_bytes, sha256_bytes
from transcribe.domain.models import OCRSettings
from transcribe.errors import CorpusError, JobConflictError, TranscribeError, ValidationError
from transcribe.ports import Clock, IdGenerator, SystemClock, UuidGenerator, to_iso
from transcribe.providers.base import VisionOCRProvider
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.archive import discover_project_roots
from transcribe.services.job import JobCoordinator, JobProgress, build_coordinator
from transcribe.services.project import ProjectService, open_project_paths

_log = logging.getLogger(__name__)

ProviderFactory = Callable[[str], VisionOCRProvider]


@dataclass
class BatchCandidate:
    notebook_id: str
    title: str
    root: Path
    managed_relpath: str
    pages_total: int
    pages_pending: int
    pages_failed: int


@dataclass
class BatchOcrProgress:
    ocr_run_id: str
    status: str  # idle|pending|running|completed|partial|failed|cancelled
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    current_item: str = ""
    current_page_ids: list[str] = field(default_factory=list)
    pages_completed: int = 0
    pages_total: int = 0
    pages_failed: int = 0
    pages_skipped: int = 0
    message: str = ""
    cancel_requested: bool = False


@dataclass
class _BatchState:
    progress: BatchOcrProgress
    run: OcrBatchRun | None = None
    thread: threading.Thread | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    inner: JobCoordinator | None = None


def _snapshot(progress: BatchOcrProgress) -> BatchOcrProgress:
    return replace(progress, current_page_ids=list(progress.current_page_ids))


def _default_progress_log(progress: BatchOcrProgress) -> None:
    item = f" item={progress.current_item}" if progress.current_item else ""
    print(
        f"[transcribe:batch-ocr] [{progress.status}] "
        f"notebooks={progress.completed}/{progress.total} "
        f"failed={progress.failed} skipped={progress.skipped}"
        f"{item}"
        f"{f' — {progress.message}' if progress.message else ''}",
        file=sys.stderr,
        flush=True,
    )


def settings_fingerprint(settings: OCRSettings, *, force: bool) -> str:
    body = {"settings": settings.as_dict(), "force": bool(force)}
    return sha256_bytes(canonical_json_bytes(body))


def page_counts(projects: ProjectService, project) -> tuple[int, int, int]:
    """Return (total, pending_or_failed, failed) page counts."""
    total = len(project.pages)
    pending = 0
    failed = 0
    for page in project.pages:
        result = projects.load_page_result(page.page_id)
        if result is None or result.status != "succeeded":
            pending += 1
        if result is not None and result.status == "failed":
            failed += 1
    return total, pending, failed


def _managed_relpath(corpus: CorpusPaths, root: Path) -> str:
    try:
        return root.resolve().relative_to(corpus.projects_dir.resolve()).as_posix()
    except ValueError:
        return root.name


def resolve_notebook_root(corpus: CorpusPaths, notebook_id: str) -> Path:
    """Resolve a notebook id via corpus index, then project-folder scan."""
    nid = notebook_id.strip()
    if not nid:
        raise ValidationError("notebook_id must be non-empty")
    store = CorpusIndexStore(corpus)
    try:
        index = store.load()
    except CorpusError:
        index = None
    if index is not None:
        for entry in index.entries:
            if entry.notebook_id == nid:
                return corpus.resolve_managed(entry.managed_relpath)
    for root in discover_project_roots(corpus.projects_dir):
        try:
            payload_id = ProjectService(
                open_project_paths(root),
                clock=SystemClock(),
                ids=UuidGenerator(),
            ).load(reconcile=False).id
        except (TranscribeError, OSError, ValueError, KeyError):
            continue
        if payload_id == nid:
            return root
    raise CorpusError(f"notebook not found: {nid}")


def resolve_notebook_ref(corpus: CorpusPaths, ref: str | Path) -> tuple[str, Path]:
    """Accept a notebook id or project root path; return (notebook_id, root)."""
    text = str(ref).strip()
    if not text:
        raise ValidationError("notebook reference must be non-empty")
    path = Path(text).expanduser()
    if path.exists() and (path / "project.json").exists():
        project = ProjectService(
            open_project_paths(path),
            clock=SystemClock(),
            ids=UuidGenerator(),
        ).load(reconcile=False)
        return project.id, path.resolve()
    root = resolve_notebook_root(corpus, text)
    project = ProjectService(
        open_project_paths(root),
        clock=SystemClock(),
        ids=UuidGenerator(),
    ).load(reconcile=False)
    return project.id, root


def list_candidates(
    corpus: CorpusPaths,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
) -> list[BatchCandidate]:
    clock = clock or SystemClock()
    ids = ids or UuidGenerator()
    out: list[BatchCandidate] = []
    for root in discover_project_roots(corpus.projects_dir):
        try:
            projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
            project = projects.load(reconcile=False)
        except (TranscribeError, OSError, ValueError, KeyError):
            continue
        total, pending, failed = page_counts(projects, project)
        out.append(
            BatchCandidate(
                notebook_id=project.id,
                title=(project.title or root.name).strip() or root.name,
                root=root,
                managed_relpath=_managed_relpath(corpus, root),
                pages_total=total,
                pages_pending=pending,
                pages_failed=failed,
            )
        )
    return out


def select_pending(candidates: list[BatchCandidate]) -> list[BatchCandidate]:
    return [c for c in candidates if c.pages_pending > 0]


def select_by_ids(
    candidates: list[BatchCandidate], notebook_ids: list[str]
) -> list[BatchCandidate]:
    wanted = [n.strip() for n in notebook_ids if n.strip()]
    by_id = {c.notebook_id: c for c in candidates}
    missing = [nid for nid in wanted if nid not in by_id]
    if missing:
        raise CorpusError(f"notebook(s) not found: {', '.join(missing)}")
    return [by_id[nid] for nid in wanted]


def select_from_import_run(
    corpus: CorpusPaths,
    import_run_id: str,
    candidates: list[BatchCandidate],
) -> list[BatchCandidate]:
    run = ImportRunStore(corpus).load(import_run_id)
    nids = committed_notebook_ids(run)
    if not nids:
        raise ValidationError(
            f"import run {import_run_id} has no committed notebooks to transcribe"
        )
    return select_by_ids(candidates, nids)


class BatchOcrCoordinator:
    """One in-process batch OCR job for the workspace; sequential per notebook."""

    def __init__(
        self,
        corpus: CorpusPaths,
        *,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
        provider: VisionOCRProvider | None = None,
        provider_factory: ProviderFactory | None = None,
        archive_runtime: RuntimePaths | None = None,
    ) -> None:
        self.corpus = corpus
        self.clock = clock or SystemClock()
        self.ids = ids or UuidGenerator()
        self.provider = provider
        self.provider_factory = provider_factory
        self.archive_runtime = archive_runtime
        self.store = OcrBatchRunStore(corpus)
        self._lock = threading.Lock()
        self._state: _BatchState | None = None

    def get_progress(self) -> BatchOcrProgress:
        with self._lock:
            if self._state is None:
                return BatchOcrProgress(ocr_run_id="", status="idle")
            return _snapshot(self._state.progress)

    def is_running(self) -> bool:
        with self._lock:
            if self._state is None:
                return False
            thread = self._state.thread
            return bool(thread is not None and thread.is_alive())

    def request_cancel(self) -> None:
        with self._lock:
            if self._state is None:
                return
            self._state.cancel_event.set()
            self._state.progress.cancel_requested = True
            self._state.progress.message = "Stopping after current page…"
            inner = self._state.inner
            snap = _snapshot(self._state.progress)
        if inner is not None:
            inner.request_cancel()
        _default_progress_log(snap)

    def create_run(
        self,
        candidates: list[BatchCandidate],
        *,
        settings: OCRSettings,
        force: bool = False,
        import_run_id: str | None = None,
    ) -> OcrBatchRun:
        if not candidates:
            raise ValidationError("select at least one notebook to transcribe")
        if not (settings.model_name or "").strip():
            raise ValidationError("vision model is required")
        now = to_iso(self.clock.now())
        items = [
            OcrBatchItem(
                notebook_id=c.notebook_id,
                title=c.title,
                managed_relpath=c.managed_relpath,
                state="pending",
                pages_total=c.pages_total,
            )
            for c in candidates
        ]
        run = OcrBatchRun(
            ocr_run_id=self.ids.new_id(),
            created_at=now,
            updated_at=now,
            status="pending",
            force=bool(force),
            settings=settings.as_dict(),
            settings_fingerprint=settings_fingerprint(settings, force=force),
            import_run_id=import_run_id,
            items=items,
        )
        self.store.save(run)
        return run

    def start(self, ocr_run_id: str) -> str:
        with self._lock:
            if self._state is not None and self._state.thread and self._state.thread.is_alive():
                raise JobConflictError("a batch transcription job is already running")
            run = self.store.load(ocr_run_id)
            progress = BatchOcrProgress(
                ocr_run_id=run.ocr_run_id,
                status="running",
                total=len(run.items),
                message="Starting…",
            )
            state = _BatchState(progress=progress, run=run)
            self._state = state
            _default_progress_log(progress)

            def runner() -> None:
                try:
                    self._run_batch(state)
                except Exception as exc:  # noqa: BLE001
                    _log.exception("batch OCR failed")
                    with self._lock:
                        state.progress.status = "failed"
                        state.progress.message = str(exc)

            thread = threading.Thread(
                target=runner, name=f"transcribe-batch-ocr-{ocr_run_id}", daemon=True
            )
            state.thread = thread
            thread.start()
            return ocr_run_id

    def run_blocking(self, ocr_run_id: str) -> BatchOcrProgress:
        with self._lock:
            if self._state is not None and self._state.thread and self._state.thread.is_alive():
                raise JobConflictError("a batch transcription job is already running")
            run = self.store.load(ocr_run_id)
            progress = BatchOcrProgress(
                ocr_run_id=run.ocr_run_id,
                status="running",
                total=len(run.items),
            )
            state = _BatchState(progress=progress, run=run)
            self._state = state
        self._run_batch(state)
        return self.get_progress()

    def resume(self, ocr_run_id: str, *, blocking: bool = True) -> BatchOcrProgress | str:
        run = self.store.load(ocr_run_id)
        for item in run.items:
            if item.state == "running":
                item.state = "pending"
                item.error_message = None
        run.updated_at = to_iso(self.clock.now())
        self.store.save(run)
        if blocking:
            return self.run_blocking(ocr_run_id)
        return self.start(ocr_run_id)

    def _provider_for(self, base_url: str) -> VisionOCRProvider:
        if self.provider is not None:
            return self.provider
        if self.provider_factory is not None:
            return self.provider_factory(base_url)
        from transcribe.providers.ollama import OllamaVisionProvider

        return OllamaVisionProvider(base_url)

    def _run_batch(self, state: _BatchState) -> None:
        run = self.store.load(state.run.ocr_run_id if state.run else "")
        settings = OCRSettings.from_dict(run.settings)
        provider = self._provider_for(settings.base_url)
        total = len(run.items)

        for idx, item in enumerate(run.items):
            if state.cancel_event.is_set():
                if item.state == "pending":
                    item.state = "cancelled"
                continue
            if item.state not in {"pending", "running"}:
                continue

            label = f"{idx + 1}/{total} · {item.title or item.notebook_id}"
            item.state = "running"
            run.status = "running"
            run.updated_at = to_iso(self.clock.now())
            self.store.save(run)
            with self._lock:
                state.progress.status = "running"
                state.progress.current_item = label
                state.progress.message = f"Transcribing {label}"
                state.progress.total = total
                snap = _snapshot(state.progress)
            _default_progress_log(snap)

            try:
                root = self._root_for_item(item)
                _paths, projects, coord, _ingest = build_coordinator(
                    root,
                    clock=self.clock,
                    ids=self.ids,
                    provider=provider,
                    archive_runtime=self.archive_runtime,
                )
                project = projects.load(reconcile=True)
                if not project.pages:
                    item.state = "skipped"
                    item.pages_total = 0
                    continue
                merged = OCRSettings.from_dict(settings.as_dict())
                project = projects.save_settings(project, merged)
                coord.provider = provider
                with self._lock:
                    state.inner = coord

                def on_progress(job: JobProgress, *, _item=item, _label=label) -> None:
                    if state.cancel_event.is_set():
                        coord.request_cancel()
                    with self._lock:
                        state.progress.current_item = _label
                        state.progress.current_page_ids = list(job.current_page_ids)
                        state.progress.pages_completed = job.completed
                        state.progress.pages_failed = job.failed
                        state.progress.pages_skipped = job.skipped
                        state.progress.pages_total = job.total
                        state.progress.message = job.message or f"Transcribing {_label}"
                        state.progress.cancel_requested = state.cancel_event.is_set()

                job = coord.run_blocking(force=run.force, on_progress=on_progress)
                item.pages_total = job.total
                item.pages_completed = job.completed
                item.pages_failed = job.failed
                item.pages_skipped = job.skipped
                pages_done = job.completed + job.failed + job.skipped
                stopped_mid_notebook = (
                    job.status == "cancelled" and pages_done < job.total
                )
                if stopped_mid_notebook:
                    item.state = "cancelled"
                    item.error_message = job.message or "cancelled"
                elif job.status == "failed" and job.completed == 0 and job.skipped == 0:
                    item.state = "failed"
                    item.error_message = job.message or "failed"
                elif job.failed and job.completed == 0 and job.skipped == 0:
                    item.state = "failed"
                    item.error_message = job.message or f"{job.failed} page(s) failed"
                else:
                    item.state = "completed"
                    if job.failed:
                        item.error_message = job.message or f"{job.failed} page(s) failed"
            except (JobConflictError, TranscribeError, OSError, ValueError) as exc:
                item.state = "failed"
                item.error_message = str(exc)
            finally:
                with self._lock:
                    state.inner = None
                    done = sum(1 for i in run.items if i.state == "completed")
                    failed = sum(1 for i in run.items if i.state == "failed")
                    skipped = sum(1 for i in run.items if i.state == "skipped")
                    state.progress.completed = done
                    state.progress.failed = failed
                    state.progress.skipped = skipped

            run.updated_at = to_iso(self.clock.now())
            self.store.save(run)

        if state.cancel_event.is_set():
            for item in run.items:
                if item.state == "pending":
                    item.state = "cancelled"

        run.status = finalize_ocr_batch_status(run)
        run.updated_at = to_iso(self.clock.now())
        self.store.save(run)
        with self._lock:
            state.progress.status = run.status
            state.progress.current_item = ""
            state.progress.current_page_ids = []
            state.progress.message = f"Batch {run.status}"
            state.progress.completed = sum(1 for i in run.items if i.state == "completed")
            state.progress.failed = sum(1 for i in run.items if i.state == "failed")
            state.progress.skipped = sum(1 for i in run.items if i.state == "skipped")
            snap = _snapshot(state.progress)
        _default_progress_log(snap)

    def _root_for_item(self, item: OcrBatchItem) -> Path:
        if item.managed_relpath:
            try:
                return self.corpus.resolve_managed(item.managed_relpath)
            except ValueError:
                pass
        return resolve_notebook_root(self.corpus, item.notebook_id)


def build_batch_ocr_coordinator(
    corpus: CorpusPaths,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    provider: VisionOCRProvider | None = None,
    archive_runtime: RuntimePaths | None = None,
) -> BatchOcrCoordinator:
    return BatchOcrCoordinator(
        corpus,
        clock=clock,
        ids=ids,
        provider=provider,
        archive_runtime=archive_runtime,
    )
