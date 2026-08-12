"""Duplicate classification and policy application for ImportPlan items."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from transcribe.corpus.index import CorpusIndexStore
from transcribe.corpus.paths import CorpusPaths
from transcribe.corpus.plan import (
    POLICY_CREATE_DUPLICATE_V1,
    POLICY_SKIP_EXISTING_V1,
    ImportPlanItem,
)
from transcribe.domain.models import Project
from transcribe.persistence.atomic import read_json
from transcribe.persistence.schema import require_format

CLASS_SAME_BYTES_SAME_NOTEBOOK = "same_bytes_same_notebook"
CLASS_SAME_BYTES_OTHER_NOTEBOOK = "same_bytes_other_notebook"
CLASS_SAME_FILENAME_DIFFERENT_BYTES = "same_filename_different_bytes"
CLASS_NOVEL = "novel"


@dataclass(frozen=True)
class DuplicateClassification:
    classification: str
    notebook_id: str | None = None
    source_id: str | None = None
    page_ids: list[str] = field(default_factory=list)
    render_ids: list[str] = field(default_factory=list)

    @property
    def should_skip_existing(self) -> bool:
        return self.classification == CLASS_SAME_BYTES_SAME_NOTEBOOK

    def resulting_ids(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.notebook_id is not None:
            payload["notebook_id"] = self.notebook_id
        if self.source_id is not None:
            payload["source_id"] = self.source_id
        if self.page_ids:
            payload["page_ids"] = list(self.page_ids)
        if self.render_ids:
            payload["render_ids"] = list(self.render_ids)
        return payload


def should_skip_for_policy(
    classification: DuplicateClassification, import_policy_id: str
) -> bool:
    if import_policy_id == POLICY_SKIP_EXISTING_V1:
        return classification.should_skip_existing
    if import_policy_id == POLICY_CREATE_DUPLICATE_V1:
        return False
    return False


def classify_duplicate(
    corpus_paths: CorpusPaths,
    item: ImportPlanItem,
    *,
    target_project: Project | None = None,
) -> DuplicateClassification:
    """Classify source SHA/name against registered notebooks before policy."""
    target = target_project
    target_root: Path | None = None
    others: list[tuple[str, Project]] = []

    store = CorpusIndexStore(corpus_paths)
    index = store.load()
    if index is not None:
        for entry in index.entries:
            try:
                root = corpus_paths.resolve_managed(entry.managed_relpath)
                project = _load_project(root)
            except Exception:
                continue
            if entry.notebook_id == item.notebook_id:
                target = target or project
                target_root = root
            else:
                others.append((entry.notebook_id, project))

    if target is not None:
        same = _source_by_sha(target, item.source_sha256)
        if same is not None:
            return _source_classification(
                CLASS_SAME_BYTES_SAME_NOTEBOOK,
                target.id,
                target,
                same.source_id,
            )
        if _same_filename_different_bytes(target, item):
            return DuplicateClassification(
                classification=CLASS_SAME_FILENAME_DIFFERENT_BYTES,
                notebook_id=target.id,
            )

    for notebook_id, project in others:
        same = _source_by_sha(project, item.source_sha256)
        if same is not None:
            return _source_classification(
                CLASS_SAME_BYTES_OTHER_NOTEBOOK,
                notebook_id,
                project,
                same.source_id,
            )

    # If there is no index yet, target_project is authoritative for the target.
    _ = target_root
    return DuplicateClassification(classification=CLASS_NOVEL, notebook_id=item.notebook_id)


def _load_project(root: Path) -> Project:
    payload = require_format(read_json(root / "project.json"), "transcribe.project")
    return Project.from_dict(payload)


def _source_by_sha(project: Project, sha256: str):
    for source in project.sources:
        if source.sha256 == sha256:
            return source
    return None


def _same_filename_different_bytes(project: Project, item: ImportPlanItem) -> bool:
    name = (item.original_filename or "").casefold()
    if not name:
        return False
    for source in project.sources:
        if source.original_filename.casefold() == name and source.sha256 != item.source_sha256:
            return True
    return False


def _source_classification(
    classification: str,
    notebook_id: str,
    project: Project,
    source_id: str,
) -> DuplicateClassification:
    pages = [p for p in project.pages if p.source_id == source_id]
    return DuplicateClassification(
        classification=classification,
        notebook_id=notebook_id,
        source_id=source_id,
        page_ids=[p.page_id for p in pages],
        render_ids=[p.active_render_id for p in pages],
    )
