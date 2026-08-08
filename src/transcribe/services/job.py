"""OCR job coordination with fingerprint skip and cooperative cancel."""

from __future__ import annotations

import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from transcribe import __version__
from transcribe.domain.fingerprint import compute_input_fingerprint, sha256_bytes, sha256_text
from transcribe.domain.models import (
    AttemptError,
    AttemptProvenance,
    OCRAttempt,
    PageResult,
    Project,
)
from transcribe.errors import JobConflictError, ProviderError
from transcribe.ingest import IngestService
from transcribe.paths import ProjectPaths
from transcribe.persistence.locks import JobLock
from transcribe.ports import Clock, IdGenerator, to_iso
from transcribe.preprocess import PREPROCESS_VERSION, apply_preprocess
from transcribe.prompts import render_prompt
from transcribe.providers.base import VisionOCRProvider
from transcribe.services.project import ProjectService


@dataclass
class JobProgress:
    job_id: str
    status: str  # running|completed|cancelled|failed|idle
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    current_page_ids: list[str] = field(default_factory=list)
    message: str = ""
    cancel_requested: bool = False


@dataclass
class JobState:
    progress: JobProgress
    thread: threading.Thread | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


def _default_progress_log(progress: JobProgress) -> None:
    """Print job progress to the process terminal (CLI and Streamlit server)."""
    current = ",".join(progress.current_page_ids[:3])
    if len(progress.current_page_ids) > 3:
        current += ",…"
    current_bit = f" current={current}" if current else ""
    print(
        f"[transcribe] [{progress.status}] "
        f"done={progress.completed}/{progress.total} "
        f"failed={progress.failed} skipped={progress.skipped}"
        f"{current_bit}"
        f"{f' — {progress.message}' if progress.message else ''}",
        file=sys.stderr,
        flush=True,
    )


class JobCoordinator:
    def __init__(
        self,
        paths: ProjectPaths,
        project_service: ProjectService,
        provider: VisionOCRProvider,
        *,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self.paths = paths
        self.projects = project_service
        self.provider = provider
        self.clock = clock
        self.ids = ids
        self._lock = threading.Lock()
        self._job: JobState | None = None
        self._job_file_lock = JobLock(paths.job_lock)

    def get_progress(self) -> JobProgress:
        with self._lock:
            if self._job is None:
                return JobProgress(job_id="", status="idle")
            return self._job.progress

    def request_cancel(self) -> None:
        with self._lock:
            if self._job is None:
                return
            self._job.cancel_event.set()
            self._job.progress.cancel_requested = True
            self._job.progress.message = "Stopping after current page…"
            _default_progress_log(self._job.progress)

    def start(
        self,
        *,
        page_ids: list[str] | None = None,
        force: bool = False,
    ) -> str:
        with self._lock:
            if self._job is not None and self._job.thread and self._job.thread.is_alive():
                raise JobConflictError("a transcription job is already running in this process")
            if not self._job_file_lock.try_acquire():
                raise JobConflictError(
                    "another process holds the OCR job lock for this project"
                )
            job_id = self.ids.new_id()
            progress = JobProgress(job_id=job_id, status="running", message="Starting…")
            state = JobState(progress=progress)
            self._job = state
            _default_progress_log(progress)

            def runner() -> None:
                try:
                    self._run_job(
                        state,
                        page_ids=page_ids,
                        force=force,
                        on_progress=_default_progress_log,
                    )
                finally:
                    self._job_file_lock.release()

            thread = threading.Thread(target=runner, name=f"transcribe-job-{job_id}", daemon=True)
            state.thread = thread
            thread.start()
            return job_id

    def run_blocking(
        self,
        *,
        page_ids: list[str] | None = None,
        force: bool = False,
        on_progress: Callable[[JobProgress], None] | None = None,
    ) -> JobProgress:
        """CLI-friendly synchronous run (still uses job lock)."""
        if not self._job_file_lock.try_acquire():
            raise JobConflictError(
                "another process holds the OCR job lock for this project"
            )
        job_id = self.ids.new_id()
        progress = JobProgress(job_id=job_id, status="running")
        state = JobState(progress=progress)
        with self._lock:
            self._job = state

        def emit(p: JobProgress) -> None:
            _default_progress_log(p)
            if on_progress is not None:
                on_progress(p)

        try:
            self._run_job(state, page_ids=page_ids, force=force, on_progress=emit)
            return state.progress
        finally:
            self._job_file_lock.release()

    def _run_job(
        self,
        state: JobState,
        *,
        page_ids: list[str] | None,
        force: bool,
        on_progress: Callable[[JobProgress], None] | None = None,
    ) -> None:
        project = self.projects.load(reconcile=False)
        targets = page_ids or [p.page_id for p in project.pages]
        work: list[str] = []
        skipped = 0
        for page_id in targets:
            if not force and self._should_skip(project, page_id):
                skipped += 1
                continue
            work.append(page_id)

        state.progress.total = len(work)
        state.progress.skipped = skipped
        state.progress.message = f"{len(work)} page(s) to process ({skipped} skipped)"
        if on_progress:
            on_progress(state.progress)

        workers = max(1, min(2, int(project.settings.max_workers or 1)))
        if not work:
            state.progress.status = "completed"
            state.progress.message = "Nothing to do"
            if on_progress:
                on_progress(state.progress)
            return

        def process_one(page_id: str) -> str:
            if state.cancel_event.is_set():
                return "cancelled"
            return self._transcribe_page(project, page_id)

        try:
            if workers == 1:
                for page_id in work:
                    if state.cancel_event.is_set():
                        break
                    state.progress.current_page_ids = [page_id]
                    state.progress.message = (
                        f"Waiting on Ollama for page {page_id[:8]}… "
                        "(first page can take several minutes if the model must load)"
                    )
                    if on_progress:
                        on_progress(state.progress)
                    outcome = process_one(page_id)
                    self._tally(state, outcome)
                    detail = ""
                    if outcome == "failed":
                        result = self.projects.load_page_result(page_id)
                        attempt = result.active_attempt() if result else None
                        if attempt and attempt.error:
                            detail = f": {attempt.error.message}"
                    state.progress.message = (
                        f"Page {page_id[:8]} {outcome} "
                        f"({state.progress.completed + state.progress.failed}/"
                        f"{state.progress.total}){detail}"
                    )
                    if on_progress:
                        on_progress(state.progress)
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {}
                    for page_id in work:
                        if state.cancel_event.is_set():
                            break
                        futures[pool.submit(process_one, page_id)] = page_id
                    state.progress.current_page_ids = list(futures.values())
                    state.progress.message = (
                        f"Waiting on Ollama for {len(futures)} page(s)… "
                        "(model load / first page can take several minutes)"
                    )
                    if on_progress:
                        on_progress(state.progress)
                    for fut in as_completed(futures):
                        outcome = fut.result()
                        self._tally(state, outcome)
                        if on_progress:
                            on_progress(state.progress)
            if state.cancel_event.is_set():
                state.progress.status = "cancelled"
                state.progress.message = "Stopped after current page"
            else:
                state.progress.status = "completed"
                state.progress.message = "Done"
            state.progress.current_page_ids = []
            if on_progress:
                on_progress(state.progress)
        except Exception as exc:  # noqa: BLE001
            state.progress.status = "failed"
            state.progress.message = str(exc)
            state.progress.current_page_ids = []
            if on_progress:
                on_progress(state.progress)

    def _tally(self, state: JobState, outcome: str) -> None:
        if outcome == "succeeded":
            state.progress.completed += 1
        elif outcome == "failed":
            state.progress.failed += 1
        elif outcome == "cancelled":
            pass

    def _should_skip(self, project: Project, page_id: str) -> bool:
        result = self.projects.load_page_result(page_id)
        if result is None:
            return False
        attempt = result.active_attempt()
        if attempt is None or attempt.status != "succeeded":
            return False
        current = self._compute_fingerprint(project, page_id)
        return current[0] == attempt.input_fingerprint

    def _compute_fingerprint(
        self, project: Project, page_id: str
    ) -> tuple[str, dict[str, Any], bytes, str, str, str]:
        page = next(p for p in project.pages if p.page_id == page_id)
        render = project.renders[page.active_render_id]
        image_path = self.paths.resolve_contained(render.image_relpath)
        image_bytes = image_path.read_bytes()
        settings = project.settings
        processed = apply_preprocess(image_bytes, settings.preprocess_profile)
        input_sha = sha256_bytes(processed)
        prompt_id, prompt_version, prompt_text = render_prompt(
            prompt_id=settings.prompt_id,
            language=settings.language,
            custom_prompt=settings.custom_prompt,
        )
        prompt_sha = sha256_text(prompt_text)
        digest: str | None = None
        verified = False
        resolve = getattr(self.provider, "resolve_model_identity", None)
        if callable(resolve):
            digest, verified = resolve(settings.model_name)
        fp, payload = compute_input_fingerprint(
            provider=getattr(self.provider, "provider_id", "unknown"),
            model_name=settings.model_name,
            model_digest=digest,
            model_identity_verified=verified,
            input_sha256=input_sha,
            prompt_sha256=prompt_sha,
            preprocess_profile=settings.preprocess_profile or "none",
            preprocess_version=PREPROCESS_VERSION,
            generation_options=settings.generation_options.as_dict(),
        )
        return fp, payload, processed, prompt_id, prompt_version, prompt_text

    def _transcribe_page(self, project: Project, page_id: str) -> str:
        settings = project.settings
        if not settings.model_name:
            raise ProviderError("No model selected", code="model_missing")
        page = next(p for p in project.pages if p.page_id == page_id)
        (
            fingerprint,
            fp_payload,
            image_bytes,
            prompt_id,
            prompt_version,
            prompt_text,
        ) = self._compute_fingerprint(project, page_id)

        attempt_id = self.ids.new_id()
        started = to_iso(self.clock.now())
        digest = fp_payload.get("model_digest")
        verified = bool(fp_payload.get("model_identity_verified"))
        running = OCRAttempt(
            attempt_id=attempt_id,
            status="running",
            input_fingerprint=fingerprint,
            fingerprint_payload=fp_payload,
            raw_text=None,
            provenance=AttemptProvenance(
                model_name=settings.model_name,
                model_digest=digest if isinstance(digest, str) else None,
                model_identity_verified=verified,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
                prompt_sha256=sha256_text(prompt_text),
                prompt_text=prompt_text,
                input_sha256=sha256_bytes(image_bytes),
                preprocess_profile=settings.preprocess_profile or "none",
                preprocess_version=PREPROCESS_VERSION,
                generation_options=settings.generation_options.as_dict(),
                application_version=__version__,
                ollama_host=settings.base_url,
                request_id=attempt_id,
                render_id=page.active_render_id,
            ),
            provider_metadata={},
            started_at=started,
        )
        self.projects.record_generation(page_id, running)

        try:
            result = self.provider.transcribe_image(
                model=settings.model_name,
                prompt=prompt_text,
                image_bytes=image_bytes,
                options=settings.generation_options.as_dict(),
            )
            # Prefer provider-reported identity
            if running.provenance:
                running.provenance.model_digest = result.model_digest
                running.provenance.model_identity_verified = result.model_identity_verified
            running.raw_text = result.text
            running.provider_metadata = result.provider_metadata
            running.status = "succeeded"
            running.completed_at = to_iso(self.clock.now())
            # Recompute fingerprint with provider digest if it differs
            if result.model_digest != digest or result.model_identity_verified != verified:
                fp2, payload2 = compute_input_fingerprint(
                    provider=getattr(self.provider, "provider_id", "unknown"),
                    model_name=settings.model_name,
                    model_digest=result.model_digest,
                    model_identity_verified=result.model_identity_verified,
                    input_sha256=sha256_bytes(image_bytes),
                    prompt_sha256=sha256_text(prompt_text),
                    preprocess_profile=settings.preprocess_profile or "none",
                    preprocess_version=PREPROCESS_VERSION,
                    generation_options=settings.generation_options.as_dict(),
                )
                running.input_fingerprint = fp2
                running.fingerprint_payload = payload2
            self.projects.record_generation(page_id, running)
            return "succeeded"
        except ProviderError as exc:
            running.status = "failed"
            running.error = AttemptError(
                code=exc.code, message=str(exc), retriable=exc.retriable
            )
            running.completed_at = to_iso(self.clock.now())
            self.projects.record_generation(page_id, running)
            return "failed"
        except Exception as exc:  # noqa: BLE001
            running.status = "failed"
            running.error = AttemptError(
                code="internal", message=str(exc), retriable=False
            )
            running.completed_at = to_iso(self.clock.now())
            self.projects.record_generation(page_id, running)
            return "failed"


def build_coordinator(
    root,
    *,
    clock: Clock,
    ids: IdGenerator,
    provider: VisionOCRProvider | None = None,
) -> tuple[ProjectPaths, ProjectService, JobCoordinator, IngestService]:
    from pathlib import Path

    from transcribe.providers.ollama import OllamaVisionProvider
    from transcribe.services.project import open_project_paths

    paths = open_project_paths(Path(root))
    projects = ProjectService(paths, clock=clock, ids=ids)
    # Load settings for provider base URL if project exists
    from transcribe.runtime_paths import default_ollama_base_url

    base_url = default_ollama_base_url()
    if paths.manifest.exists():
        try:
            project = projects.load(reconcile=True)
            base_url = project.settings.base_url
        except Exception:
            pass
    prov = provider or OllamaVisionProvider(base_url)
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.cleanup_staging()
    coord = JobCoordinator(paths, projects, prov, clock=clock, ids=ids)
    return paths, projects, coord, ingest
