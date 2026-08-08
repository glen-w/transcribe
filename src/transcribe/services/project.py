"""Project load/save, reconciliation, merge-safe result writes."""

from __future__ import annotations

from pathlib import Path

from transcribe.domain.dates import ApproximateDate, normalize_tags
from transcribe.domain.models import (
    MAX_ATTEMPTS_RETAINED,
    OCRAttempt,
    OCRSettings,
    PageResult,
    Project,
)
from transcribe.domain.validation import validate_page_result, validate_project
from transcribe.errors import ProjectError
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import job_lock_held, mutation_lock
from transcribe.persistence.schema import require_format
from transcribe.ports import Clock, IdGenerator, to_iso
from transcribe.runtime_paths import default_ollama_base_url

_UNSET = object()


class ProjectService:
    def __init__(
        self,
        paths: ProjectPaths,
        *,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self.paths = paths
        self.clock = clock
        self.ids = ids

    def create(self, title: str = "Untitled notebook") -> Project:
        self.paths.ensure_layout()
        if self.paths.manifest.exists():
            raise ProjectError(f"project already exists at {self.paths.root}")
        now = to_iso(self.clock.now())
        project = Project(
            id=self.ids.new_id(),
            title=title,
            created_at=now,
            updated_at=now,
            settings=OCRSettings(base_url=default_ollama_base_url()),
        )
        validate_project(project)
        with mutation_lock(self.paths.mutation_lock):
            write_json_atomic(self.paths.manifest, project.as_dict())
        return project

    def _load_unlocked(self, *, reconcile: bool = True) -> Project:
        if not self.paths.manifest.exists():
            raise ProjectError(f"no project.json at {self.paths.root}")
        payload = require_format(read_json(self.paths.manifest), "transcribe.project")
        project = Project.from_dict(payload)
        validate_project(project, paths=self.paths, deep=False)
        if reconcile:
            self._reconcile_interrupted_locked()
        return project

    def load(self, *, reconcile: bool = True) -> Project:
        # Finish or roll back a crash-interrupted ingest before trusting the manifest.
        if self.paths.ingest_journal.exists():
            from transcribe.ingest import IngestService

            IngestService(
                self.paths, clock=self.clock, ids=self.ids
            ).recover_incomplete_ingest()
        with mutation_lock(self.paths.mutation_lock):
            project = self._load_unlocked(reconcile=reconcile)
        if reconcile:
            from transcribe.analysis.storage import AnalysisStorage

            AnalysisStorage(self.paths).reconcile_interrupted()
        return project

    def save_settings(self, project: Project, settings: OCRSettings) -> Project:
        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            current.settings = settings
            current.updated_at = to_iso(self.clock.now())
            validate_project(current)
            write_json_atomic(self.paths.manifest, current.as_dict())
            return current

    def update_page_metadata(
        self,
        page_id: str,
        *,
        date: ApproximateDate | None | object = _UNSET,
        tags: list[str] | object = _UNSET,
    ) -> Project:
        """Update user-owned page date/tags. Omit a kwarg (or pass sentinel) to leave it."""
        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            found = False
            for page in current.pages:
                if page.page_id != page_id:
                    continue
                found = True
                if date is not _UNSET:
                    page.date = date  # type: ignore[assignment]
                if tags is not _UNSET:
                    page.tags = normalize_tags(tags)  # type: ignore[arg-type]
                break
            if not found:
                raise ProjectError(f"unknown page_id: {page_id}")
            current.updated_at = to_iso(self.clock.now())
            validate_project(current)
            write_json_atomic(self.paths.manifest, current.as_dict())
            return current

    def update_notebook_metadata(
        self,
        *,
        title: str | object = _UNSET,
        tags: list[str] | object = _UNSET,
        cover_page_id: str | None | object = _UNSET,
        date_start: ApproximateDate | None | object = _UNSET,
        date_end: ApproximateDate | None | object = _UNSET,
    ) -> Project:
        """Update notebook-level user metadata. Omit kwargs to leave fields unchanged."""
        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            if title is not _UNSET:
                current.title = str(title)
            if tags is not _UNSET:
                current.tags = normalize_tags(tags)  # type: ignore[arg-type]
            if cover_page_id is not _UNSET:
                if cover_page_id is not None and not any(
                    p.page_id == cover_page_id for p in current.pages
                ):
                    raise ProjectError(f"unknown cover_page_id: {cover_page_id}")
                current.cover_page_id = cover_page_id  # type: ignore[assignment]
            if date_start is not _UNSET:
                current.date_start = date_start  # type: ignore[assignment]
            if date_end is not _UNSET:
                current.date_end = date_end  # type: ignore[assignment]
            current.updated_at = to_iso(self.clock.now())
            validate_project(current)
            write_json_atomic(self.paths.manifest, current.as_dict())
            return current

    def _load_page_result_unlocked(self, page_id: str) -> PageResult | None:
        path = self.paths.result_path(page_id)
        if not path.exists():
            return None
        payload = require_format(read_json(path), "transcribe.page-result")
        result = PageResult.from_dict(payload)
        validate_page_result(result, expected_page_id=page_id)
        return result

    def load_page_result(self, page_id: str) -> PageResult | None:
        return self._load_page_result_unlocked(page_id)

    def record_generation(self, page_id: str, attempt: OCRAttempt) -> PageResult:
        with mutation_lock(self.paths.mutation_lock):
            existing = self._load_page_result_unlocked(page_id) or PageResult(
                page_id=page_id
            )
            # Replace same attempt_id if updating running→terminal; else append.
            replaced = False
            for i, old in enumerate(existing.attempts):
                if old.attempt_id == attempt.attempt_id:
                    existing.attempts[i] = attempt
                    replaced = True
                    break
            if not replaced:
                existing.attempts.append(attempt)
            existing.active_attempt_id = attempt.attempt_id
            if len(existing.attempts) > MAX_ATTEMPTS_RETAINED:
                # Keep active + newest others
                active_id = existing.active_attempt_id
                ordered = sorted(
                    existing.attempts,
                    key=lambda a: a.started_at,
                    reverse=True,
                )
                kept: list[OCRAttempt] = []
                for a in ordered:
                    if a.attempt_id == active_id or len(kept) < MAX_ATTEMPTS_RETAINED:
                        if a not in kept:
                            kept.append(a)
                existing.attempts = list(reversed(kept))
            existing.updated_at = to_iso(self.clock.now())
            validate_page_result(existing, expected_page_id=page_id)
            write_json_atomic(self.paths.result_path(page_id), existing.as_dict())
            return existing

    def save_user_edit(self, page_id: str, edited_text: str | None) -> PageResult:
        with mutation_lock(self.paths.mutation_lock):
            existing = self._load_page_result_unlocked(page_id)
            if existing is None:
                existing = PageResult(page_id=page_id)
            existing.edited_text = edited_text
            existing.updated_at = to_iso(self.clock.now())
            validate_page_result(existing, expected_page_id=page_id)
            write_json_atomic(self.paths.result_path(page_id), existing.as_dict())
            return existing

    def adopt_raw_as_edit(self, page_id: str) -> PageResult:
        """Clear edited_text so effective text becomes active raw."""
        return self.save_user_edit(page_id, None)

    def _reconcile_interrupted_locked(self) -> None:
        if job_lock_held(self.paths.job_lock):
            return
        for path in self.paths.results_dir.glob("*.json"):
            try:
                payload = require_format(read_json(path), "transcribe.page-result")
                result = PageResult.from_dict(payload)
                validate_page_result(result, expected_page_id=path.stem)
            except Exception:
                continue
            changed = False
            for attempt in result.attempts:
                if attempt.status == "running":
                    attempt.status = "interrupted"
                    if attempt.error is None:
                        from transcribe.domain.models import AttemptError

                        attempt.error = AttemptError(
                            code="interrupted",
                            message="OCR attempt interrupted by process exit",
                            retriable=True,
                        )
                    attempt.completed_at = to_iso(self.clock.now())
                    changed = True
            if changed:
                result.updated_at = to_iso(self.clock.now())
                write_json_atomic(path, result.as_dict())


def open_project_paths(root: Path) -> ProjectPaths:
    paths = ProjectPaths(root=Path(root).expanduser().resolve())
    paths.ensure_layout()
    return paths
