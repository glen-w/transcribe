"""Project load/save, reconciliation, merge-safe result writes."""

from __future__ import annotations

from pathlib import Path

from transcribe.domain.models import (
    MAX_ATTEMPTS_RETAINED,
    OCRAttempt,
    OCRSettings,
    PageResult,
    Project,
)
from transcribe.errors import ProjectError
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import job_lock_held, mutation_lock
from transcribe.persistence.schema import require_format
from transcribe.ports import Clock, IdGenerator, to_iso


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
            settings=OCRSettings(),
        )
        with mutation_lock(self.paths.mutation_lock):
            write_json_atomic(self.paths.manifest, project.as_dict())
        return project

    def load(self, *, reconcile: bool = True) -> Project:
        if not self.paths.manifest.exists():
            raise ProjectError(f"no project.json at {self.paths.root}")
        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            project = Project.from_dict(payload)
            for page in project.pages:
                # Validate stored render path containment via renders map
                render = project.renders.get(page.active_render_id)
                if render is None:
                    raise ProjectError(
                        f"page {page.page_id} missing render {page.active_render_id}"
                    )
                self.paths.resolve_contained(render.image_relpath)
            for source in project.sources:
                self.paths.resolve_contained(source.stored_relpath)
            if reconcile:
                self._reconcile_interrupted_locked()
            return project

    def save_settings(self, project: Project, settings: OCRSettings) -> Project:
        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            current.settings = settings
            current.updated_at = to_iso(self.clock.now())
            write_json_atomic(self.paths.manifest, current.as_dict())
            return current

    def load_page_result(self, page_id: str) -> PageResult | None:
        path = self.paths.result_path(page_id)
        if not path.exists():
            return None
        payload = require_format(read_json(path), "transcribe.page-result")
        # Ignore payload["status"] if present — authority is active_attempt.status
        # via PageResult.status. Writers always persist the derived value via as_dict().
        return PageResult.from_dict(payload)

    def record_generation(self, page_id: str, attempt: OCRAttempt) -> PageResult:
        with mutation_lock(self.paths.mutation_lock):
            existing = self.load_page_result(page_id) or PageResult(page_id=page_id)
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
            # Persist with derived status field
            write_json_atomic(self.paths.result_path(page_id), existing.as_dict())
            return existing

    def save_user_edit(self, page_id: str, edited_text: str | None) -> PageResult:
        with mutation_lock(self.paths.mutation_lock):
            existing = self.load_page_result(page_id)
            if existing is None:
                existing = PageResult(page_id=page_id)
            existing.edited_text = edited_text
            existing.updated_at = to_iso(self.clock.now())
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
            except Exception:
                continue
            result = PageResult.from_dict(payload)
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
