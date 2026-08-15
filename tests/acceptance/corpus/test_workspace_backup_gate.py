"""Acceptance: backup → mutate → restore → corpus-doctor deep green."""

from __future__ import annotations

from pathlib import Path

from transcribe.corpus import CorpusPaths, ImportOrchestrator, ImportPlan, ImportPlanItem
from transcribe.corpus import POLICY_SKIP_EXISTING_V1
from transcribe.domain.fingerprint import sha256_bytes
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.corpus_doctor import CorpusDoctorService
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.workspace_backup import (
    BackupOptions,
    WorkspaceBackupService,
)
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def _runtime(tmp_path: Path) -> RuntimePaths:
    data = tmp_path / "data"
    projects = tmp_path / "projects"
    inbox = tmp_path / "inbox"
    exports = tmp_path / "exports"
    for path in (data, projects, inbox, exports, data / "config"):
        path.mkdir(parents=True, exist_ok=True)
    return RuntimePaths(
        repo_root=tmp_path,
        data_dir=data,
        projects_dir=projects,
        inbox_dir=inbox,
        export_dir=exports,
    )


def _item(source_path: Path, data: bytes) -> ImportPlanItem:
    return ImportPlanItem(
        item_id="item1",
        op="create_notebook",
        notebook_id="nb-backup",
        source_sha256=sha256_bytes(data),
        media_type="image/png",
        page_indexes=[0],
        source_id="src-backup",
        page_ids=["page-backup"],
        render_ids=["render-backup"],
        provenance={
            "source_path": str(source_path),
            "title": "Backup demo",
            "managed_relpath": "nb-backup",
        },
        original_filename=source_path.name,
    )


def test_backup_restore_round_trip_doctor_green(tmp_path: Path) -> None:
    rt = _runtime(tmp_path)
    corpus = CorpusPaths.from_runtime(rt)
    corpus.ensure_layout()

    png = _png_bytes(color=(10, 20, 30))
    source_path = tmp_path / "page.png"
    source_path.write_bytes(png)

    clock, ids = FakeClock(), SequentialIds("run")
    orchestrator = ImportOrchestrator(corpus, clock=clock, ids=ids)
    plan = ImportPlan(
        plan_id="plan-backup",
        import_policy_id=POLICY_SKIP_EXISTING_V1,
        items=[_item(source_path, png)],
    )
    run = orchestrator.create_run_from_plan(plan)
    completed = orchestrator.commit_run(run.import_run_id)
    assert completed.status == "complete"

    root = rt.projects_dir / "nb-backup"
    assert (root / "project.json").is_file()
    assert CorpusDoctorService(corpus).run(deep=True).ok

    # Seed disposable cache that must not survive as authority
    (rt.data_dir / "cache").mkdir(parents=True)
    (rt.data_dir / "cache" / "archive.sqlite").write_bytes(b"cache")

    service = WorkspaceBackupService()
    archive = rt.export_dir / "backups" / "roundtrip.zip"
    created = service.create_backup(rt, archive, BackupOptions())
    assert created.notebook_count == 1
    assert service.verify_backup(archive).ok

    # Mutate workspace after backup
    ProjectService(open_project_paths(root), clock=clock, ids=ids).load(reconcile=False)
    import shutil

    shutil.rmtree(root)
    assert not root.exists()

    restore = service.restore_backup(rt, archive, safety=True, dry_run=False)
    assert restore.safety_archive is not None
    assert restore.safety_archive.is_file()
    assert (rt.projects_dir / "nb-backup" / "project.json").is_file()
    assert not (rt.data_dir / "cache" / "archive.sqlite").exists()
    assert restore.doctor is not None
    assert restore.ok
    assert CorpusDoctorService(CorpusPaths.from_runtime(rt)).run(deep=True).ok


def test_restore_dry_run_and_cli_safety_flag_semantics(tmp_path: Path) -> None:
    rt = _runtime(tmp_path)
    corpus = CorpusPaths.from_runtime(rt)
    corpus.ensure_layout()
    png = _png_bytes()
    source_path = tmp_path / "page.png"
    source_path.write_bytes(png)
    clock, ids = FakeClock(), SequentialIds("run")
    orchestrator = ImportOrchestrator(corpus, clock=clock, ids=ids)
    run = orchestrator.create_run_from_plan(
        ImportPlan(
            plan_id="plan-dry",
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            items=[_item(source_path, png)],
        )
    )
    orchestrator.commit_run(run.import_run_id)

    service = WorkspaceBackupService()
    archive = rt.export_dir / "backups" / "dry.zip"
    service.create_backup(rt, archive)

    before = list(rt.projects_dir.rglob("project.json"))
    dry = service.restore_backup(rt, archive, safety=False, dry_run=True)
    assert dry.dry_run and dry.ok
    assert list(rt.projects_dir.rglob("project.json")) == before
