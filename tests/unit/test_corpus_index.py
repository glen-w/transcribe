"""Corpus index and ImportRun foundation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.corpus import (
    CorpusIndexStore,
    CorpusPaths,
    ImportRun,
    ImportRunStore,
    compute_plan_fingerprint,
    plans_are_idempotent_retries,
    validate_entry_matches_project,
)
from transcribe.corpus.import_run import ImportRunItemOutcome
from transcribe.errors import CorpusError, ValidationError
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import write_json_atomic
from transcribe.services.corpus_doctor import CorpusDoctorService
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def test_corpus_index_register_and_order(tmp_path: Path):
    runtime_data = tmp_path / "data"
    projects = runtime_data / "projects"
    projects.mkdir(parents=True)
    paths = CorpusPaths(data_dir=runtime_data, projects_dir=projects)
    store = CorpusIndexStore(paths, clock=FakeClock())

    nb = projects / "nb-a"
    nb.mkdir()
    write_json_atomic(
        nb / "project.json",
        {
            "format": "transcribe.project",
            "schema_version": 1,
            "id": "notebook-aaa",
            "title": "A",
            "created_at": "2026-01-01T00:00:00.000Z",
            "updated_at": "2026-01-01T00:00:00.000Z",
            "settings": {},
            "sources": [],
            "pages": [],
            "renders": {},
        },
    )

    index = store.register_notebook(
        notebook_id="notebook-aaa",
        managed_relpath="nb-a",
        project_id="notebook-aaa",
    )
    assert [e.notebook_id for e in index.entries] == ["notebook-aaa"]

    store.register_notebook(
        notebook_id="notebook-bbb",
        managed_relpath="nb-b",
        project_id="notebook-bbb",
    )
    (projects / "nb-b").mkdir(exist_ok=True)
    loaded = store.load()
    assert loaded is not None
    assert loaded.notebook_ids() == ["notebook-aaa", "notebook-bbb"]


def test_corpus_index_rejects_notebook_id_mismatch():
    with pytest.raises(ValidationError):
        validate_entry_matches_project(notebook_id="a", project_id="b")


def test_corpus_index_rejects_path_escape(tmp_path: Path):
    paths = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    paths.projects_dir.mkdir(parents=True)
    store = CorpusIndexStore(paths, clock=FakeClock())
    with pytest.raises((CorpusError, ValidationError, ValueError)):
        store.register_notebook(
            notebook_id="x",
            managed_relpath="../outside",
            project_id="x",
        )


def test_import_run_roundtrip(tmp_path: Path):
    paths = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    store = ImportRunStore(paths)
    run = ImportRun(
        import_run_id="run1",
        plan_id="plan1",
        plan_fingerprint="a" * 64,
        import_policy_id="skip_existing_v1",
        created_at="2026-01-01T00:00:00.000Z",
        updated_at="2026-01-01T00:00:00.000Z",
        status="complete",
    )
    store.save(run)
    loaded = store.load("run1")
    assert loaded.plan_id == "plan1"
    assert loaded.status == "complete"


def test_plan_fingerprint_stable_and_ignores_paths():
    items_a = [
        {
            "item_id": "i1",
            "op": "import_into_notebook",
            "notebook_id": "n1",
            "source_sha256": "b" * 64,
            "media_type": "image/png",
            "page_indexes": [0],
            "source_id": "s1",
            "page_ids": ["p1"],
            "render_ids": ["r1"],
            "provenance": {"original_path": "/Volumes/A/scan.png"},
        }
    ]
    items_b = [
        {
            "item_id": "i1",
            "op": "import_into_notebook",
            "notebook_id": "n1",
            "source_sha256": "b" * 64,
            "media_type": "image/png",
            "page_indexes": [0],
            "source_id": "s1",
            "page_ids": ["p1"],
            "render_ids": ["r1"],
            "provenance": {"original_path": "/Volumes/B/moved.png"},
        }
    ]
    fp_a = compute_plan_fingerprint(
        schema_version=1,
        plan_id="plan1",
        import_policy_id="skip_existing_v1",
        items=items_a,
    )
    fp_b = compute_plan_fingerprint(
        schema_version=1,
        plan_id="plan1",
        import_policy_id="skip_existing_v1",
        items=items_b,
    )
    assert fp_a == fp_b
    assert len(fp_a) == 64
    assert plans_are_idempotent_retries(
        plan_id_a="plan1",
        fingerprint_a=fp_a,
        policy_a="skip_existing_v1",
        item_ids_a={"i1"},
        plan_id_b="plan1",
        fingerprint_b=fp_b,
        policy_b="skip_existing_v1",
        item_ids_b={"i1"},
    )
    assert not plans_are_idempotent_retries(
        plan_id_a="plan1",
        fingerprint_a=fp_a,
        policy_a="skip_existing_v1",
        item_ids_a={"i1"},
        plan_id_b="plan1",
        fingerprint_b=fp_a,
        policy_b="create_duplicate_v1",
        item_ids_b={"i1"},
    )


def test_corpus_doctor_detects_duplicate_page_ids(tmp_path: Path):
    data = tmp_path / "data"
    projects_dir = data / "projects"
    projects_dir.mkdir(parents=True)
    corpus = CorpusPaths(data_dir=data, projects_dir=projects_dir)
    store = CorpusIndexStore(corpus, clock=FakeClock())

    shared_page = "dup-page-id"
    for name, id_prefix in (("nb1", "a"), ("nb2", "b")):
        root = projects_dir / name
        clock, ids = FakeClock(), SequentialIds(prefix=id_prefix)
        paths = open_project_paths(root)
        projects_svc = ProjectService(paths, clock=clock, ids=ids)
        projects_svc.create(name)
        ingest = IngestService(paths, clock=clock, ids=ids)
        project = ingest.import_bytes("a.png", _png_bytes())
        project.pages[0].page_id = shared_page
        write_json_atomic(paths.manifest, project.as_dict())
        store.register_notebook(
            notebook_id=project.id,
            managed_relpath=name,
            project_id=project.id,
        )

    report = CorpusDoctorService(corpus).run(per_notebook=False)
    assert any(f.code == "duplicate_page_id" for f in report.findings), report.findings
    assert not report.ok


def test_corpus_doctor_absent_index_is_warning(tmp_path: Path):
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    report = CorpusDoctorService(corpus).run()
    assert report.ok
    assert any(f.code == "corpus_index_absent" for f in report.findings)


def test_corpus_doctor_committed_import_run_ids_must_resolve(tmp_path: Path):
    """Corpus invariant #6: dangling committed IDs fail doctor."""
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    clock, ids = FakeClock(), SequentialIds("doc")
    paths = open_project_paths(corpus.projects_dir / "nb1")
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("nb1")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    CorpusIndexStore(corpus, clock=clock).register_notebook(
        notebook_id=project.id,
        managed_relpath="nb1",
        project_id=project.id,
    )

    # Healthy committed run → doctor green
    from transcribe.corpus import (
        ImportOrchestrator,
        ImportPlan,
        ImportPlanItem,
        POLICY_SKIP_EXISTING_V1,
    )
    from transcribe.domain.fingerprint import sha256_bytes

    data = _png_bytes(color=(9, 9, 9))
    src = tmp_path / "b.png"
    src.write_bytes(data)
    orch = ImportOrchestrator(corpus, clock=clock, ids=ids)
    run = orch.create_run_from_plan(
        ImportPlan(
            plan_id="plan-ok",
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            items=[
                ImportPlanItem(
                    item_id="i1",
                    op="import_into_notebook",
                    notebook_id=project.id,
                    source_sha256=sha256_bytes(data),
                    media_type="image/png",
                    page_indexes=[0],
                    source_id="src-ok",
                    page_ids=["page-ok"],
                    render_ids=["render-ok"],
                    provenance={"source_path": str(src)},
                    original_filename="b.png",
                )
            ],
        )
    )
    completed = orch.commit_run(run.import_run_id)
    assert completed.status == "complete"
    assert CorpusDoctorService(corpus).run(deep=True).ok

    # Corrupt resulting_ids on disk → doctor fails
    store = ImportRunStore(corpus)
    bad = store.load(run.import_run_id)
    bad.items[0].resulting_ids["page_ids"] = ["missing-page-id"]
    store.save(bad)
    report = CorpusDoctorService(corpus).run(per_notebook=False)
    assert not report.ok
    assert any(f.code == "import_run_committed_page_missing" for f in report.findings)


def test_corpus_doctor_skipped_without_reason_fails(tmp_path: Path):
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    clock, ids = FakeClock(), SequentialIds("sk")
    paths = open_project_paths(corpus.projects_dir / "nb")
    project = ProjectService(paths, clock=clock, ids=ids).create("nb")
    CorpusIndexStore(corpus, clock=clock).register_notebook(
        notebook_id=project.id,
        managed_relpath="nb",
        project_id=project.id,
    )
    corpus.ensure_layout()
    run = ImportRun(
        import_run_id="run-skip-bad",
        plan_id="plan-skip",
        plan_fingerprint="a" * 64,
        import_policy_id="skip_existing_v1",
        created_at="2026-01-01T00:00:00.000Z",
        updated_at="2026-01-01T00:00:00.000Z",
        status="complete",
        items=[
            ImportRunItemOutcome(
                item_id="i1",
                state="skipped",
                resulting_ids={"notebook_id": project.id},
                # missing skip_classification
            )
        ],
    )
    ImportRunStore(corpus).save(run)
    report = CorpusDoctorService(corpus).run(per_notebook=False)
    assert not report.ok
    assert any(f.code == "import_run_outcome_missing_reason" for f in report.findings)


def test_corpus_doctor_malformed_import_run_reported(tmp_path: Path):
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    clock, ids = FakeClock(), SequentialIds("mal")
    paths = open_project_paths(corpus.projects_dir / "nb")
    project = ProjectService(paths, clock=clock, ids=ids).create("nb")
    CorpusIndexStore(corpus, clock=clock).register_notebook(
        notebook_id=project.id,
        managed_relpath="nb",
        project_id=project.id,
    )
    corpus.ensure_layout()
    (corpus.import_runs_dir / "broken.json").write_text("{not-json", encoding="utf-8")
    report = CorpusDoctorService(corpus).run(per_notebook=False)
    assert not report.ok
    assert any(f.code == "import_run_load_failed" for f in report.findings)
