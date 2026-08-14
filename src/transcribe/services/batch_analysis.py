"""Sequential multi-notebook Analyse using per-notebook AnalysisCoordinator."""

from __future__ import annotations

import hashlib
import logging
import sys
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Sequence

from transcribe.analysis.coordinator import AnalysisCoordinator, AnalysisProgress
from transcribe.analysis.parents import batch_module_order
from transcribe.analysis.plan import (
    AnalysisRunPlan,
    FrozenTextModel,
    PlanHashMismatchError,
    build_analysis_run_plan,
    config_fingerprint_for_plan,
)
from transcribe.analysis.presets import expand_with_hard_parents
from transcribe.config.models import EffectiveConfig
from transcribe.corpus.analysis_batch_run import (
    AnalysisBatchItem,
    AnalysisBatchRun,
    AnalysisBatchRunStore,
    finalize_analysis_batch_status,
)
from transcribe.corpus.paths import CorpusPaths
from transcribe.domain.fingerprint import canonical_json_bytes
from transcribe.errors import JobConflictError, TranscribeError, ValidationError
from transcribe.ports import Clock, IdGenerator, SystemClock, UuidGenerator, to_iso
from transcribe.services.batch_notebooks import (
    NotebookCandidate,
    list_candidates,
    list_candidates_light,
    pages_with_text_count,
    resolve_notebook_root,
    select_by_ids,
    select_from_import_run,
    select_needing_analysis,
)
from transcribe.services.project import ProjectService, open_project_paths

_log = logging.getLogger(__name__)

__all__ = [
    "BatchAnalysisCoordinator",
    "BatchAnalysisProgress",
    "NotebookCandidate",
    "build_batch_analysis_coordinator",
    "list_analysis_candidates",
    "list_candidates_light",
    "plan_template_hash",
    "select_by_ids",
    "select_from_import_run",
    "select_needing_analysis",
]


@dataclass
class BatchAnalysisProgress:
    analysis_batch_id: str
    status: str  # idle|pending|running|completed|partial|failed|cancelled
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    current_item: str = ""
    current_module_id: str = ""
    modules_completed: int = 0
    modules_failed: int = 0
    modules_skipped: int = 0
    modules_total: int = 0
    message: str = ""
    cancel_requested: bool = False
    error: str | None = None


@dataclass
class _BatchState:
    progress: BatchAnalysisProgress
    run: AnalysisBatchRun | None = None
    thread: threading.Thread | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    inner: AnalysisCoordinator | None = None


def _snapshot(progress: BatchAnalysisProgress) -> BatchAnalysisProgress:
    return replace(progress)


def _default_progress_log(progress: BatchAnalysisProgress) -> None:
    item = f" item={progress.current_item}" if progress.current_item else ""
    module = f" module={progress.current_module_id}" if progress.current_module_id else ""
    print(
        f"[transcribe:batch-analysis] [{progress.status}] "
        f"notebooks={progress.completed}/{progress.total} "
        f"failed={progress.failed} skipped={progress.skipped}"
        f"{item}{module}"
        f"{f' — {progress.message}' if progress.message else ''}",
        file=sys.stderr,
        flush=True,
    )


def plan_template_hash(
    *,
    module_ids: Sequence[str],
    question_text: str | None,
    effective_config: dict[str, Any] | EffectiveConfig,
    config_fingerprint: str,
    text_model: dict[str, Any] | FrozenTextModel | None,
    preset_key: str | None,
    preset_content_version: int | None,
    preset_policy_fingerprint: str | None,
) -> str:
    """Hash of template fields shared across notebooks (no project_id / run_id)."""
    cfg = (
        effective_config.as_dict()
        if isinstance(effective_config, EffectiveConfig)
        else dict(effective_config or {})
    )
    model = (
        text_model.as_dict()
        if isinstance(text_model, FrozenTextModel)
        else (dict(text_model) if text_model else None)
    )
    body = {
        "module_ids": list(module_ids),
        "question_text": question_text,
        "effective_config": cfg,
        "text_model": model,
        "config_fingerprint": config_fingerprint,
        "preset_key": preset_key,
        "preset_content_version": preset_content_version,
        "preset_policy_fingerprint": preset_policy_fingerprint,
    }
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def list_analysis_candidates(
    corpus: CorpusPaths,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
) -> list[NotebookCandidate]:
    return list_candidates(
        corpus, clock=clock, ids=ids, include_analysis=True
    )


class BatchAnalysisCoordinator:
    """One in-process bulk Analyse job for the workspace; sequential per notebook."""

    def __init__(
        self,
        corpus: CorpusPaths,
        *,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.corpus = corpus
        self.clock = clock or SystemClock()
        self.ids = ids or UuidGenerator()
        self.store = AnalysisBatchRunStore(corpus)
        self._lock = threading.Lock()
        self._state: _BatchState | None = None

    def get_progress(self) -> BatchAnalysisProgress:
        with self._lock:
            if self._state is None:
                return BatchAnalysisProgress(analysis_batch_id="", status="idle")
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
            self._state.progress.message = "Stopping after current notebook…"
            inner = self._state.inner
            snap = _snapshot(self._state.progress)
        if inner is not None:
            inner.cancel()
        _default_progress_log(snap)

    def create_run(
        self,
        candidates: list[NotebookCandidate],
        *,
        module_ids: Sequence[str],
        question_text: str | None = None,
        preset_label: str | None = None,
        preset_key: str | None = None,
        preset_content_version: int | None = None,
        preset_policy_fingerprint: str | None = None,
        import_run_id: str | None = None,
        seed_project: ProjectService | None = None,
        text_model_name: str | None = None,
    ) -> AnalysisBatchRun:
        if not candidates:
            raise ValidationError("select at least one notebook to analyse")
        ordered = list(batch_module_order(list(expand_with_hard_parents(list(module_ids)))))
        if not ordered:
            raise ValidationError("analysis batch requires at least one module")

        # Freeze template from the first candidate (or an explicit seed project).
        if seed_project is not None:
            projects = seed_project
        else:
            projects = ProjectService(
                open_project_paths(candidates[0].root),
                clock=self.clock,
                ids=self.ids,
            )
        override = (text_model_name or "").strip() or None
        template_plan = build_analysis_run_plan(
            project_service=projects,
            module_ids=ordered,
            question_text=question_text,
            preset_label=preset_label,
            preset_key=preset_key,
            preset_content_version=preset_content_version,
            preset_policy_fingerprint=preset_policy_fingerprint,
            clock=self.clock,
            ids=self.ids,
            text_model_name=override,
        )
        if override and template_plan.needs_llm() and template_plan.text_model is None:
            raise ValidationError(
                f"could not resolve text model `{override}` "
                "(needs a reachable text Ollama model)"
            )
        # Template fingerprint ignores project_id; recompute hash without it.
        tmpl_hash = plan_template_hash(
            module_ids=template_plan.module_ids,
            question_text=template_plan.question_text,
            effective_config=template_plan.effective_config,
            config_fingerprint=template_plan.config_fingerprint,
            text_model=template_plan.text_model,
            preset_key=template_plan.preset_key,
            preset_content_version=template_plan.preset_content_version,
            preset_policy_fingerprint=template_plan.preset_policy_fingerprint,
        )
        # Also keep a config fingerprint that is project-agnostic for storage.
        cfg_fp = config_fingerprint_for_plan(
            template_plan.effective_config,
            text_model=template_plan.text_model,
            module_ids=template_plan.module_ids,
            question_text=template_plan.question_text,
        )

        now = to_iso(self.clock.now())
        items = [
            AnalysisBatchItem(
                notebook_id=c.notebook_id,
                title=c.title,
                managed_relpath=c.managed_relpath,
                state="pending",
                modules_total=len(ordered),
            )
            for c in candidates
        ]
        run = AnalysisBatchRun(
            analysis_batch_id=self.ids.new_id(),
            created_at=now,
            updated_at=now,
            status="pending",
            module_ids=list(ordered),
            question_text=template_plan.question_text,
            effective_config=template_plan.effective_config.as_dict(),
            config_fingerprint=cfg_fp,
            text_model=(
                template_plan.text_model.as_dict() if template_plan.text_model else None
            ),
            plan_template_hash=tmpl_hash,
            preset_label=template_plan.preset_label,
            preset_key=template_plan.preset_key,
            preset_content_version=template_plan.preset_content_version,
            preset_policy_fingerprint=template_plan.preset_policy_fingerprint,
            import_run_id=import_run_id,
            items=items,
        )
        self.store.save(run)
        return run

    def start(self, analysis_batch_id: str) -> str:
        with self._lock:
            if (
                self._state is not None
                and self._state.thread
                and self._state.thread.is_alive()
            ):
                raise JobConflictError("a batch analysis job is already running")
            run = self.store.load(analysis_batch_id)
            progress = BatchAnalysisProgress(
                analysis_batch_id=run.analysis_batch_id,
                status="running",
                total=len(run.items),
                modules_total=len(run.module_ids),
                message="Starting…",
            )
            state = _BatchState(progress=progress, run=run)
            self._state = state
            _default_progress_log(progress)

            def runner() -> None:
                try:
                    self._run_batch(state)
                except Exception as exc:  # noqa: BLE001
                    _log.exception("batch analysis failed")
                    with self._lock:
                        state.progress.status = "failed"
                        state.progress.message = str(exc)
                        state.progress.error = str(exc)

            thread = threading.Thread(
                target=runner,
                name=f"transcribe-batch-analysis-{analysis_batch_id}",
                daemon=True,
            )
            state.thread = thread
            thread.start()
            return analysis_batch_id

    def run_blocking(self, analysis_batch_id: str) -> BatchAnalysisProgress:
        with self._lock:
            if (
                self._state is not None
                and self._state.thread
                and self._state.thread.is_alive()
            ):
                raise JobConflictError("a batch analysis job is already running")
            run = self.store.load(analysis_batch_id)
            progress = BatchAnalysisProgress(
                analysis_batch_id=run.analysis_batch_id,
                status="running",
                total=len(run.items),
                modules_total=len(run.module_ids),
            )
            state = _BatchState(progress=progress, run=run)
            self._state = state
        self._run_batch(state)
        return self.get_progress()

    def resume(
        self, analysis_batch_id: str, *, blocking: bool = True
    ) -> BatchAnalysisProgress | str:
        run = self.store.load(analysis_batch_id)
        for item in run.items:
            if item.state == "running":
                item.state = "pending"
                item.error_message = None
        run.updated_at = to_iso(self.clock.now())
        self.store.save(run)
        if blocking:
            return self.run_blocking(analysis_batch_id)
        return self.start(analysis_batch_id)

    def _run_batch(self, state: _BatchState) -> None:
        run = self.store.load(state.run.analysis_batch_id if state.run else "")
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
                state.progress.current_module_id = ""
                state.progress.modules_completed = 0
                state.progress.modules_failed = 0
                state.progress.modules_skipped = 0
                state.progress.modules_total = len(run.module_ids)
                state.progress.message = f"Analysing {label}"
                state.progress.total = total
                snap = _snapshot(state.progress)
            _default_progress_log(snap)

            try:
                root = self._root_for_item(item)
                projects = ProjectService(
                    open_project_paths(root), clock=self.clock, ids=self.ids
                )
                project = projects.load(reconcile=True)
                if pages_with_text_count(projects, project) == 0:
                    item.state = "skipped"
                    item.modules_total = len(run.module_ids)
                    item.error_message = "no effective page text"
                    continue

                plan = self._plan_for_notebook(run, projects, project)
                item.inner_run_id = plan.run_id
                item.modules_total = len(plan.module_ids)
                self.store.save(run)

                coord = AnalysisCoordinator(
                    projects, clock=self.clock, ids=self.ids
                )
                with self._lock:
                    state.inner = coord

                def on_progress(
                    progress: AnalysisProgress, *, _label=label, _item=item
                ) -> None:
                    if state.cancel_event.is_set():
                        coord.cancel()
                    with self._lock:
                        state.progress.current_item = _label
                        state.progress.current_module_id = progress.current_module_id
                        state.progress.modules_completed = progress.completed
                        state.progress.modules_failed = progress.failed
                        state.progress.modules_skipped = progress.skipped
                        state.progress.modules_total = progress.total or len(
                            run.module_ids
                        )
                        state.progress.message = progress.message or (
                            f"Analysing {progress.current_module_id} in {_label}"
                            if progress.current_module_id
                            else f"Analysing {_label}"
                        )
                        state.progress.cancel_requested = state.cancel_event.is_set()
                        if progress.error:
                            state.progress.error = progress.error

                inner = coord.run_blocking(plan, on_progress=on_progress)
                item.modules_total = inner.total
                item.modules_completed = inner.completed
                item.modules_failed = inner.failed
                item.modules_skipped = inner.skipped
                if inner.status == "cancelled":
                    item.state = "cancelled"
                    item.error_message = inner.message or "cancelled"
                elif inner.status == "failed":
                    item.state = "failed"
                    item.error_message = inner.error or inner.message or "failed"
                else:
                    item.state = "completed"
                    if inner.failed:
                        item.error_message = (
                            inner.message or f"{inner.failed} module(s) failed"
                        )
            except (
                JobConflictError,
                PlanHashMismatchError,
                TranscribeError,
                OSError,
                ValueError,
            ) as exc:
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
                    state.progress.current_module_id = ""

            run.updated_at = to_iso(self.clock.now())
            self.store.save(run)

        if state.cancel_event.is_set():
            for item in run.items:
                if item.state == "pending":
                    item.state = "cancelled"

        run.status = finalize_analysis_batch_status(run)
        run.updated_at = to_iso(self.clock.now())
        self.store.save(run)
        with self._lock:
            state.progress.status = run.status
            state.progress.current_item = ""
            state.progress.current_module_id = ""
            state.progress.message = f"Batch {run.status}"
            state.progress.completed = sum(
                1 for i in run.items if i.state == "completed"
            )
            state.progress.failed = sum(1 for i in run.items if i.state == "failed")
            state.progress.skipped = sum(1 for i in run.items if i.state == "skipped")
            snap = _snapshot(state.progress)
        _default_progress_log(snap)

    def _plan_for_notebook(
        self,
        run: AnalysisBatchRun,
        projects: ProjectService,
        project: Any,
    ) -> AnalysisRunPlan:
        """Build a per-notebook plan from the frozen batch template."""
        batch_frozen = (
            FrozenTextModel.from_dict(run.text_model) if run.text_model else None
        )
        return build_analysis_run_plan(
            project_service=projects,
            module_ids=list(run.module_ids),
            question_text=run.question_text,
            preset_label=run.preset_label,
            preset_key=run.preset_key,
            preset_content_version=run.preset_content_version,
            preset_policy_fingerprint=run.preset_policy_fingerprint,
            clock=self.clock,
            ids=self.ids,
            project=project,
            text_model=batch_frozen,
        )

    def _root_for_item(self, item: AnalysisBatchItem) -> Path:
        if item.managed_relpath:
            try:
                return self.corpus.resolve_managed(item.managed_relpath)
            except ValueError:
                pass
        return resolve_notebook_root(self.corpus, item.notebook_id)


def build_batch_analysis_coordinator(
    corpus: CorpusPaths,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
) -> BatchAnalysisCoordinator:
    return BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
