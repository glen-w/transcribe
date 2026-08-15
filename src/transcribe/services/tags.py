"""Transcribe host for the organisation tag catalog (corpus rewrite, assignments)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from transcribe.corpus.paths import CorpusPaths
from transcribe.domain.models import Project
from transcribe.domain.validation import validate_project
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import analysis_lock_held, job_lock_held, mutation_lock
from transcribe.persistence.schema import SchemaError, require_format
from transcribe.ports import Clock, IdGenerator, SystemClock, UuidGenerator, to_iso
from transcribe.runtime_paths import RuntimePaths, build_runtime_paths
from transcribe.services.archive import bump_archive_generation, discover_corpus_project_roots
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.tagging.kernel import (
    RewritePlan,
    TagCatalog,
    TagDef,
    TagError,
    apply_rewrite,
    change_slug,
    delete_tag,
    display_tag,
    merge_tags,
    normalize_slugs,
    recolor,
    rename_label,
)
from transcribe.tagging.store import TagCatalogStore

AUTO_TAG_FORMAT = "transcribe.detection-auto-tag"
AUTO_TAG_FILENAME = "detection-auto-tag.json"


@dataclass
class RewriteResult:
    updated_notebooks: int = 0
    skipped_roots: list[str] = field(default_factory=list)
    unchanged_notebooks: int = 0


@dataclass
class UsageCounts:
    notebooks: dict[str, int] = field(default_factory=dict)
    pages: dict[str, int] = field(default_factory=dict)


class TagService:
    def __init__(
        self,
        runtime: RuntimePaths | None = None,
        *,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.runtime = runtime or build_runtime_paths()
        self.clock = clock or SystemClock()
        self.ids = ids or UuidGenerator()
        self.store = TagCatalogStore(self.runtime, clock=self.clock, ids=self.ids)

    def load_catalog(self) -> TagCatalog:
        return self.store.load().catalog

    def catalog_load(self):
        return self.store.load()

    def display(self, slug: str, catalog: TagCatalog | None = None) -> TagDef:
        return display_tag(catalog or self.load_catalog(), slug)

    def assign_page(
        self,
        projects: ProjectService,
        page_id: str,
        tags: Sequence[str],
        *,
        labels: Mapping[str, str] | None = None,
    ) -> Project:
        label_map = dict(labels or {})
        for raw in tags:
            slug = normalize_slugs([raw])
            if not slug:
                continue
            token = slug[0]
            cleaned = str(raw).strip()
            if cleaned and token not in label_map:
                label_map[token] = cleaned
        slugs = normalize_slugs(tags)
        self.store.ensure_slugs(slugs, labels=label_map)
        return projects.update_page_metadata(page_id, tags=slugs)

    def assign_notebook(
        self,
        projects: ProjectService,
        tags: Sequence[str],
        *,
        labels: Mapping[str, str] | None = None,
    ) -> Project:
        label_map = dict(labels or {})
        for raw in tags:
            slug = normalize_slugs([raw])
            if not slug:
                continue
            token = slug[0]
            cleaned = str(raw).strip()
            if cleaned and token not in label_map:
                label_map[token] = cleaned
        slugs = normalize_slugs(tags)
        self.store.ensure_slugs(slugs, labels=label_map)
        return projects.update_notebook_metadata(tags=slugs)

    def union_page_tags(
        self,
        projects: ProjectService,
        page_ids: Sequence[str],
        slug: str,
        *,
        label: str | None = None,
        color: str | None = None,
    ) -> int:
        """Add ``slug`` to each page (additive). Returns how many pages changed."""
        slugs = normalize_slugs([slug])
        if not slugs:
            return 0
        token = slugs[0]
        labels = {token: label} if label else None
        colors = {token: color} if color else None
        self.store.ensure_slugs([token], labels=labels, colors=colors)
        changed = 0
        wanted = set(page_ids)
        with mutation_lock(projects.paths.mutation_lock):
            payload = require_format(read_json(projects.paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            for page in current.pages:
                if page.page_id not in wanted:
                    continue
                if token in page.tags:
                    continue
                page.tags = normalize_slugs([*page.tags, token])
                changed += 1
            if changed:
                current.updated_at = to_iso(self.clock.now())
                validate_project(current)
                write_json_atomic(projects.paths.manifest, current.as_dict())
        if changed:
            bump_archive_generation(self.runtime)
        return changed

    def rename_label(self, tag_id: str, new_label: str) -> TagCatalog:
        loaded = self.store.load()
        if loaded.recovery:
            raise TagError(loaded.recovery_message or "tag catalog is in recovery")
        now = to_iso(self.clock.now())
        updated = rename_label(loaded.catalog, tag_id, new_label, now_iso=now)
        return self.store.save(updated)

    def recolor(self, tag_id: str, color: str) -> TagCatalog:
        loaded = self.store.load()
        if loaded.recovery:
            raise TagError(loaded.recovery_message or "tag catalog is in recovery")
        now = to_iso(self.clock.now())
        updated = recolor(loaded.catalog, tag_id, color, now_iso=now)
        return self.store.save(updated)

    def change_slug(self, tag_id: str, new_slug: str) -> tuple[TagCatalog, RewriteResult]:
        loaded = self.store.load()
        if loaded.recovery:
            raise TagError(loaded.recovery_message or "tag catalog is in recovery")
        now = to_iso(self.clock.now())
        updated, plan = change_slug(loaded.catalog, tag_id, new_slug, now_iso=now)
        saved = self.store.save(updated)
        result = self.rewrite_across_corpus(plan)
        return saved, result

    def merge(self, source_id: str, target_id: str) -> tuple[TagCatalog, RewriteResult]:
        loaded = self.store.load()
        if loaded.recovery:
            raise TagError(loaded.recovery_message or "tag catalog is in recovery")
        now = to_iso(self.clock.now())
        updated, plan = merge_tags(loaded.catalog, source_id, target_id, now_iso=now)
        saved = self.store.save(updated)
        result = self.rewrite_across_corpus(plan)
        return saved, result

    def delete(self, tag_id: str) -> tuple[TagCatalog, RewriteResult]:
        loaded = self.store.load()
        if loaded.recovery:
            raise TagError(loaded.recovery_message or "tag catalog is in recovery")
        now = to_iso(self.clock.now())
        updated, plan = delete_tag(loaded.catalog, tag_id, now_iso=now)
        saved = self.store.save(updated)
        result = self.rewrite_across_corpus(plan)
        return saved, result

    def rewrite_across_corpus(self, plan: RewritePlan) -> RewriteResult:
        result = RewriteResult()
        if plan.is_empty():
            return result
        corpus = CorpusPaths.from_runtime(self.runtime)
        corpus.ensure_layout()
        roots = discover_corpus_project_roots(self.runtime)
        with mutation_lock(corpus.lock_path):
            for root in roots:
                status = self._rewrite_notebook(root, plan)
                if status == "skipped":
                    result.skipped_roots.append(str(root))
                elif status == "updated":
                    result.updated_notebooks += 1
                else:
                    result.unchanged_notebooks += 1
        if result.updated_notebooks:
            bump_archive_generation(self.runtime)
        return result

    def _rewrite_notebook(self, root: Path, plan: RewritePlan) -> str:
        paths = open_project_paths(root)
        if job_lock_held(paths.job_lock) or analysis_lock_held(paths.analysis_lock):
            return "skipped"
        with mutation_lock(paths.mutation_lock):
            payload = require_format(read_json(paths.manifest), "transcribe.project")
            current = Project.from_dict(payload)
            changed = False
            new_nb = apply_rewrite(current.tags, plan)
            if new_nb != list(current.tags):
                current.tags = new_nb
                changed = True
            for page in current.pages:
                new_page = apply_rewrite(page.tags, plan)
                if new_page != list(page.tags):
                    page.tags = new_page
                    changed = True
            if not changed:
                return "unchanged"
            current.updated_at = to_iso(self.clock.now())
            validate_project(current)
            write_json_atomic(paths.manifest, current.as_dict())
        return "updated"

    def usage_counts(self) -> UsageCounts:
        counts = UsageCounts()
        for root in discover_corpus_project_roots(self.runtime):
            try:
                projects = ProjectService(open_project_paths(root), clock=self.clock, ids=self.ids)
                project = projects.load(reconcile=False)
            except (OSError, ValueError, TypeError, SchemaError):
                continue
            for slug in project.tags:
                counts.notebooks[slug] = counts.notebooks.get(slug, 0) + 1
            for page in project.pages:
                seen: set[str] = set()
                for slug in page.tags:
                    if slug in seen:
                        continue
                    seen.add(slug)
                    counts.pages[slug] = counts.pages.get(slug, 0) + 1
        return counts

    def auto_tag_path(self) -> Path:
        return self.runtime.data_dir / "config" / AUTO_TAG_FILENAME

    def auto_tag_map(self) -> dict[str, bool]:
        path = self.auto_tag_path()
        if not path.exists():
            return {}
        try:
            payload = read_json(path)
            require_format(payload, AUTO_TAG_FORMAT)
        except (OSError, ValueError, TypeError, SchemaError):
            return {}
        raw = payload.get("detectors") or {}
        if not isinstance(raw, dict):
            return {}
        return {str(k): bool(v) for k, v in raw.items()}

    def auto_tag_enabled(self, detector_id: str) -> bool:
        return bool(self.auto_tag_map().get(detector_id, False))

    def set_auto_tag(self, detector_id: str, enabled: bool) -> None:
        path = self.auto_tag_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        current = self.auto_tag_map()
        current[detector_id] = bool(enabled)
        write_json_atomic(
            path,
            {
                "format": AUTO_TAG_FORMAT,
                "schema_version": 1,
                "detectors": current,
            },
        )
