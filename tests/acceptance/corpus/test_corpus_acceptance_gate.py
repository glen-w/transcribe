from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.corpus import (
    CorpusIndexStore,
    CorpusPaths,
    ImportOrchestrator,
    ImportPlan,
    ImportPlanItem,
    POLICY_CREATE_DUPLICATE_V1,
    POLICY_SKIP_EXISTING_V1,
)
from transcribe.corpus.orchestrator import CrashHookTriggered
from transcribe.domain.fingerprint import sha256_bytes
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import read_json
from transcribe.services.corpus_doctor import CorpusDoctorService
from transcribe.services.corpus_registry import rebuild_index_from_projects
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def _corpus(tmp_path: Path) -> CorpusPaths:
    paths = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    paths.projects_dir.mkdir(parents=True)
    return paths


def _source(tmp_path: Path, name: str, *, color=(20, 40, 60)) -> tuple[Path, bytes]:
    data = _png_bytes(color=color)
    path = tmp_path / name
    path.write_bytes(data)
    return path, data


def _item(
    source_path: Path,
    data: bytes,
    *,
    item_id: str = "item1",
    op: str = "create_notebook",
    notebook_id: str = "nb-planned",
    source_id: str = "src-planned",
    page_id: str = "page-planned",
    render_id: str = "render-planned",
    managed_relpath: str | None = None,
) -> ImportPlanItem:
    provenance = {"source_path": str(source_path), "title": "planned"}
    if managed_relpath is not None:
        provenance["managed_relpath"] = managed_relpath
    return ImportPlanItem(
        item_id=item_id,
        op=op,
        notebook_id=notebook_id,
        source_sha256=sha256_bytes(data),
        media_type="image/png",
        page_indexes=[0],
        source_id=source_id,
        page_ids=[page_id],
        render_ids=[render_id],
        provenance=provenance,
        original_filename=source_path.name,
    )


def _plan(item: ImportPlanItem, *, policy: str = POLICY_SKIP_EXISTING_V1) -> ImportPlan:
    return ImportPlan(plan_id=f"plan-{item.item_id}", import_policy_id=policy, items=[item])


@pytest.mark.parametrize(
    "boundary",
    [
        "notebook_creation",
        "corpus_registration",
        "source_promotion",
        "render_promotion",
        "project_json_commit",
        "import_run_item_commit",
        "final_run_state",
    ],
)
def test_crash_injection_resume_is_idempotent(tmp_path: Path, boundary: str) -> None:
    corpus = _corpus(tmp_path)
    source_path, data = _source(tmp_path, f"{boundary}.png")
    item = _item(source_path, data, managed_relpath=f"nb-{boundary}")
    clock, ids = FakeClock(), SequentialIds("run")
    orchestrator = ImportOrchestrator(corpus, clock=clock, ids=ids)
    run = orchestrator.create_run_from_plan(_plan(item))

    seen: list[str] = []

    def crash_once(name: str) -> None:
        seen.append(name)
        if name == boundary:
            raise RuntimeError(f"boom at {name}")

    with pytest.raises(CrashHookTriggered):
        orchestrator.commit_run(run.import_run_id, crash_hook=crash_once)

    completed = orchestrator.commit_run(run.import_run_id)
    assert completed.status == "complete"
    assert completed.items[0].state == "committed"
    root = corpus.projects_dir / f"nb-{boundary}"
    project = ProjectService(open_project_paths(root), clock=clock, ids=ids).load(reconcile=False)
    assert [source.source_id for source in project.sources] == [item.source_id]
    assert [page.page_id for page in project.pages] == item.page_ids
    assert set(project.renders) == set(item.render_ids)

    retried = orchestrator.commit_run(run.import_run_id)
    assert retried.status == "complete"
    project = ProjectService(open_project_paths(root), clock=clock, ids=ids).load(reconcile=False)
    assert len(project.sources) == 1
    assert CorpusDoctorService(corpus).run(deep=True).ok
    assert boundary in seen


def _existing_notebook(corpus: CorpusPaths, tmp_path: Path):
    source_path, data = _source(tmp_path, "existing.png", color=(1, 2, 3))
    clock, ids = FakeClock(), SequentialIds("ex")
    paths = open_project_paths(corpus.projects_dir / "existing-nb")
    project = ProjectService(paths, clock=clock, ids=ids).create("existing")
    project = IngestService(paths, clock=clock, ids=ids).import_path(source_path)
    CorpusIndexStore(corpus, clock=clock).register_notebook(
        notebook_id=project.id,
        managed_relpath="existing-nb",
        project_id=project.id,
    )
    return project, source_path, data


def test_skip_existing_policy_skips_only_target_duplicate(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    project, source_path, data = _existing_notebook(corpus, tmp_path)
    item = _item(
        source_path,
        data,
        op="import_into_notebook",
        notebook_id=project.id,
        source_id="bulk-src",
        page_id="bulk-page",
        render_id="bulk-render",
    )
    orchestrator = ImportOrchestrator(corpus, clock=FakeClock(), ids=SequentialIds("skip"))
    run = orchestrator.create_run_from_plan(_plan(item, policy=POLICY_SKIP_EXISTING_V1))

    completed = orchestrator.commit_run(run.import_run_id)
    assert completed.status == "complete"
    assert completed.items[0].state == "skipped"
    assert completed.items[0].skip_classification == "same_bytes_same_notebook"
    loaded = ProjectService(
        open_project_paths(corpus.projects_dir / "existing-nb"),
        clock=FakeClock(),
        ids=SequentialIds("load"),
    ).load(reconcile=False)
    assert len(loaded.sources) == 1


def test_create_duplicate_policy_uses_preallocated_ids(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    project, source_path, data = _existing_notebook(corpus, tmp_path)
    item = _item(
        source_path,
        data,
        op="import_into_notebook",
        notebook_id=project.id,
        source_id="dup-src",
        page_id="dup-page",
        render_id="dup-render",
    )
    orchestrator = ImportOrchestrator(corpus, clock=FakeClock(), ids=SequentialIds("dup"))
    run = orchestrator.create_run_from_plan(_plan(item, policy=POLICY_CREATE_DUPLICATE_V1))

    completed = orchestrator.commit_run(run.import_run_id)
    assert completed.status == "complete"
    assert completed.items[0].state == "committed"
    loaded = ProjectService(
        open_project_paths(corpus.projects_dir / "existing-nb"),
        clock=FakeClock(),
        ids=SequentialIds("load"),
    ).load(reconcile=False)
    assert {source.source_id for source in loaded.sources} >= {"dup-src"}
    assert {page.page_id for page in loaded.pages} >= {"dup-page"}
    assert "dup-render" in loaded.renders


def test_corrupt_index_quarantine_and_rebuild(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    ids_seen: list[str] = []
    for name, prefix in (("a", "a"), ("b", "b")):
        paths = open_project_paths(corpus.projects_dir / name)
        project = ProjectService(paths, clock=FakeClock(), ids=SequentialIds(prefix)).create(name)
        ids_seen.append(project.id)
    corpus.ensure_layout()
    corpus.index_path.write_text("{not-json", encoding="utf-8")

    roots = rebuild_index_from_projects(corpus, clock=FakeClock())

    assert [root.name for root in roots] == ["a", "b"]
    quarantined = list(corpus.quarantine_dir.iterdir())
    assert len(quarantined) == 1
    index = read_json(corpus.index_path)
    assert [entry["notebook_id"] for entry in index["entries"]] == ids_seen
    doctor = CorpusDoctorService(corpus).run(deep=True)
    assert doctor.ok
    assert any(f.code == "corpus_quarantine_present" for f in doctor.findings)
    assert all(
        f.severity == "warning" for f in doctor.findings if f.code == "corpus_quarantine_present"
    )
