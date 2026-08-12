from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.corpus import (
    CorpusIndexStore,
    CorpusPaths,
    ImportPlan,
    ImportPlanItem,
    POLICY_CREATE_DUPLICATE_V1,
    POLICY_SKIP_EXISTING_V1,
    validate_import_plan,
)
from transcribe.corpus.duplicates import (
    CLASS_NOVEL,
    CLASS_SAME_BYTES_OTHER_NOTEBOOK,
    CLASS_SAME_BYTES_SAME_NOTEBOOK,
    CLASS_SAME_FILENAME_DIFFERENT_BYTES,
    classify_duplicate,
)
from transcribe.domain.fingerprint import sha256_bytes
from transcribe.errors import ValidationError
from transcribe.ingest import IngestService
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def _plan_item(**overrides) -> ImportPlanItem:
    data = {
        "item_id": "item1",
        "op": "import_into_notebook",
        "notebook_id": "nb1",
        "source_sha256": "a" * 64,
        "media_type": "image/png",
        "page_indexes": [0],
        "source_id": "src1",
        "page_ids": ["page1"],
        "render_ids": ["render1"],
        "provenance": {"source_path": "/tmp/a.png"},
        "original_filename": "a.png",
    }
    data.update(overrides)
    return ImportPlanItem(**data)


def test_import_plan_validate_accepts_preallocated_ids() -> None:
    plan = ImportPlan(
        plan_id="plan1",
        import_policy_id=POLICY_SKIP_EXISTING_V1,
        items=[_plan_item()],
    )
    validate_import_plan(plan)


def test_import_plan_validate_rejects_ordering_ambiguity() -> None:
    plan = ImportPlan(
        plan_id="plan1",
        import_policy_id=POLICY_SKIP_EXISTING_V1,
        items=[_plan_item(page_indexes=[0, 0], page_ids=["p1", "p2"], render_ids=["r1", "r2"])],
    )
    with pytest.raises(ValidationError, match="duplicates"):
        validate_import_plan(plan)


def test_import_plan_validate_rejects_missing_preallocated_ids() -> None:
    plan = ImportPlan(
        plan_id="plan1",
        import_policy_id=POLICY_SKIP_EXISTING_V1,
        items=[_plan_item(source_id="")],
    )
    with pytest.raises(ValidationError, match="source_id"):
        validate_import_plan(plan)


def test_import_plan_fingerprint_ignores_provenance() -> None:
    item_a = _plan_item(provenance={"source_path": "/mnt/a.png"})
    item_b = _plan_item(provenance={"source_path": "/mnt/moved/a.png"})
    plan_a = ImportPlan(
        plan_id="plan1",
        import_policy_id=POLICY_CREATE_DUPLICATE_V1,
        items=[item_a],
    )
    plan_b = ImportPlan(
        plan_id="plan1",
        import_policy_id=POLICY_CREATE_DUPLICATE_V1,
        items=[item_b],
    )
    assert plan_a.fingerprint() == plan_b.fingerprint()


def _registered_project(
    corpus: CorpusPaths,
    name: str,
    *,
    prefix: str,
    filename: str | None = None,
    data: bytes | None = None,
):
    root = corpus.projects_dir / name
    clock, ids = FakeClock(), SequentialIds(prefix)
    paths = open_project_paths(root)
    project = ProjectService(paths, clock=clock, ids=ids).create(name)
    if data is not None:
        project = IngestService(paths, clock=clock, ids=ids).import_bytes(
            filename or "note.png", data
        )
    CorpusIndexStore(corpus, clock=clock).register_notebook(
        notebook_id=project.id,
        managed_relpath=name,
        project_id=project.id,
    )
    return project


def test_duplicate_classification_taxonomy(tmp_path: Path) -> None:
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    first = _png_bytes(color=(1, 2, 3))
    second = _png_bytes(color=(4, 5, 6))

    nb1 = _registered_project(
        corpus, "nb1", prefix="a", filename="note.png", data=first
    )
    nb2 = _registered_project(
        corpus, "nb2", prefix="b", filename="note.png", data=second
    )

    same_target = _plan_item(
        notebook_id=nb1.id,
        source_sha256=sha256_bytes(first),
        original_filename="copy.png",
    )
    assert (
        classify_duplicate(corpus, same_target).classification
        == CLASS_SAME_BYTES_SAME_NOTEBOOK
    )

    other_target = _plan_item(
        notebook_id=nb2.id,
        source_sha256=sha256_bytes(first),
        original_filename="other-name.png",
    )
    assert (
        classify_duplicate(corpus, other_target).classification
        == CLASS_SAME_BYTES_OTHER_NOTEBOOK
    )

    filename_collision = _plan_item(
        notebook_id=nb2.id,
        source_sha256=sha256_bytes(first),
        original_filename="note.png",
    )
    assert (
        classify_duplicate(corpus, filename_collision).classification
        == CLASS_SAME_FILENAME_DIFFERENT_BYTES
    )

    novel = _plan_item(
        notebook_id=nb2.id,
        source_sha256=sha256_bytes(_png_bytes(color=(9, 9, 9))),
        original_filename="novel.png",
    )
    assert classify_duplicate(corpus, novel).classification == CLASS_NOVEL
