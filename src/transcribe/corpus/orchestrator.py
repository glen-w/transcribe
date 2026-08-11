"""ImportRun orchestrator for notebook corpus bulk import."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

import pymupdf
from PIL import Image

from transcribe.corpus.duplicates import classify_duplicate, should_skip_for_policy
from transcribe.corpus.import_run import (
    ImportRun,
    ImportRunItemOutcome,
    ImportRunStore,
    TERMINAL_STATUSES,
)
from transcribe.corpus.index import (
    CorpusEntry,
    CorpusIndex,
    CorpusIndexStore,
    ordered_corpus_then_notebook_lock,
    validate_corpus_index,
)
from transcribe.corpus.paths import CorpusPaths
from transcribe.corpus.plan import (
    OP_CREATE_NOTEBOOK,
    OP_IMPORT_INTO_NOTEBOOK,
    ImportPlan,
    ImportPlanItem,
    validate_import_plan,
)
from transcribe.domain.fingerprint import sha256_bytes
from transcribe.domain.models import PageIndex, Project, RenderProvenance, SourceDocument
from transcribe.domain.validation import validate_project
from transcribe.errors import CorpusError, IngestError, ValidationError
from transcribe.ingest import (
    DEFAULT_RENDER_DPI,
    MAX_RENDERED_BYTES,
    MAX_SOURCE_BYTES,
    _apply_visual_declutter,
    _detect_media,
    _ensure_disk_budget,
    _load_image_bytes,
    _promote_replace,
    _render_pdf_page,
    is_cover_filename,
    sanitize_filename,
)
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import read_json, write_bytes_atomic, write_json_atomic
from transcribe.persistence.locks import mutation_lock
from transcribe.persistence.schema import require_format
from transcribe.ports import Clock, IdGenerator, to_iso
from transcribe.services.project import _seed_ocr_settings, open_project_paths

CrashHook = Callable[[str], None]


class CrashHookTriggered(RuntimeError):
    """Raised when a test crash hook interrupts a durable boundary."""


class ImportOrchestrator:
    def __init__(
        self,
        corpus_paths: CorpusPaths,
        *,
        clock: Clock,
        ids: IdGenerator,
        default_dpi: int = DEFAULT_RENDER_DPI,
        visual_declutter_enabled: bool = True,
    ) -> None:
        self.paths = corpus_paths
        self.clock = clock
        self.ids = ids
        self.default_dpi = default_dpi
        self.visual_declutter_enabled = visual_declutter_enabled
        self.runs = ImportRunStore(corpus_paths)

    def create_run_from_plan(self, plan: ImportPlan) -> ImportRun:
        validate_import_plan(plan)
        now = to_iso(self.clock.now())
        run = ImportRun(
            import_run_id=self.ids.new_id(),
            plan_id=plan.plan_id,
            plan_fingerprint=plan.fingerprint(),
            import_policy_id=plan.import_policy_id,
            created_at=now,
            updated_at=now,
            status="pending",
            plan_schema_version=plan.schema_version,
            items=[
                ImportRunItemOutcome(item_id=item.item_id, state="pending")
                for item in plan.items
            ],
            plan_body=plan.as_dict(include_provenance=True),
        )
        self.runs.save(run)
        return run

    def commit_run(
        self,
        import_run_id: str,
        *,
        cancel: bool = False,
        crash_hook: CrashHook | None = None,
    ) -> ImportRun:
        run = self.runs.load(import_run_id)
        if run.status in TERMINAL_STATUSES:
            return run
        if not run.plan_body:
            raise CorpusError(f"import run {import_run_id} has no plan_body")
        plan = ImportPlan.from_dict(run.plan_body)
        validate_import_plan(plan)
        if plan.fingerprint() != run.plan_fingerprint:
            raise CorpusError(f"import run {import_run_id} plan fingerprint mismatch")

        run.status = "running"
        run.updated_at = to_iso(self.clock.now())
        self.runs.save(run)

        if cancel:
            run = self._cancel_pending(run)
        else:
            for item in plan.items:
                run = self.runs.load(import_run_id)
                if self._outcome_state(run, item.item_id) in {"committed", "skipped"}:
                    continue
                try:
                    run = self._commit_item(run, item, crash_hook=crash_hook)
                except CrashHookTriggered:
                    raise
                except Exception as exc:
                    run = self._set_outcome(
                        run,
                        ImportRunItemOutcome(
                            item_id=item.item_id,
                            state="failed",
                            resulting_ids=self._planned_ids(item),
                            error_code=type(exc).__name__,
                            error_message=str(exc),
                        ),
                    )

        run = self._finalize_run(run, cancel=cancel)
        self._hook(crash_hook, "final_run_state")
        return run

    def _commit_item(
        self,
        run: ImportRun,
        item: ImportPlanItem,
        *,
        crash_hook: CrashHook | None,
    ) -> ImportRun:
        root = self._root_for_item(item)
        if item.op == OP_CREATE_NOTEBOOK:
            root = self._ensure_created_notebook(item, root, crash_hook=crash_hook)
        elif item.op != OP_IMPORT_INTO_NOTEBOOK:
            raise ValidationError(f"unknown import op: {item.op!r}")

        project = self._load_project(root)
        if self._project_has_planned_item(project, item):
            return self._set_outcome(
                run,
                ImportRunItemOutcome(
                    item_id=item.item_id,
                    state="committed",
                    resulting_ids=self._planned_ids(item),
                ),
                crash_hook=crash_hook,
            )

        classification = classify_duplicate(self.paths, item, target_project=project)
        if should_skip_for_policy(classification, run.import_policy_id):
            return self._set_outcome(
                run,
                ImportRunItemOutcome(
                    item_id=item.item_id,
                    state="skipped",
                    resulting_ids=classification.resulting_ids(),
                    skip_classification=classification.classification,
                ),
                crash_hook=crash_hook,
            )

        project_paths = open_project_paths(root)
        self._commit_source(project_paths, item, run.import_run_id, crash_hook=crash_hook)
        return self._set_outcome(
            run,
            ImportRunItemOutcome(
                item_id=item.item_id,
                state="committed",
                resulting_ids=self._planned_ids(item),
                skip_classification=classification.classification,
            ),
            crash_hook=crash_hook,
        )

    def _ensure_created_notebook(
        self,
        item: ImportPlanItem,
        root: Path,
        *,
        crash_hook: CrashHook | None,
    ) -> Path:
        project_paths = open_project_paths(root)
        now = to_iso(self.clock.now())
        with ordered_corpus_then_notebook_lock(
            self.paths.lock_path, project_paths.mutation_lock
        ):
            if project_paths.manifest.exists():
                project = self._load_project(root)
                if project.id != item.notebook_id:
                    raise CorpusError(
                        f"existing project id {project.id!r} != planned {item.notebook_id!r}"
                    )
            else:
                project = Project(
                    id=item.notebook_id,
                    title=self._notebook_title(item),
                    created_at=now,
                    updated_at=now,
                    settings=_seed_ocr_settings(),
                )
                validate_project(project)
                write_json_atomic(project_paths.manifest, project.as_dict())
                self._hook(crash_hook, "notebook_creation")
            self._register_notebook_unlocked(item.notebook_id, root, project_id=item.notebook_id)
            self._hook(crash_hook, "corpus_registration")
        return root

    def _commit_source(
        self,
        project_paths: ProjectPaths,
        item: ImportPlanItem,
        import_run_id: str,
        *,
        crash_hook: CrashHook | None,
    ) -> None:
        self._ensure_no_live_journal(project_paths)
        data, safe_name, source_path = self._source_bytes(project_paths, item)
        if len(data) > MAX_SOURCE_BYTES:
            raise IngestError(f"source exceeds maximum size of {MAX_SOURCE_BYTES} bytes")
        source_sha = sha256_bytes(data)
        if source_sha != item.source_sha256:
            raise IngestError(f"source SHA mismatch for {item.item_id}")
        media = _detect_media(data, safe_name)
        if media != item.media_type:
            raise IngestError(
                f"media_type mismatch for {item.item_id}: plan={item.media_type!r} actual={media!r}"
            )
        dpi = self._render_dpi(item)
        _ensure_disk_budget(project_paths.root, additional=len(data))

        staging = project_paths.staging_attempt_dir(f"bulk-{import_run_id}-{item.item_id}")
        staging.mkdir(parents=True, exist_ok=True)
        final_source = project_paths.sources_dir / f"{item.source_id}-{safe_name}"
        source_rel = project_paths.relativize(final_source)
        page_entries: list[dict[str, Any]] = []
        rendered_budget = 0
        try:
            if not final_source.exists():
                staged_source = staging / safe_name
                write_bytes_atomic(staged_source, data)
                _promote_replace(staged_source, final_source)
            elif sha256_bytes(final_source.read_bytes()) != item.source_sha256:
                raise IngestError(f"managed source collision for {item.source_id}")
            self._hook(crash_hook, "source_promotion")

            renderer_version = getattr(pymupdf, "VersionBind", "unknown")
            pillow_version = getattr(Image, "__version__", "unknown")
            is_pdf = media == "application/pdf"

            if is_pdf:
                doc = pymupdf.open(stream=data, filetype="pdf")
            else:
                doc = None
            try:
                for pos, page_index in enumerate(item.page_indexes):
                    if is_pdf:
                        assert doc is not None
                        png, _w, _h = _render_pdf_page(doc, page_index, dpi)
                        renderer = "pymupdf"
                        version = str(renderer_version)
                        pdf_page_index = page_index
                    else:
                        if page_index != 0:
                            raise IngestError("image imports must use page_index 0")
                        png, _w, _h, _sha = _load_image_bytes(data)
                        renderer = "pillow"
                        version = str(pillow_version)
                        pdf_page_index = None
                    png, width, height, png_sha, declutter = _apply_visual_declutter(
                        png, enabled=self.visual_declutter_enabled
                    )
                    rendered_budget += len(png)
                    if rendered_budget > MAX_RENDERED_BYTES:
                        raise IngestError(
                            f"rendered output exceeds maximum of {MAX_RENDERED_BYTES} bytes"
                        )
                    _ensure_disk_budget(project_paths.root, additional=len(png))
                    render_id = item.render_ids[pos]
                    final_png = project_paths.page_render_path(
                        item.source_id, page_index, render_id
                    )
                    if final_png.exists():
                        if sha256_bytes(final_png.read_bytes()) != png_sha:
                            raise IngestError(f"managed render collision for {render_id}")
                    else:
                        staged_png = staging / f"{page_index:04d}-{render_id}.png"
                        write_bytes_atomic(staged_png, png)
                        _promote_replace(staged_png, final_png)
                    entry: dict[str, Any] = {
                        "page_id": item.page_ids[pos],
                        "page_index": page_index,
                        "render_id": render_id,
                        "width": width,
                        "height": height,
                        "png_sha": png_sha,
                        "pdf_page_index": pdf_page_index,
                        "final_rel": project_paths.relativize(final_png),
                        "renderer": renderer,
                        "renderer_version": version,
                        "source_sha256": source_sha,
                        "render_dpi": dpi,
                    }
                    entry.update(declutter)
                    page_entries.append(entry)
            finally:
                if doc is not None:
                    doc.close()
            self._hook(crash_hook, "render_promotion")

            with mutation_lock(project_paths.mutation_lock):
                payload = require_format(
                    read_json(project_paths.manifest), "transcribe.project"
                )
                project = Project.from_dict(payload)
                if not self._project_has_planned_item(project, item):
                    self._check_id_collisions(project, item)
                    new_pages: list[PageIndex] = []
                    new_renders: dict[str, RenderProvenance] = {}
                    for entry in page_entries:
                        rid = entry["render_id"]
                        new_renders[rid] = self._render_from_entry(entry)
                        new_pages.append(
                            PageIndex(
                                page_id=entry["page_id"],
                                source_id=item.source_id,
                                page_index=entry["page_index"],
                                active_render_id=rid,
                                width=entry["width"],
                                height=entry["height"],
                            )
                        )
                    now = to_iso(self.clock.now())
                    project.sources.append(
                        SourceDocument(
                            source_id=item.source_id,
                            original_filename=safe_name,
                            stored_relpath=source_rel,
                            media_type=media,
                            sha256=source_sha,
                            page_count=len(new_pages),
                            imported_at=now,
                            render_dpi=dpi,
                            original_path=str(source_path) if source_path else None,
                            source_size_bytes=len(data),
                            import_run_id=import_run_id,
                        )
                    )
                    project.pages.extend(new_pages)
                    project.renders.update(new_renders)
                    if (
                        project.cover_page_id is None
                        and new_pages
                        and is_cover_filename(safe_name)
                        and media.startswith("image/")
                    ):
                        project.cover_page_id = new_pages[0].page_id
                    project.updated_at = now
                    validate_project(project, paths=project_paths)
                    write_json_atomic(project_paths.manifest, project.as_dict())
            self._hook(crash_hook, "project_json_commit")
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _source_bytes(
        self, project_paths: ProjectPaths, item: ImportPlanItem
    ) -> tuple[bytes, str, Path | None]:
        safe_name = sanitize_filename(item.original_filename or "source")
        final_source = project_paths.sources_dir / f"{item.source_id}-{safe_name}"
        if final_source.exists():
            return final_source.read_bytes(), safe_name, None
        provenance = item.provenance or {}
        raw = provenance.get("source_path") or provenance.get("original_path") or provenance.get("path")
        if not raw:
            raise IngestError(f"{item.item_id} provenance.source_path is required")
        source_path = Path(str(raw)).expanduser()
        data = source_path.read_bytes()
        return data, safe_name, source_path

    def _ensure_no_live_journal(self, paths: ProjectPaths) -> None:
        if not paths.ingest_journal.exists():
            return
        from transcribe.ingest import IngestService

        IngestService(
            paths,
            clock=self.clock,
            ids=self.ids,
            visual_declutter_enabled=self.visual_declutter_enabled,
        ).recover_incomplete_ingest(
            visual_declutter_enabled=self.visual_declutter_enabled
        )
        if paths.ingest_journal.exists():
            raise CorpusError(f"live ingest journal already exists: {paths.ingest_journal}")

    def _register_notebook_unlocked(
        self, notebook_id: str, root: Path, *, project_id: str
    ) -> None:
        if notebook_id != project_id:
            raise ValidationError(f"notebook_id {notebook_id!r} != project_id {project_id!r}")
        rel = root.resolve().relative_to(self.paths.projects_dir.resolve()).as_posix()
        now = to_iso(self.clock.now())
        if self.paths.index_path.exists():
            index = CorpusIndex.from_dict(read_json(self.paths.index_path))
        else:
            index = CorpusIndex(updated_at=now, entries=[])
        for entry in index.entries:
            if entry.notebook_id == notebook_id:
                entry.managed_relpath = rel
                entry.updated_at = now
                index.updated_at = now
                validate_corpus_index(index, paths=self.paths)
                write_json_atomic(self.paths.index_path, index.as_dict())
                return
            if entry.managed_relpath == rel:
                raise CorpusError(f"managed_relpath already registered: {rel}")
        index.entries.append(
            CorpusEntry(
                notebook_id=notebook_id,
                managed_relpath=rel,
                registered_at=now,
                updated_at=now,
            )
        )
        index.updated_at = now
        validate_corpus_index(index, paths=self.paths)
        self.paths.ensure_layout()
        write_json_atomic(self.paths.index_path, index.as_dict())

    def _root_for_item(self, item: ImportPlanItem) -> Path:
        if item.op == OP_CREATE_NOTEBOOK:
            rel = (item.provenance or {}).get("managed_relpath")
            managed_rel = str(rel).strip() if rel else item.notebook_id
            return self.paths.resolve_managed(managed_rel)
        index = CorpusIndexStore(self.paths).load()
        if index is None:
            raise CorpusError("corpus index is absent; cannot import into notebook")
        for entry in index.entries:
            if entry.notebook_id == item.notebook_id:
                return self.paths.resolve_managed(entry.managed_relpath)
        raise CorpusError(f"notebook not registered in corpus: {item.notebook_id}")

    def _load_project(self, root: Path) -> Project:
        payload = require_format(read_json(root / "project.json"), "transcribe.project")
        project = Project.from_dict(payload)
        validate_project(project)
        return project

    def _project_has_planned_item(self, project: Project, item: ImportPlanItem) -> bool:
        if not any(source.source_id == item.source_id for source in project.sources):
            return False
        page_ids = {p.page_id for p in project.pages}
        render_ids = set(project.renders)
        return set(item.page_ids).issubset(page_ids) and set(item.render_ids).issubset(
            render_ids
        )

    def _check_id_collisions(self, project: Project, item: ImportPlanItem) -> None:
        if any(source.source_id == item.source_id for source in project.sources):
            raise CorpusError(f"source_id collision: {item.source_id}")
        page_ids = {p.page_id for p in project.pages}
        render_ids = set(project.renders)
        for page_id in item.page_ids:
            if page_id in page_ids:
                raise CorpusError(f"page_id collision: {page_id}")
        for render_id in item.render_ids:
            if render_id in render_ids:
                raise CorpusError(f"render_id collision: {render_id}")

    def _render_from_entry(self, entry: dict[str, Any]) -> RenderProvenance:
        return RenderProvenance(
            render_id=entry["render_id"],
            source_sha256=entry["source_sha256"],
            pdf_page_index=entry["pdf_page_index"],
            render_dpi=entry["render_dpi"],
            renderer=entry["renderer"],
            renderer_version=entry["renderer_version"],
            rendered_image_sha256=entry["png_sha"],
            width=entry["width"],
            height=entry["height"],
            image_relpath=entry["final_rel"],
            declutter_state=entry.get("declutter_state"),
            declutter_version=entry.get("declutter_version"),
            declutter_ops=entry.get("declutter_ops"),
            declutter_identity_sha256=entry.get("declutter_identity_sha256"),
            declutter_params=entry.get("declutter_params"),
            declutter_original_width=entry.get("declutter_original_width"),
            declutter_original_height=entry.get("declutter_original_height"),
            declutter_crop_left=entry.get("declutter_crop_left"),
            declutter_crop_top=entry.get("declutter_crop_top"),
            declutter_crop_right=entry.get("declutter_crop_right"),
            declutter_crop_bottom=entry.get("declutter_crop_bottom"),
            declutter_inset_left=entry.get("declutter_inset_left"),
            declutter_inset_top=entry.get("declutter_inset_top"),
            declutter_inset_right=entry.get("declutter_inset_right"),
            declutter_inset_bottom=entry.get("declutter_inset_bottom"),
            declutter_note=entry.get("declutter_note"),
        )

    def _set_outcome(
        self,
        run: ImportRun,
        outcome: ImportRunItemOutcome,
        *,
        crash_hook: CrashHook | None = None,
    ) -> ImportRun:
        replaced = False
        for idx, existing in enumerate(run.items):
            if existing.item_id == outcome.item_id:
                run.items[idx] = outcome
                replaced = True
                break
        if not replaced:
            run.items.append(outcome)
        run.updated_at = to_iso(self.clock.now())
        self.runs.save(run)
        self._hook(crash_hook, "import_run_item_commit")
        return run

    def _cancel_pending(self, run: ImportRun) -> ImportRun:
        changed = False
        for item in run.items:
            if item.state in {"pending", "failed"}:
                item.state = "cancelled_pending"
                changed = True
        if changed:
            run.updated_at = to_iso(self.clock.now())
            self.runs.save(run)
        return run

    def _finalize_run(self, run: ImportRun, *, cancel: bool) -> ImportRun:
        states = [item.state for item in run.items]
        committed = any(state == "committed" for state in states)
        failures = any(state == "failed" for state in states)
        cancelled = any(state == "cancelled_pending" for state in states)
        if cancel:
            run.status = "cancelled_with_commits" if committed else "cancelled"
        elif failures or cancelled:
            run.status = "partial" if committed else "failed"
        else:
            run.status = "complete"
        run.updated_at = to_iso(self.clock.now())
        self.runs.save(run)
        return run

    def _outcome_state(self, run: ImportRun, item_id: str) -> str | None:
        for item in run.items:
            if item.item_id == item_id:
                return item.state
        return None

    def _planned_ids(self, item: ImportPlanItem) -> dict[str, Any]:
        return {
            "notebook_id": item.notebook_id,
            "source_id": item.source_id,
            "page_ids": list(item.page_ids),
            "render_ids": list(item.render_ids),
        }

    def _notebook_title(self, item: ImportPlanItem) -> str:
        prov = item.provenance or {}
        title = str(prov.get("title") or "").strip()
        return title or item.original_filename or "Imported notebook"

    def _render_dpi(self, item: ImportPlanItem) -> int:
        raw = (item.provenance or {}).get("render_dpi")
        return int(raw) if raw is not None else self.default_dpi

    def _hook(self, crash_hook: CrashHook | None, boundary: str) -> None:
        if crash_hook is not None:
            try:
                crash_hook(boundary)
            except Exception as exc:
                raise CrashHookTriggered(boundary) from exc


__all__ = ["CrashHookTriggered", "ImportOrchestrator"]
