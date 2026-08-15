"""Unit tests for full-workspace backup / restore."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from transcribe.errors import BackupError
from transcribe.persistence.atomic import write_json_atomic
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.workspace_backup import (
    MANIFEST_NAME,
    BackupOptions,
    WorkspaceBackupService,
)


def _runtime(tmp_path: Path) -> RuntimePaths:
    data = tmp_path / "data"
    projects = tmp_path / "projects"
    inbox = tmp_path / "inbox"
    exports = tmp_path / "exports"
    for path in (data, projects, inbox, exports, data / "config", data / "corpus"):
        path.mkdir(parents=True, exist_ok=True)
    return RuntimePaths(
        repo_root=tmp_path,
        data_dir=data,
        projects_dir=projects,
        inbox_dir=inbox,
        export_dir=exports,
    )


def _seed_workspace(rt: RuntimePaths) -> None:
    write_json_atomic(
        rt.data_dir / "config" / "settings.json",
        {"format": "transcribe.settings", "schema_version": 1, "settings": {}},
    )
    (rt.data_dir / "corpus" / "corpus-index.json").write_text(
        json.dumps(
            {
                "format": "transcribe.corpus-index",
                "schema_version": 1,
                "entries": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    nb = rt.projects_dir / "demo"
    nb.mkdir(parents=True)
    write_json_atomic(
        nb / "project.json",
        {
            "format": "transcribe.project",
            "schema_version": 1,
            "id": "nb-demo",
            "title": "Demo",
            "created_at": "2020-01-01T00:00:00Z",
            "updated_at": "2020-01-01T00:00:00Z",
            "sources": [],
            "pages": [],
            "renders": {},
        },
    )
    (nb / ".cache" / "thumb.png").parent.mkdir(parents=True)
    (nb / ".cache" / "thumb.png").write_bytes(b"nope")
    (rt.data_dir / "cache" / "archive.sqlite").parent.mkdir(parents=True)
    (rt.data_dir / "cache" / "archive.sqlite").write_bytes(b"sqlite")
    (rt.data_dir / "corpus" / ".corpus.lock").write_text("", encoding="utf-8")
    (rt.inbox_dir / "scan.png").write_bytes(b"inbox")
    (rt.export_dir / "old.txt").write_text("export", encoding="utf-8")


def test_create_verify_excludes_cache_and_locks(tmp_path: Path) -> None:
    rt = _runtime(tmp_path)
    _seed_workspace(rt)
    dest = rt.export_dir / "backups" / "ws.zip"
    service = WorkspaceBackupService()
    result = service.create_backup(rt, dest, BackupOptions())
    assert result.archive_path.is_file()
    assert result.notebook_count == 1

    with zipfile.ZipFile(dest) as zf:
        names = set(zf.namelist())
    assert MANIFEST_NAME in names
    assert "projects/demo/project.json" in names
    assert "data/config/settings.json" in names
    assert "data/corpus/corpus-index.json" in names
    assert not any("archive.sqlite" in n for n in names)
    assert not any(".cache/" in n for n in names)
    assert not any(n.endswith(".lock") for n in names if n != MANIFEST_NAME)
    assert not any(n.startswith("inbox/") for n in names)
    assert not any(n.startswith("exports/") for n in names)

    verified = service.verify_backup(dest)
    assert verified.ok


def test_include_inbox_and_exports_skips_dest_zip(tmp_path: Path) -> None:
    rt = _runtime(tmp_path)
    _seed_workspace(rt)
    dest = rt.export_dir / "backups" / "ws.zip"
    service = WorkspaceBackupService()
    service.create_backup(
        rt,
        dest,
        BackupOptions(include_inbox=True, include_exports=True),
    )
    with zipfile.ZipFile(dest) as zf:
        names = set(zf.namelist())
    assert "inbox/scan.png" in names
    assert "exports/old.txt" in names
    assert "exports/backups/ws.zip" not in names
    assert not any(n.endswith(".partial") for n in names)


def test_verify_rejects_zip_slip(tmp_path: Path) -> None:
    rt = _runtime(tmp_path)
    _seed_workspace(rt)
    dest = rt.export_dir / "backups" / "ws.zip"
    service = WorkspaceBackupService()
    service.create_backup(rt, dest)

    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(dest, "r") as src, zipfile.ZipFile(evil, "w") as out:
        for info in src.infolist():
            out.writestr(info, src.read(info.filename))
        out.writestr("../escape.txt", b"nope")

    with pytest.raises(BackupError, match="zip-slip|unsafe|unexpected"):
        service.verify_backup(evil)


def test_dry_run_restore_does_not_write(tmp_path: Path) -> None:
    rt = _runtime(tmp_path)
    _seed_workspace(rt)
    dest = rt.export_dir / "backups" / "ws.zip"
    service = WorkspaceBackupService()
    service.create_backup(rt, dest)

    marker = rt.projects_dir / "demo" / "project.json"
    before = marker.read_bytes()
    (rt.projects_dir / "demo" / "extra.txt").write_text("stay-for-dry-run", encoding="utf-8")

    result = service.restore_backup(rt, dest, safety=False, dry_run=True)
    assert result.dry_run
    assert result.ok
    assert marker.read_bytes() == before
    assert (rt.projects_dir / "demo" / "extra.txt").is_file()
