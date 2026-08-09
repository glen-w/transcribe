"""OCR job coordination with fingerprint skip and cooperative cancel."""

from __future__ import annotations

import copy
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from transcribe import __version__
from transcribe.domain.fingerprint import compute_input_fingerprint, sha256_bytes, sha256_text
from transcribe.domain.models import (
    AttemptError,
    AttemptProvenance,
    OCRAttempt,
    Project,
)
from transcribe.errors import JobConflictError, ProviderError
from transcribe.ingest import IngestService
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import write_json_atomic
from transcribe.persistence.locks import JobLock
from transcribe.ports import Clock, IdGenerator, to_iso
from transcribe.preprocess import PREPROCESS_VERSION, apply_preprocess
from transcribe.prompts import render_prompt
from transcribe.providers.base import VisionOCRProvider
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.ocr_cleanup import (
    CleanupPlanConfig,
    resolve_cleanup_plan_config,
    run_ocr_cleanup,
)
from transcribe.services.project import ProjectService

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobPlan:
    """Immutable execution plan resolved once at job start."""

    job_id: str
    page_ids: tuple[str, ...]
    force: bool
    model_name: str
    model_digest: str | None
    model_identity_verified: bool
    base_url: str
    provider_id: str
    prompt_id: str
    prompt_version: str
    prompt_text: str
    prompt_sha256: str
    preprocess_profile: str
    preprocess_version: int
    generation_options: dict[str, Any]
    max_workers: int
    config_fingerprint: str
    cleanup: CleanupPlanConfig = field(default_factory=lambda: CleanupPlanConfig(
        enabled=False,
        mode="strip_leak",
        model_name="",
        model_digest="",
        prompt_id="",
        prompt_version="",
        prompt_template_sha256="",
    ))


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
    plan: JobPlan | None = None
    provider: VisionOCRProvider | None = None
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


def _snapshot_progress(progress: JobProgress) -> JobProgress:
    return replace(progress, current_page_ids=list(progress.current_page_ids))


class JobCoordinator:
    def __init__(
        self,
        paths: ProjectPaths,
        project_service: ProjectService,
        provider: VisionOCRProvider,
        *,
        clock: Clock,
        ids: IdGenerator,
        cleanup_client: Any | None = None,
        archive_runtime: RuntimePaths | None = None,
    ) -> None:
        self.paths = paths
        self.projects = project_service
        self.provider = provider
        self.clock = clock
        self.ids = ids
        self.cleanup_client = cleanup_client
        self.archive_runtime = archive_runtime
        self._lock = threading.Lock()
        self._job: JobState | None = None
        self._job_file_lock = JobLock(paths.job_lock)

    def get_progress(self) -> JobProgress:
        with self._lock:
            if self._job is None:
                return JobProgress(job_id="", status="idle")
            return _snapshot_progress(self._job.progress)

    def request_cancel(self) -> None:
        with self._lock:
            if self._job is None:
                return
            self._job.cancel_event.set()
            self._job.progress.cancel_requested = True
            self._job.progress.message = "Stopping after current page…"
            snap = _snapshot_progress(self._job.progress)
        _default_progress_log(snap)

    def _validate_cleanup_settings_or_raise(self) -> None:
        """Fail-fast cleanup config check before job start (plan freeze)."""
        project = self.projects.load(reconcile=False)
        resolve_cleanup_plan_config(project.settings, client=self.cleanup_client)

    def start(
        self,
        *,
        page_ids: list[str] | None = None,
        force: bool = False,
    ) -> str:
        self._validate_cleanup_settings_or_raise()
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
        self._validate_cleanup_settings_or_raise()
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
            return self.get_progress()
        finally:
            self._job_file_lock.release()

    def _update_progress(
        self,
        state: JobState,
        *,
        on_progress: Callable[[JobProgress], None] | None = None,
        **fields: Any,
    ) -> None:
        with self._lock:
            for key, value in fields.items():
                setattr(state.progress, key, value)
            snap = _snapshot_progress(state.progress)
        if on_progress:
            on_progress(snap)

    def _tally(self, state: JobState, outcome: str) -> None:
        with self._lock:
            if outcome == "succeeded":
                state.progress.completed += 1
            elif outcome == "failed":
                state.progress.failed += 1

    def _persist_job_record(self, state: JobState, *, terminal: bool = False) -> None:
        plan = state.plan
        if plan is None:
            return
        self.paths.jobs_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            progress = _snapshot_progress(state.progress)
        payload = {
            "format": "transcribe.job-record",
            "schema_version": 1,
            "job_id": plan.job_id,
            "config_fingerprint": plan.config_fingerprint,
            "force": plan.force,
            "model_name": plan.model_name,
            "model_digest": plan.model_digest,
            "model_identity_verified": plan.model_identity_verified,
            "base_url": plan.base_url,
            "provider_id": plan.provider_id,
            "target_page_ids": list(plan.page_ids),
            "started_at": None,
            "ended_at": to_iso(self.clock.now()) if terminal else None,
            "status": progress.status,
            "total": progress.total,
            "completed": progress.completed,
            "failed": progress.failed,
            "skipped": progress.skipped,
            "message": progress.message,
        }
        # Preserve started_at across updates when file exists
        path = self.paths.jobs_dir / f"{plan.job_id}.json"
        if path.exists():
            try:
                from transcribe.persistence.atomic import read_json

                prior = read_json(path)
                if isinstance(prior, dict) and prior.get("started_at"):
                    payload["started_at"] = prior["started_at"]
            except Exception:
                payload["started_at"] = to_iso(self.clock.now())
        else:
            payload["started_at"] = to_iso(self.clock.now())
        write_json_atomic(path, payload)

    def _build_plan(
        self,
        project: Project,
        *,
        job_id: str,
        page_ids: list[str] | None,
        force: bool,
        provider: VisionOCRProvider,
    ) -> JobPlan:
        settings = project.settings
        if not settings.model_name:
            raise ProviderError("No model selected", code="model_missing")
        targets = tuple(page_ids or [p.page_id for p in project.pages])
        prompt_id, prompt_version, prompt_text = render_prompt(
            prompt_id=settings.prompt_id,
            language=settings.language,
            custom_prompt=settings.custom_prompt,
        )
        prompt_sha = sha256_text(prompt_text)
        digest: str | None = None
        verified = False
        resolve = getattr(provider, "resolve_model_identity", None)
        if callable(resolve):
            digest, verified = resolve(settings.model_name)
        gen_opts = copy.deepcopy(settings.generation_options.as_dict())
        provider_id = getattr(provider, "provider_id", "unknown")
        base_url = settings.base_url
        preprocess_profile = settings.preprocess_profile or "none"
        max_workers = max(1, min(2, int(settings.max_workers or 1)))
        cleanup = resolve_cleanup_plan_config(settings, client=self.cleanup_client)
        config_fp, _ = compute_input_fingerprint(
            provider=provider_id,
            model_name=settings.model_name,
            model_digest=digest,
            model_identity_verified=verified,
            input_sha256="",
            prompt_sha256=prompt_sha,
            preprocess_profile=preprocess_profile,
            preprocess_version=PREPROCESS_VERSION,
            generation_options=gen_opts,
            cleanup=cleanup.fingerprint_dict(),
        )
        return JobPlan(
            job_id=job_id,
            page_ids=targets,
            force=force,
            model_name=settings.model_name,
            model_digest=digest,
            model_identity_verified=bool(verified),
            base_url=base_url,
            provider_id=provider_id,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            prompt_text=prompt_text,
            prompt_sha256=prompt_sha,
            preprocess_profile=preprocess_profile,
            preprocess_version=PREPROCESS_VERSION,
            generation_options=gen_opts,
            max_workers=max_workers,
            config_fingerprint=config_fp,
            cleanup=cleanup,
        )

    def _seal_provider(
        self, plan: JobPlan, start_provider: VisionOCRProvider
    ) -> VisionOCRProvider:
        """Freeze a provider instance for this job from the plan + start-time provider."""
        current_url = getattr(start_provider, "base_url", None)
        if current_url == plan.base_url:
            return start_provider
        from transcribe.providers.ollama import OllamaVisionProvider

        if plan.provider_id == "ollama" or isinstance(
            start_provider, OllamaVisionProvider
        ):
            return OllamaVisionProvider(plan.base_url)
        return start_provider

    def _run_job(
        self,
        state: JobState,
        *,
        page_ids: list[str] | None,
        force: bool,
        on_progress: Callable[[JobProgress], None] | None = None,
    ) -> None:
        project = self.projects.load(reconcile=False)
        # Capture provider reference at job start; later UI swaps of self.provider are ignored.
        start_provider = self.provider
        plan = self._build_plan(
            project,
            job_id=state.progress.job_id,
            page_ids=page_ids,
            force=force,
            provider=start_provider,
        )
        sealed_provider = self._seal_provider(plan, start_provider)
        state.plan = plan
        state.provider = sealed_provider
        self._persist_job_record(state, terminal=False)

        work: list[str] = []
        skipped = 0
        for page_id in plan.page_ids:
            if not force and self._should_skip(project, page_id, plan):
                skipped += 1
                continue
            work.append(page_id)

        self._update_progress(
            state,
            on_progress=on_progress,
            total=len(work),
            skipped=skipped,
            message=f"{len(work)} page(s) to process ({skipped} skipped)",
        )

        if not work:
            self._update_progress(
                state,
                on_progress=on_progress,
                status="completed",
                message="Nothing to do",
            )
            self._persist_job_record(state, terminal=True)
            return

        def process_one(page_id: str) -> str:
            if state.cancel_event.is_set():
                return "cancelled"
            return self._transcribe_page(project, page_id, plan, sealed_provider)

        try:
            if plan.max_workers == 1:
                for page_id in work:
                    if state.cancel_event.is_set():
                        break
                    self._update_progress(
                        state,
                        on_progress=on_progress,
                        current_page_ids=[page_id],
                        message=(
                            f"Waiting on Ollama for page {page_id[:8]}… "
                            "(first page can take several minutes if the model must load)"
                        ),
                    )
                    outcome = process_one(page_id)
                    self._tally(state, outcome)
                    detail = ""
                    if outcome == "failed":
                        result = self.projects.load_page_result(page_id)
                        attempt = result.active_attempt() if result else None
                        if attempt and attempt.error:
                            detail = f": {attempt.error.message}"
                    with self._lock:
                        done = state.progress.completed + state.progress.failed
                        total = state.progress.total
                    self._update_progress(
                        state,
                        on_progress=on_progress,
                        message=f"Page {page_id[:8]} {outcome} ({done}/{total}){detail}",
                    )
            else:
                with ThreadPoolExecutor(max_workers=plan.max_workers) as pool:
                    futures = {}
                    for page_id in work:
                        if state.cancel_event.is_set():
                            break
                        futures[pool.submit(process_one, page_id)] = page_id
                    self._update_progress(
                        state,
                        on_progress=on_progress,
                        current_page_ids=list(futures.values()),
                        message=(
                            f"Waiting on Ollama for {len(futures)} page(s)… "
                            "(model load / first page can take several minutes)"
                        ),
                    )
                    for fut in as_completed(futures):
                        outcome = fut.result()
                        self._tally(state, outcome)
                        with self._lock:
                            snap = _snapshot_progress(state.progress)
                        if on_progress:
                            on_progress(snap)
            if state.cancel_event.is_set():
                self._update_progress(
                    state,
                    on_progress=on_progress,
                    status="cancelled",
                    message="Stopped after current page",
                    current_page_ids=[],
                )
            else:
                self._update_progress(
                    state,
                    on_progress=on_progress,
                    status="completed",
                    message="Done",
                    current_page_ids=[],
                )
            self._best_effort_fill_page_dates()
            self._persist_job_record(state, terminal=True)
        except Exception as exc:  # noqa: BLE001
            self._update_progress(
                state,
                on_progress=on_progress,
                status="failed",
                message=str(exc),
                current_page_ids=[],
            )
            self._persist_job_record(state, terminal=True)

    def _best_effort_fill_page_dates(self) -> None:
        try:
            changed = self.projects.fill_page_dates_ordered()
            if changed:
                self._bump_archive_if_configured()
        except Exception:  # noqa: BLE001
            _log.exception("post-job page date fill failed")

    def _bump_archive_if_configured(self) -> None:
        if self.archive_runtime is None:
            return
        from transcribe.services.archive import bump_archive_generation

        bump_archive_generation(self.archive_runtime)

    def _best_effort_suggest_page_date(self, page_id: str) -> None:
        try:
            if self.projects.suggest_page_date(page_id):
                self._bump_archive_if_configured()
        except Exception:  # noqa: BLE001
            _log.exception("page date suggestion failed for %s", page_id)

    def _should_skip(self, project: Project, page_id: str, plan: JobPlan) -> bool:
        # Unverified model identity is non-cacheable for skip purposes.
        if not plan.model_identity_verified:
            return False
        result = self.projects.load_page_result(page_id)
        if result is None:
            return False
        attempt = result.active_attempt()
        if attempt is None or attempt.status != "succeeded":
            return False
        current = self._compute_fingerprint(project, page_id, plan)
        return current[0] == attempt.input_fingerprint

    def _compute_fingerprint(
        self, project: Project, page_id: str, plan: JobPlan
    ) -> tuple[str, dict[str, Any], bytes]:
        page = next(p for p in project.pages if p.page_id == page_id)
        render = project.renders[page.active_render_id]
        image_path = self.paths.resolve_contained(render.image_relpath)
        image_bytes = image_path.read_bytes()
        processed = apply_preprocess(image_bytes, plan.preprocess_profile)
        input_sha = sha256_bytes(processed)
        fp, payload = compute_input_fingerprint(
            provider=plan.provider_id,
            model_name=plan.model_name,
            model_digest=plan.model_digest,
            model_identity_verified=plan.model_identity_verified,
            input_sha256=input_sha,
            prompt_sha256=plan.prompt_sha256,
            preprocess_profile=plan.preprocess_profile,
            preprocess_version=plan.preprocess_version,
            generation_options=plan.generation_options,
            cleanup=plan.cleanup.fingerprint_dict(),
        )
        return fp, payload, processed

    def _transcribe_page(
        self,
        project: Project,
        page_id: str,
        plan: JobPlan,
        provider: VisionOCRProvider,
    ) -> str:
        page = next(p for p in project.pages if p.page_id == page_id)
        fingerprint, fp_payload, image_bytes = self._compute_fingerprint(
            project, page_id, plan
        )

        attempt_id = self.ids.new_id()
        started = to_iso(self.clock.now())
        running = OCRAttempt(
            attempt_id=attempt_id,
            status="running",
            input_fingerprint=fingerprint,
            fingerprint_payload=fp_payload,
            raw_text=None,
            provenance=AttemptProvenance(
                model_name=plan.model_name,
                model_digest=plan.model_digest,
                model_identity_verified=plan.model_identity_verified,
                prompt_id=plan.prompt_id,
                prompt_version=plan.prompt_version,
                prompt_sha256=plan.prompt_sha256,
                prompt_text=plan.prompt_text,
                input_sha256=sha256_bytes(image_bytes),
                preprocess_profile=plan.preprocess_profile,
                preprocess_version=plan.preprocess_version,
                generation_options=dict(plan.generation_options),
                application_version=__version__,
                ollama_host=plan.base_url,
                request_id=attempt_id,
                render_id=page.active_render_id,
            ),
            provider_metadata={},
            started_at=started,
            cleanup=None,
        )
        self.projects.record_generation(page_id, running)

        try:
            result = provider.transcribe_image(
                model=plan.model_name,
                prompt=plan.prompt_text,
                image_bytes=image_bytes,
                options=dict(plan.generation_options),
            )
            if running.provenance:
                running.provenance.model_digest = result.model_digest
                running.provenance.model_identity_verified = result.model_identity_verified

            vision_text = result.text
            final_text, cleanup_record = run_ocr_cleanup(
                vision_text=vision_text,
                plan=plan.cleanup,
                base_url=plan.base_url,
                client=self.cleanup_client,
            )

            # Atomic success write: raw_text + cleanup together; never persist
            # cleaned text without a complete cleanup record.
            running.raw_text = final_text
            running.cleanup = cleanup_record
            running.provider_metadata = result.provider_metadata
            running.status = "succeeded"
            running.completed_at = to_iso(self.clock.now())
            if (
                result.model_digest != plan.model_digest
                or result.model_identity_verified != plan.model_identity_verified
            ):
                fp2, payload2 = compute_input_fingerprint(
                    provider=plan.provider_id,
                    model_name=plan.model_name,
                    model_digest=result.model_digest,
                    model_identity_verified=result.model_identity_verified,
                    input_sha256=sha256_bytes(image_bytes),
                    prompt_sha256=plan.prompt_sha256,
                    preprocess_profile=plan.preprocess_profile,
                    preprocess_version=plan.preprocess_version,
                    generation_options=plan.generation_options,
                    cleanup=plan.cleanup.fingerprint_dict(),
                )
                running.input_fingerprint = fp2
                running.fingerprint_payload = payload2
            self.projects.record_generation(page_id, running)
            self._best_effort_suggest_page_date(page_id)
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
    archive_runtime: RuntimePaths | None = None,
) -> tuple[ProjectPaths, ProjectService, JobCoordinator, IngestService]:
    from pathlib import Path

    from transcribe.providers.ollama import OllamaVisionProvider
    from transcribe.services.project import open_project_paths

    paths = open_project_paths(Path(root))
    projects = ProjectService(paths, clock=clock, ids=ids)
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
    coord = JobCoordinator(
        paths,
        projects,
        prov,
        clock=clock,
        ids=ids,
        archive_runtime=archive_runtime,
    )
    return paths, projects, coord, ingest
