"""Project load/save, reconciliation, merge-safe result writes."""

from __future__ import annotations

import shutil
from pathlib import Path

from transcribe.domain.dates import (
    ApproximateDate,
    DATE_SOURCE_EXTRACTED,
    DATE_SOURCE_INHERITED,
    extract_page_date,
    normalize_tags,
)
from transcribe.domain.models import (
    MAX_ATTEMPTS_RETAINED,
    OCRAttempt,
    OCRSettings,
    PageIndex,
    PageResult,
    Project,
)
from transcribe.domain.validation import validate_page_result, validate_project
from transcribe.errors import JobConflictError, ProjectError
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import job_lock_held, mutation_lock
from transcribe.persistence.schema import require_format
from transcribe.ports import Clock, IdGenerator, to_iso
from transcribe.runtime_paths import default_ollama_base_url


def _seed_ocr_settings() -> OCRSettings:
    """Seed new-project OCR from workspace defaults (one-shot; then project-owned)."""
    from transcribe.config.facade import get_config

    view = get_config()
    ocr = view.effective.ocr
    base = (ocr.base_url or "").strip() or default_ollama_base_url()
    data = {
        "base_url": base,
        "prompt_id": ocr.prompt_id,
        "language": ocr.language,
        "preprocess_profile": ocr.preprocess_profile,
        "max_workers": ocr.max_workers,
        "cleanup_enabled": ocr.cleanup_enabled,
        "cleanup_mode": ocr.cleanup_mode,
        "cleanup_model_name": ocr.cleanup_model_name,
        "text_model_name": ocr.text_model_name,
    }
    return OCRSettings.from_dict(data)


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
            settings=_seed_ocr_settings(),
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

            declutter = True
            try:
                from transcribe.config.facade import get_config

                declutter = bool(
                    get_config().effective.ingest.visual_declutter_enabled
                )
            except Exception:
                pass
            IngestService(
                self.paths,
                clock=self.clock,
                ids=self.ids,
                visual_declutter_enabled=declutter,
            ).recover_incomplete_ingest()
        with mutation_lock(self.paths.mutation_lock):
            project = self._load_unlocked(reconcile=reconcile)
        if reconcile:
            from transcribe.analysis.storage import AnalysisStorage
            from transcribe.detection.storage import DetectionStorage

            AnalysisStorage(self.paths).reconcile_interrupted()
            DetectionStorage(self.paths).reconcile_interrupted()
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
        tags: list[str] | object = _UNSET,
    ) -> Project:
        """Merge-safe page metadata updates (tags). Date changes use approve_page_date."""
        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            found = False
            for page in current.pages:
                if page.page_id != page_id:
                    continue
                found = True
                if tags is not _UNSET:
                    page.tags = normalize_tags(tags)  # type: ignore[arg-type]
                break
            if not found:
                raise ProjectError(f"unknown page_id: {page_id}")
            current.updated_at = to_iso(self.clock.now())
            validate_project(current)
            write_json_atomic(self.paths.manifest, current.as_dict())
            return current

    def approve_page_date(
        self,
        page_id: str,
        date: ApproximateDate | None,
    ) -> tuple[Project, bool]:
        """Atomically set human-approved date (approved=True, source=None).

        Returns (project, date_value_changed).
        """
        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            page = self._require_page(current, page_id)
            old = page.date
            page.set_date_state(date, approved=True, source=None)
            current.updated_at = to_iso(self.clock.now())
            validate_project(current)
            write_json_atomic(self.paths.manifest, current.as_dict())
            return current, old != page.date

    def suggest_page_date(self, page_id: str) -> bool:
        """Suggest date from effective_text or previous page. Returns True if date value changed.

        Reloads on-disk project under the mutation lock (never a job-start snapshot).
        Never overwrites an approved date.
        """
        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            page = self._require_page(current, page_id)
            if page.date is not None and page.date_approved:
                return False
            idx = next(i for i, p in enumerate(current.pages) if p.page_id == page_id)
            old_date = page.date
            old_approved = page.date_approved
            old_source = page.date_source
            result = self._load_page_result_unlocked(page_id)
            text = result.effective_text() if result else None
            self._apply_suggestion(
                current.pages, idx, text, cover_page_id=current.cover_page_id
            )
            page = current.pages[idx]
            value_changed = old_date != page.date
            state_changed = (
                value_changed
                or old_approved != page.date_approved
                or old_source != page.date_source
            )
            if state_changed:
                current.updated_at = to_iso(self.clock.now())
                validate_project(current)
                write_json_atomic(self.paths.manifest, current.as_dict())
            return value_changed

    def fill_page_dates_ordered(self) -> int:
        """Walk pages in order; apply extract→inherit; one manifest write.

        Cover page (explicit ``cover_page_id``, else first page) inherits from the
        first dated page when it has no extractable stamp — done in a post-pass
        so later pages can donate a date.

        Returns number of pages whose date **value** changed.
        """
        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            value_changed = 0
            any_change = False

            def _note(page: PageIndex, old_date, old_approved, old_source) -> None:
                nonlocal value_changed, any_change
                if old_date != page.date:
                    value_changed += 1
                if (
                    old_date != page.date
                    or old_approved != page.date_approved
                    or old_source != page.date_source
                ):
                    any_change = True

            for idx, page in enumerate(current.pages):
                if page.date is not None and page.date_approved:
                    continue
                old_date = page.date
                old_approved = page.date_approved
                old_source = page.date_source
                result = self._load_page_result_unlocked(page.page_id)
                text = result.effective_text() if result else None
                self._apply_suggestion(
                    current.pages,
                    idx,
                    text,
                    cover_page_id=current.cover_page_id,
                )
                _note(current.pages[idx], old_date, old_approved, old_source)

            cover_idx = self._cover_page_index(current.pages, current.cover_page_id)
            if cover_idx is not None:
                cover = current.pages[cover_idx]
                if cover.date is None or not cover.date_approved:
                    old_date = cover.date
                    old_approved = cover.date_approved
                    old_source = cover.date_source
                    result = self._load_page_result_unlocked(cover.page_id)
                    text = result.effective_text() if result else None
                    self._apply_suggestion(
                        current.pages,
                        cover_idx,
                        text,
                        cover_page_id=current.cover_page_id,
                    )
                    _note(current.pages[cover_idx], old_date, old_approved, old_source)

            if any_change:
                current.updated_at = to_iso(self.clock.now())
                validate_project(current)
                write_json_atomic(self.paths.manifest, current.as_dict())
            return value_changed

    @staticmethod
    def _require_page(project: Project, page_id: str) -> PageIndex:
        for page in project.pages:
            if page.page_id == page_id:
                return page
        raise ProjectError(f"unknown page_id: {page_id}")

    @staticmethod
    def _cover_page_index(
        pages: list[PageIndex], cover_page_id: str | None
    ) -> int | None:
        if not pages:
            return None
        if cover_page_id:
            for i, page in enumerate(pages):
                if page.page_id == cover_page_id:
                    return i
        return 0

    def _apply_suggestion(
        self,
        pages: list[PageIndex],
        idx: int,
        text: str | None,
        *,
        cover_page_id: str | None = None,
    ) -> None:
        page = pages[idx]
        if page.date is not None and page.date_approved:
            return
        extracted = extract_page_date(text)
        if extracted is not None:
            page.set_date_state(
                extracted, approved=False, source=DATE_SOURCE_EXTRACTED
            )
            return
        for prev in reversed(pages[:idx]):
            if prev.date is not None:
                page.set_date_state(
                    prev.date, approved=False, source=DATE_SOURCE_INHERITED
                )
                return
        # Cover pages rarely carry a diary stamp; inherit the first dated page.
        cover_idx = self._cover_page_index(pages, cover_page_id)
        if cover_idx == idx:
            for other in pages:
                if other.page_id == page.page_id or other.date is None:
                    continue
                page.set_date_state(
                    other.date, approved=False, source=DATE_SOURCE_INHERITED
                )
                return
        page.set_date_state(None, approved=True, source=None)

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


def delete_managed_notebook(
    project_root: Path | str,
    *,
    projects_dir: Path | str,
) -> Path:
    """Delete a managed notebook directory (imported copies only).

    External originals outside the project tree are never touched. The root must
    resolve under ``projects_dir``, be a real directory, and contain
    ``project.json``.
    """
    projects = Path(projects_dir).expanduser().resolve()
    try:
        root = Path(project_root).expanduser().resolve()
    except OSError as exc:
        raise ProjectError(f"unresolvable project root: {exc}") from exc

    try:
        root.relative_to(projects)
    except ValueError as exc:
        raise ProjectError(
            f"project root escapes projects directory: {root}"
        ) from exc

    if root == projects:
        raise ProjectError(
            "refusing to delete projects directory itself; pass a notebook root"
        )
    if not root.is_dir():
        raise ProjectError(f"project root is not a directory: {root}")
    if not (root / "project.json").is_file():
        raise ProjectError(f"missing project.json under {root}")

    job_lock = root / ".transcribe.job.lock"
    if job_lock_held(job_lock):
        raise JobConflictError(
            "cannot delete notebook while an OCR job is running"
        )

    # Brief exclusive section so concurrent mutators fail closed before removal.
    mutation = root / ".transcribe.lock"
    with mutation_lock(mutation):
        pass

    shutil.rmtree(root)
    return root
