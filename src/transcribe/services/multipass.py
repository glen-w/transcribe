"""Multi-model OCR pass orchestration with rank + composite."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from transcribe import __version__
from transcribe.domain.models import (
    AttemptProvenance,
    DEFAULT_PREFER_MODE,
    OCRAttempt,
    PREFER_MODES,
)
from transcribe.errors import JobConflictError, TranscribeError
from transcribe.persistence.atomic import write_json_atomic
from transcribe.persistence.locks import JobLock
from transcribe.ports import Clock, IdGenerator, to_iso
from transcribe.services.job import JobCoordinator
from transcribe.services.ocr_compare import run_composite, run_rank
from transcribe.services.ocr_preference_stats import append_preference_event
from transcribe.services.project import ProjectService

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MultiPassPlan:
    pass_id: str
    page_ids: tuple[str, ...]
    model_names: tuple[str, ...]
    force: bool
    auto_activate_composite: bool
    prefer_mode: str
    ranker_model_name: str
    base_url: str
    model_digests: dict[str, str | None] = field(default_factory=dict)
    model_verified: dict[str, bool] = field(default_factory=dict)
    cleanup_enabled: bool = False


@dataclass
class MultiPassProgress:
    pass_id: str
    status: str  # running|completed|cancelled|failed|idle
    phase: str = ""
    model_index: int = 0
    model_total: int = 0
    message: str = ""
    pages_ranked: int = 0
    pages_composite: int = 0
    cancel_requested: bool = False


class MultiPassCoordinator:
    def __init__(
        self,
        *,
        jobs: JobCoordinator,
        projects: ProjectService,
        clock: Clock,
        ids: IdGenerator,
        text_client: Any | None = None,
    ) -> None:
        self.jobs = jobs
        self.projects = projects
        self.clock = clock
        self.ids = ids
        self.text_client = text_client
        self._job_lock = JobLock(jobs.paths.job_lock)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._progress: MultiPassProgress | None = None
        self._cancel = threading.Event()

    def get_progress(self) -> MultiPassProgress:
        with self._lock:
            if self._progress is None:
                return MultiPassProgress(pass_id="", status="idle")
            return replace(self._progress)

    def is_running(self) -> bool:
        return self.get_progress().status == "running"

    def request_cancel(self) -> None:
        self._cancel.set()
        self.jobs.request_cancel()
        with self._lock:
            if self._progress is None:
                return
            self._progress.cancel_requested = True
            self._progress.message = "Stopping after current page…"

    def start(
        self,
        *,
        model_names: list[str],
        page_ids: list[str] | None = None,
        force: bool = False,
        auto_activate_composite: bool | None = None,
        cleanup_enabled: bool = False,
    ) -> str:
        """Background multipass (UI). Holds the project OCR job lock until done."""
        models = [m.strip() for m in model_names if m and str(m).strip()]
        if len(models) < 2:
            raise TranscribeError("multipass requires at least two vision models")
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise JobConflictError(
                    "a transcription job is already running in this process"
                )
            if self.jobs.is_running():
                raise JobConflictError(
                    "a transcription job is already running in this process"
                )
            if not self._job_lock.try_acquire():
                raise JobConflictError(
                    "another process holds the OCR job lock for this project"
                )
            self._cancel.clear()
            pass_id = self.ids.new_id()
            progress = MultiPassProgress(
                pass_id=pass_id, status="running", message="Starting…"
            )
            self._progress = progress

            def runner() -> None:
                try:
                    self._run(
                        models=models,
                        page_ids=page_ids,
                        force=force,
                        auto_activate_composite=auto_activate_composite,
                        on_progress=None,
                        pass_id=pass_id,
                        cleanup_enabled=cleanup_enabled,
                    )
                finally:
                    self._job_lock.release()

            thread = threading.Thread(
                target=runner, name=f"transcribe-multipass-{pass_id}", daemon=True
            )
            self._thread = thread
        thread.start()
        return pass_id

    def run_blocking(
        self,
        *,
        model_names: list[str],
        page_ids: list[str] | None = None,
        force: bool = False,
        auto_activate_composite: bool | None = None,
        on_progress: Callable[[MultiPassProgress], None] | None = None,
        cleanup_enabled: bool = False,
    ) -> MultiPassProgress:
        models = [m.strip() for m in model_names if m and str(m).strip()]
        if len(models) < 2:
            raise TranscribeError("multipass requires at least two vision models")
        self._cancel.clear()
        if not self._job_lock.try_acquire():
            raise JobConflictError(
                "another process holds the OCR job lock for this project"
            )
        try:
            return self._run(
                models=models,
                page_ids=page_ids,
                force=force,
                auto_activate_composite=auto_activate_composite,
                on_progress=on_progress,
                cleanup_enabled=cleanup_enabled,
            )
        finally:
            self._job_lock.release()

    def resume_blocking(
        self,
        pass_id: str,
        *,
        on_progress: Callable[[MultiPassProgress], None] | None = None,
    ) -> MultiPassProgress:
        """Resume an incomplete multipass job from its on-disk record."""
        payload = self._load_job_record(pass_id)
        if payload is None:
            raise TranscribeError(f"no multipass job record for {pass_id}")
        status = str(payload.get("status") or "")
        if status == "completed":
            raise TranscribeError(f"multipass {pass_id} already completed")
        models = [str(m) for m in (payload.get("model_names") or [])]
        if len(models) < 2:
            raise TranscribeError("multipass job record missing models")
        page_ids = [str(p) for p in (payload.get("page_ids") or [])] or None
        start_idx = int(payload.get("model_index") or 0)  # 1-based completed count
        phase = str(payload.get("phase") or "vision")
        cleanup_enabled = bool(payload.get("cleanup_enabled", False))
        self._cancel.clear()
        if not self._job_lock.try_acquire():
            raise JobConflictError(
                "another process holds the OCR job lock for this project"
            )
        try:
            return self._run(
                models=models,
                page_ids=page_ids,
                force=bool(payload.get("force")),
                auto_activate_composite=bool(payload.get("auto_activate_composite", True)),
                on_progress=on_progress,
                pass_id=pass_id,
                start_model_index=start_idx if phase == "vision" else len(models),
                prefer_mode_override=str(payload.get("prefer_mode") or "") or None,
                ranker_override=str(payload.get("ranker_model_name") or "") or None,
                cleanup_enabled=cleanup_enabled,
            )
        finally:
            self._job_lock.release()

    def _load_job_record(self, pass_id: str) -> dict[str, Any] | None:
        from transcribe.persistence.atomic import read_json

        path = self.jobs.paths.jobs_dir / f"multipass_{pass_id}.json"
        if not path.exists():
            return None
        try:
            payload = read_json(path)
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _emit(
        self,
        progress: MultiPassProgress,
        on_progress: Callable[[MultiPassProgress], None] | None,
        **fields: Any,
    ) -> None:
        for key, value in fields.items():
            setattr(progress, key, value)
        with self._lock:
            self._progress = progress
        if on_progress:
            on_progress(progress)
        print(
            f"[transcribe multipass] [{progress.status}] "
            f"phase={progress.phase} {progress.message}",
            flush=True,
        )

    def _run(
        self,
        *,
        models: list[str],
        page_ids: list[str] | None,
        force: bool,
        auto_activate_composite: bool | None,
        on_progress: Callable[[MultiPassProgress], None] | None,
        pass_id: str | None = None,
        start_model_index: int = 0,
        prefer_mode_override: str | None = None,
        ranker_override: str | None = None,
        cleanup_enabled: bool = False,
    ) -> MultiPassProgress:
        project = self.projects.load(reconcile=False)
        targets = tuple(page_ids or [p.page_id for p in project.pages])
        settings = project.settings
        prefer_mode = (
            prefer_mode_override
            if prefer_mode_override in PREFER_MODES
            else (
                settings.prefer_mode
                if settings.prefer_mode in PREFER_MODES
                else DEFAULT_PREFER_MODE
            )
        )
        auto_comp = (
            settings.auto_activate_composite
            if auto_activate_composite is None
            else bool(auto_activate_composite)
        )
        ranker = (ranker_override or "").strip() or (
            (settings.cleanup_model_name or "").strip()
            or (settings.text_model_name or "").strip()
        )
        if not ranker:
            raise TranscribeError(
                "multipass rank/composite requires a text/cleanup model "
                "(set cleanup_model_name or text_model_name)"
            )
        pass_id = pass_id or self.ids.new_id()
        plan = MultiPassPlan(
            pass_id=pass_id,
            page_ids=targets,
            model_names=tuple(models),
            force=force,
            auto_activate_composite=auto_comp,
            prefer_mode=prefer_mode,
            ranker_model_name=ranker,
            base_url=settings.base_url,
            cleanup_enabled=bool(cleanup_enabled),
        )
        progress = MultiPassProgress(
            pass_id=pass_id,
            status="running",
            model_total=len(models),
            phase="vision",
            model_index=start_model_index,
            message=(
                f"Resuming multipass from model {start_model_index + 1}…"
                if start_model_index
                else "Starting multipass…"
            ),
        )
        self._persist(plan, progress, terminal=False)
        self._emit(progress, on_progress)

        # Remember prior active before vision phases
        prior_active: dict[str, str | None] = {}
        for page_id in targets:
            result = self.projects.load_page_result(page_id)
            prior_active[page_id] = result.active_attempt_id if result else None

        try:
            cancelled = False
            for idx, model_name in enumerate(models):
                if idx < start_model_index:
                    continue
                if self._cancel.is_set() or self.jobs.get_progress().status == "cancelled":
                    cancelled = True
                    break
                self._emit(
                    progress,
                    on_progress,
                    phase="vision",
                    model_index=idx + 1,
                    message=f"Vision model {model_name} ({idx + 1}/{len(models)})",
                )
                job_plan = self.jobs._build_plan(
                    project,
                    job_id=f"{pass_id}-m{idx}",
                    page_ids=list(targets),
                    force=force,
                    provider=self.jobs.provider,
                    model_name=model_name,
                    activate=False,
                    pass_id=pass_id,
                    skip_match_any_succeeded=True,
                    attempt_kind="vision",
                    cleanup_enabled=bool(plan.cleanup_enabled),
                )
                self.jobs.run_frozen_plan_blocking(
                    job_plan,
                    hold_lock=False,
                    on_progress=None,
                )
                self._persist(plan, progress, terminal=False)
                inner = self.jobs.get_progress()
                if self._cancel.is_set() or inner.status == "cancelled":
                    cancelled = True
                    break

            # Rank + composite per page (skip pages already compared for this pass).
            # Cancel does not skip rank: pages that already have ≥2 vision successes
            # still get rank/composite.
            for page_id in targets:
                existing = self.projects.load_page_result(page_id)
                has_comparison = bool(
                    existing
                    and existing.comparison
                    and existing.comparison.pass_id == plan.pass_id
                )
                has_composite = bool(
                    existing
                    and any(
                        (a.attempt_kind or "") == "composite"
                        and a.pass_id == plan.pass_id
                        and a.status == "succeeded"
                        for a in existing.attempts
                    )
                )
                if has_comparison and (has_composite or not plan.auto_activate_composite):
                    if has_comparison:
                        progress.pages_ranked += 1
                    if has_composite:
                        progress.pages_composite += 1
                    continue
                self._emit(
                    progress,
                    on_progress,
                    phase="rank_composite",
                    message=f"Rank/composite page {page_id[:8]}…",
                )
                self._rank_and_composite_page(
                    page_id=page_id,
                    plan=plan,
                    prior_active_id=prior_active.get(page_id),
                    progress=progress,
                )
                self._persist(plan, progress, terminal=False)

            terminal_status = "cancelled" if cancelled or self._cancel.is_set() else "completed"
            terminal_message = (
                f"Stopped — ranked {progress.pages_ranked}, "
                f"composite {progress.pages_composite}"
                if terminal_status == "cancelled"
                else (
                    f"Done — ranked {progress.pages_ranked}, "
                    f"composite {progress.pages_composite}"
                )
            )
            self._emit(
                progress,
                on_progress,
                status=terminal_status,
                phase="done",
                message=terminal_message,
            )
            self._persist(plan, progress, terminal=True)
            return progress
        except Exception as exc:  # noqa: BLE001
            _log.exception("multipass failed")
            self._emit(
                progress,
                on_progress,
                status="failed",
                message=str(exc),
            )
            self._persist(plan, progress, terminal=True)
            return progress

    def _rank_and_composite_page(
        self,
        *,
        page_id: str,
        plan: MultiPassPlan,
        prior_active_id: str | None,
        progress: MultiPassProgress,
    ) -> None:
        result = self.projects.load_page_result(page_id)
        if result is None:
            return
        pass_attempts = [
            a
            for a in result.attempts
            if a.pass_id == plan.pass_id
            and a.status == "succeeded"
            and (a.attempt_kind or "vision") == "vision"
        ]
        # Also include any succeeded vision attempts if pass filter yields <2
        # (e.g. skips reused older attempts without this pass_id)
        if len(pass_attempts) < 2:
            pass_attempts = [
                a
                for a in result.attempts
                if a.status == "succeeded"
                and (a.attempt_kind or "vision") == "vision"
                and (a.raw_text or "").strip()
            ]
        if len(pass_attempts) < 2:
            return

        created = to_iso(self.clock.now())
        rank = run_rank(
            attempts=pass_attempts,
            pass_id=plan.pass_id,
            model_name=plan.ranker_model_name,
            model_digest=None,
            created_at=created,
            base_url=plan.base_url,
            client=self.text_client,
        )
        if rank.comparison is not None:
            self.projects.save_comparison(page_id, rank.comparison)
            progress.pages_ranked += 1

        comp = run_composite(
            attempts=pass_attempts,
            model_name=plan.ranker_model_name,
            base_url=plan.base_url,
            client=self.text_client,
        )
        composite_attempt: OCRAttempt | None = None
        if comp.text:
            attempt_id = self.ids.new_id()
            source_ids = [a.attempt_id for a in pass_attempts]
            composite_attempt = OCRAttempt(
                attempt_id=attempt_id,
                status="succeeded",
                input_fingerprint=f"composite:{plan.pass_id}:{attempt_id}",
                fingerprint_payload={
                    "kind": "composite",
                    "pass_id": plan.pass_id,
                    "source_attempt_ids": source_ids,
                },
                raw_text=comp.text,
                provenance=AttemptProvenance(
                    model_name=plan.ranker_model_name,
                    model_digest=None,
                    model_identity_verified=False,
                    prompt_id=comp.prompt_id or "ocr_composite",
                    prompt_version=comp.prompt_version or "1",
                    prompt_sha256=comp.prompt_sha256 or "",
                    prompt_text="",
                    input_sha256="",
                    preprocess_profile="none",
                    preprocess_version=0,
                    generation_options={},
                    application_version=__version__,
                    ollama_host=plan.base_url,
                    request_id=attempt_id,
                    render_id="",
                ),
                provider_metadata={},
                started_at=created,
                completed_at=created,
                attempt_kind="composite",
                pass_id=plan.pass_id,
                source_attempt_ids=source_ids,
            )
            # Fill render_id from page
            project = self.projects.load(reconcile=False)
            page = next((p for p in project.pages if p.page_id == page_id), None)
            if page and composite_attempt.provenance:
                composite_attempt.provenance.render_id = page.active_render_id
            activate = bool(plan.auto_activate_composite)
            self.projects.record_generation(
                page_id, composite_attempt, activate=activate
            )
            progress.pages_composite += 1
            if activate:
                if plan.prefer_mode == "prefer_is_promote":
                    self.projects.set_preferred_attempt(
                        page_id,
                        attempt_id,
                        mode="prefer_is_promote",
                        record_ledger=True,
                        action_override="auto_composite",
                    )
                else:
                    append_preference_event(
                        notebook_id=project.id,
                        page_id=page_id,
                        attempt_id=attempt_id,
                        model_name=plan.ranker_model_name,
                        model_digest=None,
                        attempt_kind="composite",
                        action="auto_composite",
                        pass_id=plan.pass_id,
                        clock=self.clock,
                    )
        else:
            # Fallback activation when no prior active
            result = self.projects.load_page_result(page_id)
            if result and not prior_active_id:
                best_id = None
                if rank.comparison and rank.comparison.ranked_attempt_ids:
                    best_id = rank.comparison.ranked_attempt_ids[0]
                elif pass_attempts:
                    best_id = sorted(
                        pass_attempts, key=lambda a: a.started_at, reverse=True
                    )[0].attempt_id
                if best_id:
                    self.projects.set_active_attempt(page_id, best_id)

    def _persist(
        self,
        plan: MultiPassPlan,
        progress: MultiPassProgress,
        *,
        terminal: bool,
    ) -> None:
        path = self.jobs.paths.jobs_dir / f"multipass_{plan.pass_id}.json"
        self.jobs.paths.jobs_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "transcribe.ocr-multipass-job",
            "schema_version": 1,
            "pass_id": plan.pass_id,
            "page_ids": list(plan.page_ids),
            "model_names": list(plan.model_names),
            "force": plan.force,
            "auto_activate_composite": plan.auto_activate_composite,
            "prefer_mode": plan.prefer_mode,
            "ranker_model_name": plan.ranker_model_name,
            "base_url": plan.base_url,
            "cleanup_enabled": plan.cleanup_enabled,
            "status": progress.status,
            "phase": progress.phase,
            "model_index": progress.model_index,
            "pages_ranked": progress.pages_ranked,
            "pages_composite": progress.pages_composite,
            "message": progress.message,
            "ended_at": to_iso(self.clock.now()) if terminal else None,
        }
        write_json_atomic(path, payload)
