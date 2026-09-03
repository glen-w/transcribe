"""Project load/save, reconciliation, merge-safe result writes."""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from transcribe.domain.dates import (
    ApproximateDate,
    DATE_SOURCE_EXTRACTED,
    DATE_SOURCE_INHERITED,
    DateRegression,
    extract_page_date,
    find_date_regressions,
    looks_like_unparsed_date_stamp,
    normalize_tags,
)
from transcribe.domain.models import (
    AttemptError,
    ComparisonRecord,
    DEFAULT_PREFER_MODE,
    EDIT_GATE_CHOICES,
    EFFECTIVE_TEXT_ORIGINS,
    EMPTY_OUTPUT_CODE,
    EMPTY_OUTPUT_MESSAGE,
    MAX_ATTEMPTS_RETAINED,
    OCRAttempt,
    OCRSettings,
    PREFER_MODES,
    REVIEW_STATUSES,
    PageIndex,
    PageResult,
    Project,
    page_label,
    prune_attempts,
)
from transcribe.domain.validation import validate_page_result, validate_project
from transcribe.errors import JobConflictError, ProjectError
from transcribe.corpus.paths import CorpusPaths
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
    llm = view.effective.llm
    base = (ocr.base_url or "").strip() or default_ollama_base_url()
    text_model = (ocr.text_model_name or "").strip() or (llm.text_model_preference or "").strip()
    data = {
        "base_url": base,
        "prompt_id": ocr.prompt_id,
        "language": ocr.language,
        "preprocess_profile": ocr.preprocess_profile,
        "max_workers": ocr.max_workers,
        "cleanup_enabled": ocr.cleanup_enabled,
        "cleanup_mode": ocr.cleanup_mode,
        "cleanup_model_name": ocr.cleanup_model_name,
        "text_model_name": text_model,
        "prefer_mode": getattr(ocr, "prefer_mode", "prefer_is_promote"),
        "auto_activate_composite": getattr(ocr, "auto_activate_composite", True),
    }
    return OCRSettings.from_dict(data)


_UNSET = object()


def _origin_from_active(result: PageResult) -> str | None:
    from transcribe.services.ocr_composite_state import current_composite_attempt

    if result.edited_text is not None:
        return result.effective_text_origin
    active = result.active_attempt()
    if active is None:
        return None
    current = current_composite_attempt(result)
    if current is not None and active.attempt_id == current.attempt_id:
        return "composite"
    if (active.attempt_kind or "vision") == "composite":
        return "composite"
    return "ocr_attempt"


def _latest_succeeded_with_text(
    attempts: list[OCRAttempt],
    *,
    exclude_id: str | None = None,
) -> OCRAttempt | None:
    found: OCRAttempt | None = None
    for attempt in attempts:
        if exclude_id and attempt.attempt_id == exclude_id:
            continue
        if attempt.status != "succeeded":
            continue
        if not (attempt.raw_text or "").strip():
            continue
        if found is None or attempt.started_at >= found.started_at:
            found = attempt
    return found


def _active_after_generation(
    existing: PageResult,
    attempt: OCRAttempt,
    *,
    activate: bool,
) -> str | None:
    """Choose active_attempt_id after appending/updating ``attempt``.

    Succeeded-with-text may become active when ``activate`` is true. Failed,
    running, and empty writes keep a prior good reading. First-ever attempt
    (no prior succeeded-with-text) may still become active when ``activate``.
    """
    prior_good = _latest_succeeded_with_text(existing.attempts, exclude_id=attempt.attempt_id)
    current = existing.active_attempt_id
    if not activate:
        if current:
            return current
        return prior_good.attempt_id if prior_good else current
    if attempt.status == "succeeded" and (attempt.raw_text or "").strip():
        return attempt.attempt_id
    if current and current != attempt.attempt_id:
        return current
    if prior_good:
        return prior_good.attempt_id
    return attempt.attempt_id


def _review_fingerprints_match(result: PageResult | None) -> bool:
    from transcribe.services.ocr_composite_state import (
        evidence_fingerprint,
        reviewed_text_fingerprint,
    )

    if result is None:
        return False
    if not result.reviewed_text_fingerprint or not result.reviewed_evidence_fingerprint:
        return False
    text = result.effective_text() or ""
    return result.reviewed_text_fingerprint == reviewed_text_fingerprint(
        text
    ) and result.reviewed_evidence_fingerprint == evidence_fingerprint(result)


def _review_should_invalidate(before: PageResult | None, after: PageResult) -> bool:
    from transcribe.services.ocr_composite_state import evidence_fingerprint

    if before is None:
        return True
    if (before.effective_text() or "") != (after.effective_text() or ""):
        return True
    if before.active_attempt_id != after.active_attempt_id:
        return True
    return evidence_fingerprint(before) != evidence_fingerprint(after)


@dataclass
class DeclutterReapplyStats:
    pages_total: int = 0
    pages_cropped: int = 0
    pages_noop: int = 0
    pages_unchanged: int = 0
    pages_error: int = 0


class ProjectService:
    def __init__(
        self,
        paths: ProjectPaths,
        *,
        clock: Clock,
        ids: IdGenerator,
        corpus_paths: CorpusPaths | None = None,
    ) -> None:
        self.paths = paths
        self.clock = clock
        self.ids = ids
        self.corpus_paths = corpus_paths

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
        if self.corpus_paths is not None:
            from transcribe.services.corpus_registry import ensure_registered

            ensure_registered(
                self.corpus_paths,
                project_root=self.paths.root,
                project_id=project.id,
                clock=self.clock,
            )
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

                declutter = bool(get_config().effective.ingest.visual_declutter_enabled)
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

    def content_revision(self, project: Project | None = None) -> str:
        """Compute notebook content_revision from a coherent on-disk snapshot."""
        from transcribe.domain.content_revision import content_revision_hex

        with mutation_lock(self.paths.mutation_lock):
            snap = self._load_unlocked(reconcile=False) if project is None else project
            # When caller passes project, still re-read page results under lock for coherence.
            if project is not None:
                snap = project
            results: dict[str, PageResult | None] = {}
            for page in snap.pages:
                results[page.page_id] = self._load_page_result_unlocked(page.page_id)
            return content_revision_hex(snap, results)

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

    def delete_page(self, page_id: str) -> Project:
        """Remove a page from the notebook (manifest + on-disk artifacts).

        Reindexes later pages in the same source so ``page_index`` stays
        contiguous. Removes the source when it has no remaining pages. Refuses
        when the notebook would become empty (delete the notebook instead) or
        while an OCR job lock is held.
        """
        if job_lock_held(self.paths.job_lock):
            raise JobConflictError("cannot delete page while an OCR job is running")

        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            if len(current.pages) <= 1:
                raise ProjectError("cannot delete the last page; delete the notebook instead")
            page = self._require_page(current, page_id)
            source_id = page.source_id
            deleted_index = page.page_index
            render_id = page.active_render_id

            current.renders.pop(render_id, None)
            current.pages = [p for p in current.pages if p.page_id != page_id]
            if current.cover_page_id == page_id:
                current.cover_page_id = None

            # Remove this page's artifacts before reindex can reuse its directory.
            page_dir = self.paths.pages_dir / source_id / f"{deleted_index:04d}"
            if page_dir.is_dir():
                shutil.rmtree(page_dir, ignore_errors=True)
            try:
                self.paths.result_path(page_id).unlink(missing_ok=True)
            except OSError:
                pass
            try:
                self.paths.thumb_path(page_id).unlink(missing_ok=True)
            except OSError:
                pass
            try:
                self.paths.grid_thumb_path(page_id).unlink(missing_ok=True)
            except OSError:
                pass

            # Reindex later pages in this source via a staging dir to avoid collisions.
            siblings = [
                p
                for p in current.pages
                if p.source_id == source_id and p.page_index > deleted_index
            ]
            siblings.sort(key=lambda p: p.page_index)
            if siblings:
                staging_root = self.paths.pages_dir / source_id / f".reindex-{page_id}"
                if staging_root.exists():
                    shutil.rmtree(staging_root, ignore_errors=True)
                staging_root.mkdir(parents=True, exist_ok=True)
                for sibling in siblings:
                    old_index = sibling.page_index
                    old_dir = self.paths.pages_dir / source_id / f"{old_index:04d}"
                    if old_dir.is_dir():
                        old_dir.rename(staging_root / f"{old_index:04d}")
                for sibling in siblings:
                    old_index = sibling.page_index
                    new_index = old_index - 1
                    staged = staging_root / f"{old_index:04d}"
                    new_dir = self.paths.pages_dir / source_id / f"{new_index:04d}"
                    if staged.is_dir():
                        if new_dir.exists():
                            raise ProjectError(
                                f"cannot reindex page directory: {new_dir} already exists"
                            )
                        staged.rename(new_dir)
                    sibling.page_index = new_index
                    sib_render = current.renders.get(sibling.active_render_id)
                    if sib_render is not None:
                        old_rel = sib_render.image_relpath
                        prefix = f"pages/{source_id}/{old_index:04d}/"
                        new_prefix = f"pages/{source_id}/{new_index:04d}/"
                        if old_rel.startswith(prefix):
                            sib_render.image_relpath = new_prefix + old_rel[len(prefix) :]
                        if sib_render.pdf_page_index == old_index:
                            sib_render.pdf_page_index = new_index
                try:
                    staging_root.rmdir()
                except OSError:
                    shutil.rmtree(staging_root, ignore_errors=True)

            remaining_in_source = [p for p in current.pages if p.source_id == source_id]
            source_file: Path | None = None
            if remaining_in_source:
                for source in current.sources:
                    if source.source_id == source_id:
                        source.page_count = len(remaining_in_source)
                        break
            else:
                source_obj = next(
                    (s for s in current.sources if s.source_id == source_id),
                    None,
                )
                current.sources = [s for s in current.sources if s.source_id != source_id]
                if source_obj is not None:
                    try:
                        source_file = self.paths.resolve_contained(source_obj.stored_relpath)
                    except ValueError:
                        source_file = None
                source_pages_root = self.paths.pages_dir / source_id
                if source_pages_root.is_dir():
                    shutil.rmtree(source_pages_root, ignore_errors=True)

            current.updated_at = to_iso(self.clock.now())
            validate_project(current, paths=self.paths)
            write_json_atomic(self.paths.manifest, current.as_dict())

            if source_file is not None:
                try:
                    source_file.unlink(missing_ok=True)
                except OSError:
                    pass
            return current

    def approve_page_date(
        self,
        page_id: str,
        date: ApproximateDate | None,
    ) -> tuple[Project, bool]:
        """Atomically set human-approved date (approved=True, source=None).

        When the date **value** changes, re-infers unapproved downstream pages
        (and the cover page when applicable) so inherited suggestions stay aligned
        with the new upstream date.

        Returns (project, date_value_changed) for the approved page only.
        """
        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            page = self._require_page(current, page_id)
            idx = next(i for i, p in enumerate(current.pages) if p.page_id == page_id)
            old = page.date
            page.set_date_state(date, approved=True, source=None)
            date_value_changed = old != page.date
            if date_value_changed:
                self._reinfer_unapproved_page_dates(
                    current.pages,
                    cover_page_id=current.cover_page_id,
                    start_idx=idx + 1,
                    cover_look_ahead=False,
                    skip_cover_post_pass_for_idx=idx,
                )
            current.updated_at = to_iso(self.clock.now())
            validate_project(current)
            write_json_atomic(self.paths.manifest, current.as_dict())
            return current, date_value_changed

    def list_date_regressions(self, project: Project | None = None) -> list[DateRegression]:
        """Notebook-order date regressions for bulk-approve honesty."""
        current = project if project is not None else self.load(reconcile=False)
        return find_date_regressions([(page.page_id, page.date) for page in current.pages])

    def approve_all_suggested_dates(
        self,
        *,
        confirm_regressions: bool = False,
    ) -> tuple[Project, int, list[DateRegression]]:
        """Approve every unapproved suggested date in notebook order.

        Returns ``(project, approved_count, regressions)``. When regressions
        exist and ``confirm_regressions`` is false, writes nothing and returns
        count 0 so the UI can confirm.
        """
        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            regressions = find_date_regressions(
                [(page.page_id, page.date) for page in current.pages]
            )
            if regressions and not confirm_regressions:
                return current, 0, regressions
            changed = 0
            for page in current.pages:
                if page.date is None or page.date_approved:
                    continue
                page.set_date_state(page.date, approved=True, source=None)
                changed += 1
            if changed:
                current.updated_at = to_iso(self.clock.now())
                validate_project(current)
                write_json_atomic(self.paths.manifest, current.as_dict())
            return current, changed, regressions

    def ignore_all_suggested_dates(self) -> tuple[Project, int]:
        """Clear every unapproved suggested date (human ignore)."""
        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            changed = 0
            for page in current.pages:
                if page.date is None or page.date_approved:
                    continue
                page.set_date_state(None, approved=True, source=None)
                changed += 1
            if changed:
                current.updated_at = to_iso(self.clock.now())
                validate_project(current)
                write_json_atomic(self.paths.manifest, current.as_dict())
            return current, changed

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
            self._apply_suggestion(current.pages, idx, text, cover_page_id=current.cover_page_id)
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
            value_changed, any_change = self._reinfer_unapproved_page_dates(
                current.pages,
                cover_page_id=current.cover_page_id,
                start_idx=0,
            )
            if any_change:
                current.updated_at = to_iso(self.clock.now())
                validate_project(current)
                write_json_atomic(self.paths.manifest, current.as_dict())
            return value_changed

    def _reinfer_unapproved_page_dates(
        self,
        pages: list[PageIndex],
        *,
        cover_page_id: str | None,
        start_idx: int = 0,
        cover_look_ahead: bool = True,
        skip_cover_post_pass_for_idx: int | None = None,
    ) -> tuple[int, bool]:
        """Re-run extract→inherit for unapproved pages from ``start_idx`` (+ cover post-pass).

        ``cover_look_ahead`` (default true) lets undated approved cover pages inherit
        from the first dated page during a full ordered fill. Partial cascades after
        human date edits disable this so explicitly undated covers stay undated.

        Returns (date_value_changed_count, any_state_changed).
        """
        value_changed = 0
        any_change = False
        cascade_mode = not cover_look_ahead

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

        for idx in range(start_idx, len(pages)):
            page = pages[idx]
            if page.date_approved and (cascade_mode or page.date is not None):
                continue
            old_date = page.date
            old_approved = page.date_approved
            old_source = page.date_source
            result = self._load_page_result_unlocked(page.page_id)
            text = result.effective_text() if result else None
            self._apply_suggestion(
                pages,
                idx,
                text,
                cover_page_id=cover_page_id,
            )
            _note(pages[idx], old_date, old_approved, old_source)

        cover_idx = self._cover_page_index(pages, cover_page_id)
        if cover_idx is not None and cover_idx != skip_cover_post_pass_for_idx:
            cover = pages[cover_idx]
            should_refresh = not cover.date_approved
            if cover_look_ahead and cover.date is None and cover.date_approved:
                should_refresh = True
            if should_refresh:
                old_date = cover.date
                old_approved = cover.date_approved
                old_source = cover.date_source
                result = self._load_page_result_unlocked(cover.page_id)
                text = result.effective_text() if result else None
                self._apply_suggestion(
                    pages,
                    cover_idx,
                    text,
                    cover_page_id=cover_page_id,
                )
                _note(pages[cover_idx], old_date, old_approved, old_source)

        return value_changed, any_change

    @staticmethod
    def _require_page(project: Project, page_id: str) -> PageIndex:
        for page in project.pages:
            if page.page_id == page_id:
                return page
        raise ProjectError(f"unknown page_id: {page_id}")

    @staticmethod
    def _cover_page_index(pages: list[PageIndex], cover_page_id: str | None) -> int | None:
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
            page.set_date_state(extracted, approved=False, source=DATE_SOURCE_EXTRACTED)
            return
        # Failed-looking stamp: stay undated for Review (do not inherit).
        if looks_like_unparsed_date_stamp(text):
            page.set_date_state(None, approved=True, source=None)
            return
        for prev in reversed(pages[:idx]):
            if prev.date is not None:
                page.set_date_state(prev.date, approved=False, source=DATE_SOURCE_INHERITED)
                return
        # Cover pages rarely carry a diary stamp; inherit the first dated page.
        cover_idx = self._cover_page_index(pages, cover_page_id)
        if cover_idx == idx:
            for other in pages:
                if other.page_id == page.page_id or other.date is None:
                    continue
                page.set_date_state(other.date, approved=False, source=DATE_SOURCE_INHERITED)
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

    def record_generation(
        self,
        page_id: str,
        attempt: OCRAttempt,
        *,
        activate: bool = True,
    ) -> PageResult:
        with mutation_lock(self.paths.mutation_lock):
            existing = self._load_page_result_unlocked(page_id) or PageResult(page_id=page_id)
            before = PageResult.from_dict(existing.as_dict())
            # Replace same attempt_id if updating running→terminal; else append.
            replaced = False
            for i, old in enumerate(existing.attempts):
                if old.attempt_id == attempt.attempt_id:
                    existing.attempts[i] = attempt
                    replaced = True
                    break
            if not replaced:
                existing.attempts.append(attempt)
            existing.active_attempt_id = _active_after_generation(
                existing, attempt, activate=activate
            )
            if len(existing.attempts) > MAX_ATTEMPTS_RETAINED:
                existing.attempts = prune_attempts(
                    existing.attempts,
                    active_attempt_id=existing.active_attempt_id,
                    preferred_attempt_id=existing.preferred_attempt_id,
                )
            existing.updated_at = to_iso(self.clock.now())
            if attempt.status == "succeeded" and existing.edited_text is None:
                existing.effective_text_origin = _origin_from_active(existing)
            validate_page_result(existing, expected_page_id=page_id)
            write_json_atomic(self.paths.result_path(page_id), existing.as_dict())
            self._invalidate_review_unlocked(page_id, before=before, after=existing)
            return existing

    def set_active_attempt(
        self, page_id: str, attempt_id: str, *, record_ledger: bool = True
    ) -> PageResult:
        """Promote a succeeded attempt to active without clearing edited_text."""
        with mutation_lock(self.paths.mutation_lock):
            existing = self._load_page_result_unlocked(page_id)
            if existing is None:
                raise ProjectError(f"no page result for {page_id}")
            attempt = existing.attempt_by_id(attempt_id)
            if attempt is None:
                raise ProjectError(f"attempt {attempt_id!r} not found on {page_id}")
            if attempt.status != "succeeded":
                raise ProjectError(
                    f"only succeeded attempts can be activated (status={attempt.status})"
                )
            before = PageResult.from_dict(existing.as_dict())
            existing.active_attempt_id = attempt_id
            if existing.edited_text is None:
                existing.effective_text_origin = _origin_from_active(existing)
            existing.updated_at = to_iso(self.clock.now())
            validate_page_result(existing, expected_page_id=page_id)
            write_json_atomic(self.paths.result_path(page_id), existing.as_dict())
            self._invalidate_review_unlocked(page_id, before=before, after=existing)
            result = existing
            attempt_snap = attempt
        if record_ledger:
            self._append_preference_event(
                page_id=page_id,
                attempt=attempt_snap,
                action="promote",
            )
        return result

    def set_preferred_attempt(
        self,
        page_id: str,
        attempt_id: str,
        *,
        mode: str | None = None,
        edit_gate_choice: str | None = None,
        record_ledger: bool = True,
        action_override: str | None = None,
    ) -> PageResult:
        """Mark preferred; optionally promote per prefer_mode (A/B/C)."""
        resolved_mode = mode or self._resolved_prefer_mode()
        if resolved_mode not in PREFER_MODES:
            raise ProjectError(f"unsupported prefer_mode: {resolved_mode!r}")
        with mutation_lock(self.paths.mutation_lock):
            existing = self._load_page_result_unlocked(page_id)
            if existing is None:
                raise ProjectError(f"no page result for {page_id}")
            attempt = existing.attempt_by_id(attempt_id)
            if attempt is None:
                raise ProjectError(f"attempt {attempt_id!r} not found on {page_id}")
            if attempt.status != "succeeded":
                raise ProjectError(
                    f"only succeeded attempts can be preferred (status={attempt.status})"
                )
            existing.preferred_attempt_id = attempt_id
            promote = False
            if resolved_mode == "prefer_is_promote":
                promote = True
            elif resolved_mode == "prefer_only":
                promote = False
            elif resolved_mode == "prefer_promote_with_edit_gate":
                if existing.edited_text is not None:
                    if edit_gate_choice not in EDIT_GATE_CHOICES:
                        raise ProjectError(
                            "edit_gate_choice required when edited_text is set "
                            "(keep_edit|adopt_new)"
                        )
                    if edit_gate_choice == "adopt_new":
                        existing.edited_text = None
                    promote = True
                else:
                    promote = True
            before = PageResult.from_dict(existing.as_dict())
            if promote:
                existing.active_attempt_id = attempt_id
            if existing.edited_text is None:
                existing.effective_text_origin = _origin_from_active(existing)
            existing.updated_at = to_iso(self.clock.now())
            validate_page_result(existing, expected_page_id=page_id)
            write_json_atomic(self.paths.result_path(page_id), existing.as_dict())
            self._invalidate_review_unlocked(page_id, before=before, after=existing)
            result = existing
        if record_ledger:
            self._append_preference_event(
                page_id=page_id,
                attempt=attempt,
                action=action_override or ("prefer" if not promote else "prefer"),
            )
        return result

    def save_comparison(self, page_id: str, comparison: ComparisonRecord | None) -> PageResult:
        with mutation_lock(self.paths.mutation_lock):
            existing = self._load_page_result_unlocked(page_id)
            if existing is None:
                raise ProjectError(f"no page result for {page_id}")
            existing.comparison = comparison
            existing.updated_at = to_iso(self.clock.now())
            validate_page_result(existing, expected_page_id=page_id)
            write_json_atomic(self.paths.result_path(page_id), existing.as_dict())
            return existing

    def _resolved_prefer_mode(self) -> str:
        project = self.load()
        mode = getattr(project.settings, "prefer_mode", None) or DEFAULT_PREFER_MODE
        if mode in PREFER_MODES:
            return mode
        return DEFAULT_PREFER_MODE

    def _append_preference_event(
        self,
        *,
        page_id: str,
        attempt: OCRAttempt,
        action: str,
    ) -> None:
        try:
            from transcribe.services.ocr_preference_stats import append_preference_event

            project = self.load()
            append_preference_event(
                notebook_id=project.id,
                page_id=page_id,
                attempt_id=attempt.attempt_id,
                model_name=(attempt.provenance.model_name if attempt.provenance else ""),
                model_digest=(attempt.provenance.model_digest if attempt.provenance else None),
                attempt_kind=attempt.attempt_kind or "vision",
                action=action,
                pass_id=attempt.pass_id,
                clock=self.clock,
            )
        except Exception:
            # Ledger is best-effort; page mutation already committed.
            return

    def save_user_edit(
        self,
        page_id: str,
        edited_text: str | None,
        *,
        origin: str | None = None,
        mark_reviewed: bool = False,
    ) -> PageResult:
        if origin is not None and origin not in EFFECTIVE_TEXT_ORIGINS:
            raise ProjectError(f"unsupported effective_text_origin: {origin!r}")
        with mutation_lock(self.paths.mutation_lock):
            existing = self._load_page_result_unlocked(page_id)
            if existing is None:
                existing = PageResult(page_id=page_id)
            before = PageResult.from_dict(existing.as_dict())
            existing.edited_text = edited_text
            if origin is not None:
                existing.effective_text_origin = origin
            elif edited_text is None:
                existing.effective_text_origin = _origin_from_active(existing)
            existing.updated_at = to_iso(self.clock.now())
            if mark_reviewed:
                from transcribe.services.ocr_composite_state import (
                    evidence_fingerprint,
                    reviewed_text_fingerprint,
                )

                text = existing.effective_text() or ""
                existing.reviewed_text_fingerprint = reviewed_text_fingerprint(text)
                existing.reviewed_evidence_fingerprint = evidence_fingerprint(existing)
            validate_page_result(existing, expected_page_id=page_id)
            write_json_atomic(self.paths.result_path(page_id), existing.as_dict())
            if mark_reviewed:
                self._write_review_status_unlocked(page_id, "reviewed")
            else:
                self._invalidate_review_unlocked(page_id, before=before, after=existing)
            return existing

    def adopt_raw_as_edit(self, page_id: str) -> PageResult:
        """Clear edited_text so effective text becomes active raw."""
        return self.save_user_edit(page_id, None)

    def set_page_review_status(self, page_id: str, status: str) -> Project:
        """Set PageIndex.review_status. ``reviewed`` must go through save_user_edit."""
        if status not in REVIEW_STATUSES:
            raise ProjectError(f"unsupported review_status: {status!r}")
        if status == "reviewed":
            raise ProjectError("mark reviewed via save_user_edit(..., mark_reviewed=True)")
        with mutation_lock(self.paths.mutation_lock):
            return self._write_review_status_unlocked(page_id, status)

    def repair_empty_successes(self, page_id: str) -> PageResult | None:
        """Demote succeeded-but-empty vision attempts and restore a good active.

        Historical empty ``succeeded`` writes (e.g. DeepSeek-OCR + faithful prompt)
        become ``failed`` / ``empty_output``. If the active attempt has no text and
        another succeeded-with-text exists, that reading becomes current.
        """
        with mutation_lock(self.paths.mutation_lock):
            existing = self._load_page_result_unlocked(page_id)
            if existing is None:
                return None
            before = PageResult.from_dict(existing.as_dict())
            changed = False
            for i, attempt in enumerate(existing.attempts):
                if (attempt.attempt_kind or "vision") != "vision":
                    continue
                if attempt.status != "succeeded":
                    continue
                if (attempt.raw_text or "").strip():
                    continue
                attempt.status = "failed"
                attempt.error = AttemptError(
                    code=EMPTY_OUTPUT_CODE,
                    message=EMPTY_OUTPUT_MESSAGE,
                    retriable=False,
                )
                existing.attempts[i] = attempt
                changed = True
            active = existing.active_attempt()
            prior = _latest_succeeded_with_text(existing.attempts)
            if prior is not None and (
                active is None
                or active.status != "succeeded"
                or not (active.raw_text or "").strip()
            ):
                existing.active_attempt_id = prior.attempt_id
                if existing.edited_text is None:
                    existing.effective_text_origin = _origin_from_active(existing)
                changed = True
            if not changed:
                return existing
            existing.updated_at = to_iso(self.clock.now())
            validate_page_result(existing, expected_page_id=page_id)
            write_json_atomic(self.paths.result_path(page_id), existing.as_dict())
            self._invalidate_review_unlocked(page_id, before=before, after=existing)
            return existing

    def repair_review_validity(self, page_id: str) -> str:
        """If status is reviewed but fingerprints mismatch, move to needs_attention."""
        with mutation_lock(self.paths.mutation_lock):
            project = Project.from_dict(
                require_format(read_json(self.paths.manifest), "transcribe.project")
            )
            page = self._require_page(project, page_id)
            status = page.review_status or "unreviewed"
            result = self._load_page_result_unlocked(page_id)
            if status == "reviewed" and not _review_fingerprints_match(result):
                self._write_review_status_unlocked(page_id, "needs_attention")
                return "needs_attention"
            return status

    def _invalidate_review_unlocked(
        self,
        page_id: str,
        *,
        before: PageResult | None,
        after: PageResult,
    ) -> None:
        if not after.reviewed_text_fingerprint and not (
            before and before.reviewed_text_fingerprint
        ):
            return
        payload = require_format(read_json(self.paths.manifest), "transcribe.project")
        project = Project.from_dict(payload)
        page = next((p for p in project.pages if p.page_id == page_id), None)
        if page is None or (page.review_status or "unreviewed") != "reviewed":
            return
        if _review_should_invalidate(before, after):
            self._write_review_status_unlocked(page_id, "needs_attention")

    def _write_review_status_unlocked(self, page_id: str, status: str) -> Project:
        payload = require_format(read_json(self.paths.manifest), "transcribe.project")
        current = Project.from_dict(payload)
        page = self._require_page(current, page_id)
        page.review_status = status
        current.updated_at = to_iso(self.clock.now())
        validate_project(current)
        write_json_atomic(self.paths.manifest, current.as_dict())
        return current

    def cache_alignment_signals(
        self,
        page_id: str,
        *,
        source_disagreement_count: int,
        agreement_ratio: float,
    ) -> PageResult:
        with mutation_lock(self.paths.mutation_lock):
            existing = self._load_page_result_unlocked(page_id)
            if existing is None:
                existing = PageResult(page_id=page_id)
            existing.source_disagreement_count = int(source_disagreement_count)
            existing.agreement_ratio = float(agreement_ratio)
            existing.updated_at = to_iso(self.clock.now())
            validate_page_result(existing, expected_page_id=page_id)
            write_json_atomic(self.paths.result_path(page_id), existing.as_dict())
            return existing

    def reapply_visual_declutter(
        self,
        *,
        enabled: bool = True,
        on_progress: Callable[[int, int, str], None] | None = None,
        page_ids: Sequence[str] | None = None,
    ) -> DeclutterReapplyStats:
        """Re-run visual declutter on active renders; replace cropped pages.

        ``page_ids`` limits the run to those pages (notebook order of the given
        ids). ``None`` means every page. Creates a new ``render_id`` when pixels
        change. Provenance-only updates keep the existing render when bytes are
        unchanged. Refuses while an OCR job lock is held. Never restores
        already-cropped margins when ``enabled`` is False — that only records
        ``disabled`` provenance on current pixels.
        """
        from transcribe.declutter import apply_declutter
        from transcribe.domain.fingerprint import sha256_bytes
        from transcribe.domain.models import RenderProvenance
        from transcribe.persistence.atomic import write_bytes_atomic

        if job_lock_held(self.paths.job_lock):
            raise JobConflictError("cannot re-apply visual declutter while an OCR job is running")

        stats = DeclutterReapplyStats()
        with mutation_lock(self.paths.mutation_lock):
            payload = require_format(read_json(self.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            if page_ids is None:
                targets = list(current.pages)
            else:
                wanted = list(dict.fromkeys(page_ids))
                if not wanted:
                    raise ProjectError("page_ids must not be empty")
                by_id = {p.page_id: p for p in current.pages}
                missing = next((pid for pid in wanted if pid not in by_id), None)
                if missing is not None:
                    raise ProjectError(f"unknown page_id: {missing}")
                targets = [by_id[pid] for pid in wanted]
            stats.pages_total = len(targets)
            old_files: list[Path] = []
            thumb_files: list[Path] = []

            for index, page in enumerate(targets):
                if on_progress is not None:
                    on_progress(
                        index,
                        stats.pages_total,
                        f"Decluttering {page_label(current, page.page_id)}…",
                    )
                old = current.renders.get(page.active_render_id)
                if old is None:
                    stats.pages_error += 1
                    continue
                try:
                    img_path = self.paths.resolve_contained(old.image_relpath)
                    png = img_path.read_bytes()
                    result = apply_declutter(png, enabled=enabled)
                except Exception:  # noqa: BLE001 — keep going; count as error
                    stats.pages_error += 1
                    continue

                if result.state == "enabled_cropped":
                    stats.pages_cropped += 1
                elif result.state == "enabled_noop":
                    stats.pages_noop += 1
                elif result.state == "error_fallback":
                    stats.pages_error += 1
                else:
                    stats.pages_noop += 1

                pixels_changed = result.image_bytes != png
                if not pixels_changed:
                    stats.pages_unchanged += 1
                    updated = RenderProvenance(
                        render_id=old.render_id,
                        source_sha256=old.source_sha256,
                        pdf_page_index=old.pdf_page_index,
                        render_dpi=old.render_dpi,
                        renderer=old.renderer,
                        renderer_version=old.renderer_version,
                        rendered_image_sha256=old.rendered_image_sha256,
                        width=old.width,
                        height=old.height,
                        image_relpath=old.image_relpath,
                        **result.provenance_dict(),
                    )
                    current.renders[old.render_id] = updated
                    continue

                new_rid = self.ids.new_id()
                new_path = self.paths.page_render_path(page.source_id, page.page_index, new_rid)
                write_bytes_atomic(new_path, result.image_bytes)
                new_rel = self.paths.relativize(new_path)
                new_render = RenderProvenance(
                    render_id=new_rid,
                    source_sha256=old.source_sha256,
                    pdf_page_index=old.pdf_page_index,
                    render_dpi=old.render_dpi,
                    renderer=old.renderer,
                    renderer_version=old.renderer_version,
                    rendered_image_sha256=sha256_bytes(result.image_bytes),
                    width=result.width,
                    height=result.height,
                    image_relpath=new_rel,
                    **result.provenance_dict(),
                )
                current.renders[new_rid] = new_render
                del current.renders[old.render_id]
                page.active_render_id = new_rid
                page.width = result.width
                page.height = result.height
                old_files.append(img_path)
                thumb = self.paths.thumb_path(page.page_id)
                if thumb.exists():
                    thumb_files.append(thumb)
                grid_thumb = self.paths.grid_thumb_path(page.page_id)
                if grid_thumb.exists():
                    thumb_files.append(grid_thumb)

            current.updated_at = to_iso(self.clock.now())
            validate_project(current)
            write_json_atomic(self.paths.manifest, current.as_dict())

            for path in old_files:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            for path in thumb_files:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            # Active renders changed — rebuild disposable cover + grid thumbs.
            try:
                from transcribe.services.thumbnails import ThumbnailService

                ThumbnailService(self.paths).ensure_thumbs_for_pages(current)
            except Exception:  # noqa: BLE001
                pass
            if on_progress is not None:
                on_progress(
                    stats.pages_total,
                    stats.pages_total,
                    f"Finished → cropped {stats.pages_cropped}, unchanged {stats.pages_unchanged}",
                )
            return stats

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


def notebook_dir_slug(title: str) -> str:
    """Filesystem-safe folder name derived from a notebook display title."""
    raw = (title or "").strip() or "Untitled notebook"
    slug = re.sub(r"[^\w.\-()+ ]+", "_", raw, flags=re.UNICODE).strip(" .")
    slug = re.sub(r"\s+", "-", slug)
    return slug or "notebook"


def allocate_notebook_root(projects_dir: Path | str, title: str) -> Path:
    """Pick an unused directory under ``projects_dir`` for a new notebook."""
    projects = Path(projects_dir).expanduser().resolve()
    base = notebook_dir_slug(title)
    candidate = projects / base
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        alt = projects / f"{base}-{n}"
        if not alt.exists():
            return alt
        n += 1


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
        raise ProjectError(f"project root escapes projects directory: {root}") from exc

    if root == projects:
        raise ProjectError("refusing to delete projects directory itself; pass a notebook root")
    if not root.is_dir():
        raise ProjectError(f"project root is not a directory: {root}")
    if not (root / "project.json").is_file():
        raise ProjectError(f"missing project.json under {root}")

    job_lock = root / ".transcribe.job.lock"
    if job_lock_held(job_lock):
        raise JobConflictError("cannot delete notebook while an OCR job is running")

    # Brief exclusive section so concurrent mutators fail closed before removal.
    mutation = root / ".transcribe.lock"
    with mutation_lock(mutation):
        pass

    shutil.rmtree(root)
    return root
