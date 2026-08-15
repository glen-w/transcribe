"""Project-scoped async analysis batch coordination (mirrors OCR JobCoordinator)."""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from transcribe.analysis.plan import (
    AnalysisRunPlan,
    PlanHashMismatchError,
    build_analysis_run_plan,
    run_record_payload,
    verify_plan_hash,
)
from transcribe.analysis.runner import AnalysisRunner
from transcribe.errors import JobConflictError
from transcribe.persistence.locks import AnalysisLock
from transcribe.ports import Clock, IdGenerator, SystemClock, UuidGenerator, to_iso
from transcribe.services.project import ProjectService

_log = logging.getLogger(__name__)


@dataclass
class AnalysisProgress:
    run_id: str
    status: str  # running|completed|cancelled|failed|idle
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    current_module_id: str = ""
    message: str = ""
    cancel_requested: bool = False
    module_outcomes: dict[str, str] = field(default_factory=dict)
    error: str | None = None


@dataclass
class AnalysisRunState:
    progress: AnalysisProgress
    plan: AnalysisRunPlan | None = None
    thread: threading.Thread | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    results: dict[str, dict[str, Any]] = field(default_factory=dict)


def _snapshot_progress(progress: AnalysisProgress) -> AnalysisProgress:
    return replace(
        progress,
        module_outcomes=dict(progress.module_outcomes),
    )


def _default_progress_log(progress: AnalysisProgress) -> None:
    current = progress.current_module_id or ""
    current_bit = f" current={current}" if current else ""
    print(
        f"[transcribe:analysis] [{progress.status}] "
        f"done={progress.completed}/{progress.total} "
        f"failed={progress.failed} skipped={progress.skipped}"
        f"{current_bit}"
        f"{f' — {progress.message}' if progress.message else ''}",
        file=sys.stderr,
        flush=True,
    )


class AnalysisCoordinator:
    """One in-process analysis batch per project; survives Streamlit reruns via cache_resource."""

    def __init__(
        self,
        project_service: ProjectService,
        *,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.projects = project_service
        self.paths = project_service.paths
        self.clock = clock or SystemClock()
        self.ids = ids or UuidGenerator()
        self.runner = AnalysisRunner(project_service, clock=self.clock, ids=self.ids)
        self._lock = threading.Lock()
        self._analysis_file_lock = AnalysisLock(self.paths.analysis_lock)
        self._run: AnalysisRunState | None = None

    def get_progress(self) -> AnalysisProgress:
        with self._lock:
            if self._run is None:
                return AnalysisProgress(run_id="", status="idle")
            return _snapshot_progress(self._run.progress)

    def is_running(self) -> bool:
        with self._lock:
            return bool(
                self._run is not None
                and self._run.thread is not None
                and self._run.thread.is_alive()
            )

    def get_results(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            if self._run is None:
                return {}
            return {
                mid: dict(env) if isinstance(env, dict) else env
                for mid, env in self._run.results.items()
            }

    def cancel(self) -> None:
        with self._lock:
            if self._run is None:
                return
            self._run.cancel_event.set()
            self._run.progress.cancel_requested = True
            self._run.progress.message = "Stopping after current step…"
            snap = _snapshot_progress(self._run.progress)
        _default_progress_log(snap)

    def start(
        self,
        plan: AnalysisRunPlan,
        *,
        on_progress: Callable[[AnalysisProgress], None] | None = None,
    ) -> str:
        if not verify_plan_hash(plan):
            raise PlanHashMismatchError("analysis plan_hash does not match recomputed plan body")
        with self._lock:
            if self._run is not None and self._run.thread and self._run.thread.is_alive():
                raise JobConflictError("an analysis run is already running in this process")
            if not self._analysis_file_lock.try_acquire():
                raise JobConflictError("another process holds the analysis lock for this project")
            progress = AnalysisProgress(
                run_id=plan.run_id,
                status="running",
                total=plan.step_total(),
                message="Starting…",
            )
            state = AnalysisRunState(progress=progress, plan=plan)
            self._run = state
            _default_progress_log(progress)

            def runner() -> None:
                try:
                    self._execute(state, on_progress=on_progress or _default_progress_log)
                finally:
                    self._analysis_file_lock.release()

            thread = threading.Thread(
                target=runner,
                name=f"transcribe-analysis-{plan.run_id}",
                daemon=True,
            )
            state.thread = thread
            thread.start()
            return plan.run_id

    def run_blocking(
        self,
        plan: AnalysisRunPlan,
        *,
        on_progress: Callable[[AnalysisProgress], None] | None = None,
    ) -> AnalysisProgress:
        """CLI-friendly synchronous run (still uses analysis lock)."""
        if not verify_plan_hash(plan):
            raise PlanHashMismatchError("analysis plan_hash does not match recomputed plan body")
        if not self._analysis_file_lock.try_acquire():
            raise JobConflictError("another process holds the analysis lock for this project")
        progress = AnalysisProgress(
            run_id=plan.run_id,
            status="running",
            total=plan.step_total(),
        )
        state = AnalysisRunState(progress=progress, plan=plan)
        with self._lock:
            self._run = state

        def emit(p: AnalysisProgress) -> None:
            _default_progress_log(p)
            if on_progress is not None:
                on_progress(p)

        try:
            self._execute(state, on_progress=emit)
            return self.get_progress()
        finally:
            self._analysis_file_lock.release()

    def start_from_modules(
        self,
        module_ids: list[str],
        *,
        question_text: str | None = None,
        preset_label: str | None = None,
        on_progress: Callable[[AnalysisProgress], None] | None = None,
    ) -> str:
        plan = build_analysis_run_plan(
            project_service=self.projects,
            module_ids=module_ids,
            question_text=question_text,
            preset_label=preset_label,
            clock=self.clock,
            ids=self.ids,
        )
        return self.start(plan, on_progress=on_progress)

    def _update_progress(
        self,
        state: AnalysisRunState,
        *,
        on_progress: Callable[[AnalysisProgress], None] | None = None,
        **fields: Any,
    ) -> None:
        with self._lock:
            for key, value in fields.items():
                setattr(state.progress, key, value)
            snap = _snapshot_progress(state.progress)
        if on_progress:
            on_progress(snap)

    def _persist_run(
        self,
        state: AnalysisRunState,
        *,
        terminal: bool = False,
    ) -> None:
        plan = state.plan
        if plan is None:
            return
        with self._lock:
            progress = _snapshot_progress(state.progress)
        ended = to_iso(self.clock.now()) if terminal else None
        # Preserve started_at across updates.
        prior = self.runner.storage.read_run_record(plan.run_id)
        started = None
        if isinstance(prior, dict):
            started = prior.get("started_at")
        payload = run_record_payload(
            plan,
            status=progress.status,
            completed=progress.completed,
            failed=progress.failed,
            skipped=progress.skipped,
            current_module_id=progress.current_module_id or None,
            message=progress.message,
            started_at=started or plan.created_at,
            ended_at=ended,
            module_outcomes=progress.module_outcomes,
        )
        self.runner.storage.write_run_record(payload)

    def _execute(
        self,
        state: AnalysisRunState,
        *,
        on_progress: Callable[[AnalysisProgress], None] | None = None,
    ) -> None:
        plan = state.plan
        assert plan is not None
        step_total = plan.step_total()
        self._update_progress(
            state,
            on_progress=on_progress,
            status="running",
            total=step_total,
            message="Running analysis…",
        )
        self._persist_run(state, terminal=False)

        completed = failed = skipped = 0
        outcomes: dict[str, str] = {}

        def on_started(mid: str, *, index: int, total: int) -> None:
            self._update_progress(
                state,
                on_progress=on_progress,
                current_module_id=mid,
                message=f"Running {mid} ({index}/{total})…",
            )
            self._persist_run(state, terminal=False)

        def on_finished(mid: str, env: dict[str, Any]) -> None:
            nonlocal completed, failed, skipped
            outcome = str(env.get("outcome") or "failed")
            outcomes[mid] = outcome
            if outcome == "failed":
                failed += 1
            elif outcome in {
                "skipped_not_applicable",
                "unavailable_dependency",
                "insufficient_data",
            }:
                # Count as completed terminal for progress; "skipped" tallies soft skips.
                if env.get("capability_reason") in {
                    "unavailable_model",
                    "unavailable_extra",
                }:
                    skipped += 1
                else:
                    completed += 1
            else:
                completed += 1
            with self._lock:
                state.results[mid] = env
                state.progress.module_outcomes = dict(outcomes)
            self._update_progress(
                state,
                on_progress=on_progress,
                completed=completed,
                failed=failed,
                skipped=skipped,
                current_module_id=mid,
                message=f"{mid}: {outcome}",
                module_outcomes=dict(outcomes),
            )
            self._persist_run(state, terminal=False)

        try:
            if plan.module_ids:
                results = self.runner.run_batch_from_plan(
                    plan,
                    cancel_event=state.cancel_event,
                    on_module_started=on_started,
                    on_module_finished=on_finished,
                )
                with self._lock:
                    state.results.update(results)
            if not state.cancel_event.is_set() and plan.detector_ids:
                self._run_detectors(
                    state,
                    completed=completed,
                    failed=failed,
                    skipped=skipped,
                    outcomes=outcomes,
                    on_progress=on_progress,
                )
                with self._lock:
                    completed = state.progress.completed
                    failed = state.progress.failed
                    skipped = state.progress.skipped
            if state.cancel_event.is_set():
                status = "cancelled"
                message = "Cancelled"
            else:
                status = "completed"
                message = "Analysis completed"
            self._update_progress(
                state,
                on_progress=on_progress,
                status=status,
                message=message,
            )
            self._persist_run(state, terminal=True)
        except Exception as exc:  # noqa: BLE001
            _log.exception("analysis run failed: %s", plan.run_id)
            self._update_progress(
                state,
                on_progress=on_progress,
                status="failed",
                message=str(exc),
                error=str(exc),
            )
            self._persist_run(state, terminal=True)

    def _run_detectors(
        self,
        state: AnalysisRunState,
        *,
        completed: int,
        failed: int,
        skipped: int,
        outcomes: dict[str, str],
        on_progress: Callable[[AnalysisProgress], None] | None = None,
    ) -> None:
        plan = state.plan
        assert plan is not None
        from transcribe.detection.api import DetectionService

        text_ctx = plan.build_llm_context()
        svc = DetectionService(self.projects, text_ctx=text_ctx)
        module_count = len(plan.module_ids)
        total = plan.step_total()
        for offset, detector_id in enumerate(plan.detector_ids):
            if state.cancel_event.is_set():
                break
            index = module_count + offset + 1
            self._update_progress(
                state,
                on_progress=on_progress,
                current_module_id=detector_id,
                message=f"Detecting {detector_id} ({index}/{total})…",
                completed=completed,
                failed=failed,
                skipped=skipped,
                module_outcomes=dict(outcomes),
            )
            self._persist_run(state, terminal=False)
            try:
                env = svc.run_detector(
                    detector_id,
                    force=False,
                    cancel_check=state.cancel_event.is_set,
                )
            except Exception as exc:  # noqa: BLE001
                _log.exception("detector %s failed", detector_id)
                env = {
                    "outcome": "failed",
                    "capability": "error",
                    "error": str(exc),
                }
            outcome = str(env.get("outcome") or "failed")
            if state.cancel_event.is_set() and outcome not in {
                "success",
                "skipped_not_applicable",
                "unavailable_dependency",
                "insufficient_data",
            }:
                outcome = "cancelled"
                env = {**env, "outcome": outcome}
            outcomes[detector_id] = outcome
            if outcome == "failed":
                failed += 1
            elif outcome == "cancelled":
                skipped += 1
            else:
                completed += 1
            with self._lock:
                state.results[detector_id] = env
                state.progress.module_outcomes = dict(outcomes)
            self._update_progress(
                state,
                on_progress=on_progress,
                completed=completed,
                failed=failed,
                skipped=skipped,
                current_module_id=detector_id,
                message=f"{detector_id}: {outcome}",
                module_outcomes=dict(outcomes),
            )
            self._persist_run(state, terminal=False)


def build_analysis_coordinator(
    project_root: str,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
) -> tuple[Any, ProjectService, AnalysisCoordinator]:
    """UI helper: paths + ProjectService + AnalysisCoordinator for a project root."""
    from pathlib import Path

    from transcribe.services.project import open_project_paths

    paths = open_project_paths(Path(project_root))
    clock = clock or SystemClock()
    ids = ids or UuidGenerator()
    projects = ProjectService(paths, clock=clock, ids=ids)
    coord = AnalysisCoordinator(projects, clock=clock, ids=ids)
    return paths, projects, coord
