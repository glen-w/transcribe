"""Sequential multi-notebook OCR using per-notebook JobCoordinator / MultiPass."""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from transcribe.corpus.ocr_run import (
    OcrBatchItem,
    OcrBatchRun,
    OcrBatchRunStore,
    finalize_ocr_batch_status,
)
from transcribe.corpus.paths import CorpusPaths
from transcribe.domain.fingerprint import canonical_json_bytes, sha256_bytes
from transcribe.domain.models import OCRSettings
from transcribe.errors import (
    JobConflictError,
    TranscribeError,
    ValidationError,
)
from transcribe.ports import Clock, IdGenerator, SystemClock, UuidGenerator, to_iso
from transcribe.providers.base import VisionOCRProvider
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.batch_notebooks import (
    BatchCandidate,
    list_candidates,
    page_counts,
    resolve_notebook_ref,
    resolve_notebook_root,
    select_by_ids,
    select_from_import_run,
    select_pending,
)
from transcribe.services.job import JobCoordinator, JobProgress, build_coordinator
from transcribe.services.multipass import MultiPassCoordinator, MultiPassProgress
from transcribe.services.project import ProjectService, open_project_paths

_log = logging.getLogger(__name__)

ProviderFactory = Callable[[str], VisionOCRProvider]

__all__ = [
    "BatchCandidate",
    "BatchOcrCoordinator",
    "BatchOcrProgress",
    "build_batch_ocr_coordinator",
    "list_candidates",
    "page_counts",
    "resolve_notebook_ref",
    "resolve_notebook_root",
    "select_by_ids",
    "select_from_import_run",
    "select_pending",
    "settings_fingerprint",
]


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
    current_page_label: str = ""
    pages_completed: int = 0
    pages_total: int = 0
    pages_failed: int = 0
    pages_skipped: int = 0
    message: str = ""
    cancel_requested: bool = False
    mode: str = "single"
    phase: str = ""
    model_index: int = 0
    model_total: int = 0
    current_model: str = ""


@dataclass
class _BatchState:
    progress: BatchOcrProgress
    run: OcrBatchRun | None = None
    thread: threading.Thread | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    inner: JobCoordinator | None = None
    inner_multipass: MultiPassCoordinator | None = None


def _snapshot(progress: BatchOcrProgress) -> BatchOcrProgress:
    return replace(progress, current_page_ids=list(progress.current_page_ids))


def _default_progress_log(progress: BatchOcrProgress) -> None:
    item = f" item={progress.current_item}" if progress.current_item else ""
    page = f" page={progress.current_page_label}" if progress.current_page_label else ""
    model = f" model={progress.current_model}" if progress.current_model else ""
    phase = f" phase={progress.phase}" if progress.phase else ""
    print(
        f"[transcribe:batch-ocr] [{progress.status}] "
        f"notebooks={progress.completed}/{progress.total} "
        f"failed={progress.failed} skipped={progress.skipped}"
        f"{item}{page}{model}{phase}"
        f"{f' — {progress.message}' if progress.message else ''}",
        file=sys.stderr,
        flush=True,
    )


def settings_fingerprint(
    settings: OCRSettings,
    *,
    force: bool,
    mode: str = "single",
    vision_model_names: list[str] | None = None,
    multipass_cleanup_enabled: bool = False,
) -> str:
    body = {
        "settings": settings.as_dict(),
        "force": bool(force),
        "mode": mode,
        "vision_model_names": list(vision_model_names or []),
        "multipass_cleanup_enabled": bool(multipass_cleanup_enabled),
    }
    return sha256_bytes(canonical_json_bytes(body))


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
        text_client: Any | None = None,
    ) -> None:
        self.corpus = corpus
        self.clock = clock or SystemClock()
        self.ids = ids or UuidGenerator()
        self.provider = provider
        self.provider_factory = provider_factory
        self.archive_runtime = archive_runtime
        self.text_client = text_client
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
            multi = self._state.inner_multipass
            snap = _snapshot(self._state.progress)
        if multi is not None:
            multi.request_cancel()
        elif inner is not None:
            inner.request_cancel()
        _default_progress_log(snap)

    def create_run(
        self,
        candidates: list[BatchCandidate],
        *,
        settings: OCRSettings,
        force: bool = False,
        import_run_id: str | None = None,
        mode: str = "single",
        vision_model_names: list[str] | None = None,
        multipass_cleanup_enabled: bool = False,
    ) -> OcrBatchRun:
        if not candidates:
            raise ValidationError("select at least one notebook to transcribe")
        mode_norm = (mode or "single").strip() or "single"
        models = [m.strip() for m in (vision_model_names or []) if m and str(m).strip()]
        if mode_norm == "multipass":
            if len(models) < 2:
                raise ValidationError("multipass batch requires at least two vision models")
            text_model = (settings.cleanup_model_name or "").strip() or (
                settings.text_model_name or ""
            ).strip()
            if not text_model:
                raise ValidationError(
                    "multipass batch requires a text/cleanup model "
                    "(set cleanup_model_name or text_model_name)"
                )
            frozen = OCRSettings.from_dict(settings.as_dict())
            frozen.model_name = models[0]
        else:
            if not (settings.model_name or "").strip():
                raise ValidationError("vision model is required")
            frozen = OCRSettings.from_dict(settings.as_dict())
            models = []
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
            settings=frozen.as_dict(),
            settings_fingerprint=settings_fingerprint(
                frozen,
                force=force,
                mode=mode_norm,
                vision_model_names=models,
                multipass_cleanup_enabled=multipass_cleanup_enabled,
            ),
            import_run_id=import_run_id,
            items=items,
            mode=mode_norm,
            vision_model_names=models,
            multipass_cleanup_enabled=bool(multipass_cleanup_enabled),
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
                mode=run.mode,
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
                mode=run.mode,
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
        is_multipass = run.mode == "multipass"

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
                state.progress.mode = run.mode
                state.progress.current_item = label
                state.progress.message = (
                    f"Comparing models in {label}" if is_multipass else f"Transcribing {label}"
                )
                state.progress.total = total
                state.progress.phase = ""
                state.progress.model_index = 0
                state.progress.model_total = len(run.vision_model_names) if is_multipass else 0
                state.progress.current_model = ""
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

                if is_multipass:
                    self._run_multipass_item(
                        state=state,
                        run=run,
                        item=item,
                        label=label,
                        projects=projects,
                        coord=coord,
                    )
                else:
                    self._run_single_item(
                        state=state,
                        run=run,
                        item=item,
                        label=label,
                        coord=coord,
                    )
            except (JobConflictError, TranscribeError, OSError, ValueError) as exc:
                item.state = "failed"
                item.error_message = str(exc)
            finally:
                with self._lock:
                    state.inner = None
                    state.inner_multipass = None
                    done = sum(1 for i in run.items if i.state == "completed")
                    failed = sum(1 for i in run.items if i.state == "failed")
                    skipped = sum(1 for i in run.items if i.state == "skipped")
                    state.progress.completed = done
                    state.progress.failed = failed
                    state.progress.skipped = skipped
                    state.progress.phase = ""
                    state.progress.current_model = ""
                    state.progress.model_index = 0

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
            state.progress.current_page_label = ""
            state.progress.message = f"Batch {run.status}"
            state.progress.phase = ""
            state.progress.current_model = ""
            state.progress.model_index = 0
            state.progress.completed = sum(1 for i in run.items if i.state == "completed")
            state.progress.failed = sum(1 for i in run.items if i.state == "failed")
            state.progress.skipped = sum(1 for i in run.items if i.state == "skipped")
            snap = _snapshot(state.progress)
        _default_progress_log(snap)

    def _run_single_item(
        self,
        *,
        state: _BatchState,
        run: OcrBatchRun,
        item: OcrBatchItem,
        label: str,
        coord: JobCoordinator,
    ) -> None:
        with self._lock:
            state.inner = coord

        def on_progress(job: JobProgress, *, _item=item, _label=label) -> None:
            if state.cancel_event.is_set():
                coord.request_cancel()
            page_name = ""
            if job.current_labels:
                page_name = ", ".join(job.current_labels)
            elif job.current_page_ids:
                page_name = ", ".join(p[:8] for p in job.current_page_ids)
            with self._lock:
                state.progress.current_item = _label
                state.progress.current_page_ids = list(job.current_page_ids)
                state.progress.current_page_label = page_name
                state.progress.pages_completed = job.completed
                state.progress.pages_failed = job.failed
                state.progress.pages_skipped = job.skipped
                state.progress.pages_total = job.total
                state.progress.message = job.message or (
                    f"Transcribing {page_name} in {_label}"
                    if page_name
                    else f"Transcribing {_label}"
                )
                state.progress.cancel_requested = state.cancel_event.is_set()

        job = coord.run_blocking(force=run.force, on_progress=on_progress)
        item.pages_total = job.total
        item.pages_completed = job.completed
        item.pages_failed = job.failed
        item.pages_skipped = job.skipped
        pages_done = job.completed + job.failed + job.skipped
        stopped_mid_notebook = job.status == "cancelled" and pages_done < job.total
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

    def _run_multipass_item(
        self,
        *,
        state: _BatchState,
        run: OcrBatchRun,
        item: OcrBatchItem,
        label: str,
        projects: ProjectService,
        coord: JobCoordinator,
    ) -> None:
        multi = MultiPassCoordinator(
            jobs=coord,
            projects=projects,
            clock=self.clock,
            ids=self.ids,
            text_client=self.text_client,
        )
        with self._lock:
            state.inner = coord
            state.inner_multipass = multi

        models = list(run.vision_model_names)
        auto_activate = bool(OCRSettings.from_dict(run.settings).auto_activate_composite)

        def on_progress(mp: MultiPassProgress, *, _label=label) -> None:
            if state.cancel_event.is_set():
                multi.request_cancel()
            model_name = ""
            if mp.model_total and 0 < mp.model_index <= len(models):
                model_name = models[mp.model_index - 1]
            elif mp.model_total and mp.model_index == 0 and models:
                model_name = models[0]
            job = coord.get_progress()
            page_name = ""
            if job.current_labels:
                page_name = ", ".join(job.current_labels)
            elif job.current_page_ids:
                page_name = ", ".join(p[:8] for p in job.current_page_ids)
            with self._lock:
                state.progress.current_item = _label
                state.progress.phase = mp.phase
                state.progress.model_index = mp.model_index
                state.progress.model_total = mp.model_total
                state.progress.current_model = model_name
                state.progress.current_page_ids = list(job.current_page_ids)
                state.progress.current_page_label = page_name
                state.progress.pages_completed = job.completed
                state.progress.pages_failed = job.failed
                state.progress.pages_skipped = job.skipped
                state.progress.pages_total = job.total or mp.pages_total
                state.progress.message = mp.message or (
                    f"Compare {model_name} in {_label}" if model_name else f"Compare in {_label}"
                )
                state.progress.cancel_requested = state.cancel_event.is_set()

        resume_pass = (item.pass_id or "").strip()
        resume_payload = multi._load_job_record(resume_pass) if resume_pass else None
        can_resume = bool(
            resume_payload
            and str(resume_payload.get("status") or "") not in {"completed", "failed"}
        )

        if can_resume:
            progress = multi.resume_blocking(resume_pass, on_progress=on_progress)
        else:
            pass_id = resume_pass or self.ids.new_id()
            item.pass_id = pass_id
            self.store.save(run)
            progress = multi.run_blocking(
                model_names=models,
                force=run.force,
                auto_activate_composite=auto_activate,
                cleanup_enabled=run.multipass_cleanup_enabled,
                on_progress=on_progress,
                pass_id=pass_id,
            )

        job = coord.get_progress()
        item.pages_total = job.total or progress.pages_total
        item.pages_completed = job.completed or progress.pages_ranked
        item.pages_failed = job.failed
        item.pages_skipped = job.skipped
        if progress.status == "cancelled":
            item.state = "cancelled"
            item.error_message = progress.message or "cancelled"
        elif progress.status == "failed":
            item.state = "failed"
            item.error_message = progress.message or "failed"
        else:
            item.state = "completed"

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
    text_client: Any | None = None,
) -> BatchOcrCoordinator:
    return BatchOcrCoordinator(
        corpus,
        clock=clock,
        ids=ids,
        provider=provider,
        archive_runtime=archive_runtime,
        text_client=text_client,
    )
