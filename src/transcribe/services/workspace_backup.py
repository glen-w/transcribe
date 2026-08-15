"""Full-workspace backup / restore (ZIP + role-root layout)."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from transcribe import __version__
from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import BackupError
from transcribe.persistence.atomic import strict_json_dumps
from transcribe.persistence.locks import FileLock, analysis_lock_held, job_lock_held
from transcribe.persistence.schema import SchemaError, require_format
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.corpus_doctor import CorpusDoctorReport, CorpusDoctorService

MANIFEST_NAME = "transcribe.workspace-backup.json"
FORMAT = "transcribe.workspace-backup"
ROLE_TOP_LEVEL = frozenset({"projects", "data", "inbox", "exports"})
EXCLUDE_DIR_NAMES = frozenset({".cache", ".staging", "thumbs", "__pycache__"})


@dataclass(frozen=True)
class BackupOptions:
    include_inbox: bool = False
    include_exports: bool = False


@dataclass
class BackupResult:
    archive_path: Path
    manifest: dict[str, Any]
    file_count: int
    uncompressed_bytes: int
    notebook_count: int


@dataclass
class VerifyResult:
    ok: bool
    manifest: dict[str, Any]
    messages: list[str] = field(default_factory=list)


@dataclass
class RestoreResult:
    ok: bool
    safety_archive: Path | None
    verify: VerifyResult
    doctor: CorpusDoctorReport | None
    messages: list[str] = field(default_factory=list)
    dry_run: bool = False


def default_backup_dest(runtime: RuntimePaths, *, stamp: str | None = None) -> Path:
    when = stamp or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return runtime.export_dir / "backups" / f"transcribe-workspace-{when}.zip"


def default_safety_dest(runtime: RuntimePaths, *, stamp: str | None = None) -> Path:
    when = stamp or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return runtime.export_dir / "backups" / f"pre-restore-{when}.zip"


class WorkspaceBackupService:
    """Create, verify, and replace-restore full-workspace ZIP archives."""

    def create_backup(
        self,
        runtime: RuntimePaths,
        dest: Path,
        options: BackupOptions | None = None,
    ) -> BackupResult:
        options = options or BackupOptions()
        dest = Path(dest)
        self._refuse_busy(runtime)

        if dest.suffix.lower() != ".zip":
            raise BackupError("backup destination must be a .zip path")

        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_name(dest.name + ".partial")
        if partial.exists():
            partial.unlink()

        skip_paths = {dest.resolve(), partial.resolve()}
        entries: list[tuple[str, Path]] = []
        includes = {
            "projects": True,
            "config": True,
            "corpus": True,
            "ledger": False,
            "inbox": bool(options.include_inbox),
            "exports": bool(options.include_exports),
        }

        projects_root = runtime.projects_dir
        if projects_root.is_dir():
            entries.extend(
                self._collect_tree(
                    projects_root,
                    prefix="projects",
                    skip_paths=skip_paths,
                )
            )

        config_root = runtime.data_dir / "config"
        if config_root.is_dir():
            entries.extend(
                self._collect_tree(config_root, prefix="data/config", skip_paths=skip_paths)
            )

        corpus_root = runtime.data_dir / "corpus"
        if corpus_root.is_dir():
            entries.extend(
                self._collect_tree(corpus_root, prefix="data/corpus", skip_paths=skip_paths)
            )

        ledger = runtime.data_dir / "ocr_preference_ledger.json"
        if ledger.is_file():
            includes["ledger"] = True
            entries.append(("data/ocr_preference_ledger.json", ledger))

        if options.include_inbox and runtime.inbox_dir.is_dir():
            entries.extend(
                self._collect_tree(runtime.inbox_dir, prefix="inbox", skip_paths=skip_paths)
            )

        if options.include_exports and runtime.export_dir.is_dir():
            entries.extend(
                self._collect_tree(
                    runtime.export_dir,
                    prefix="exports",
                    skip_paths=skip_paths,
                )
            )

        entries.sort(key=lambda item: item[0])
        index_lines: list[str] = []
        uncompressed = 0
        notebook_count = self._count_notebooks(projects_root)
        try:
            with zipfile.ZipFile(
                partial,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                allowZip64=True,
            ) as zf:
                for member, src in entries:
                    self._assert_safe_member(member)
                    data = src.read_bytes()
                    digest = hashlib.sha256(data).hexdigest()
                    index_lines.append(f"{member}\t{len(data)}\t{digest}")
                    uncompressed += len(data)
                    zf.writestr(member, data)

                manifest = {
                    "format": FORMAT,
                    "schema_version": 1,
                    "created_at": datetime.now(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "transcribe_version": __version__,
                    "includes": includes,
                    "counts": {
                        "notebooks": notebook_count,
                        "files": len(entries),
                        "uncompressed_bytes": uncompressed,
                    },
                    "file_index_sha256": hashlib.sha256(
                        ("\n".join(index_lines) + ("\n" if index_lines else "")).encode("utf-8")
                    ).hexdigest(),
                    "roots_note": {
                        "roles": ["projects", "data/config", "data/corpus"],
                    },
                }
                require_format(manifest, FORMAT)
                zf.writestr(MANIFEST_NAME, strict_json_dumps(manifest))
        except BackupError:
            if partial.exists():
                partial.unlink(missing_ok=True)
            raise
        except Exception:
            if partial.exists():
                partial.unlink(missing_ok=True)
            raise

        partial.replace(dest)
        return BackupResult(
            archive_path=dest,
            manifest=manifest,
            file_count=len(entries),
            uncompressed_bytes=uncompressed,
            notebook_count=notebook_count,
        )

    def verify_backup(self, archive: Path) -> VerifyResult:
        archive = Path(archive)
        messages: list[str] = []
        if not archive.is_file():
            raise BackupError(f"archive not found: {archive}")
        try:
            with zipfile.ZipFile(archive, mode="r") as zf:
                names = zf.namelist()
                if MANIFEST_NAME not in names:
                    raise BackupError(f"missing {MANIFEST_NAME}")
                raw = zf.read(MANIFEST_NAME)
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise BackupError(f"manifest is not valid JSON: {exc}") from exc
                try:
                    manifest = require_format(payload, FORMAT)
                except SchemaError as exc:
                    raise BackupError(str(exc)) from exc

                index_lines: list[str] = []
                has_projects = False
                has_config = False
                has_corpus = False
                for info in zf.infolist():
                    name = info.filename
                    if name.endswith("/"):
                        continue
                    self._assert_safe_member(name)
                    if name == MANIFEST_NAME:
                        continue
                    top = name.split("/", 1)[0]
                    if top not in ROLE_TOP_LEVEL:
                        raise BackupError(f"unexpected top-level member: {name!r}")
                    if name.startswith("projects/"):
                        has_projects = True
                    if name.startswith("data/config/"):
                        has_config = True
                    if name.startswith("data/corpus/"):
                        has_corpus = True
                    data = zf.read(info)
                    digest = hashlib.sha256(data).hexdigest()
                    index_lines.append(f"{name}\t{len(data)}\t{digest}")

                index_lines.sort()
                digest = hashlib.sha256(
                    ("\n".join(index_lines) + ("\n" if index_lines else "")).encode("utf-8")
                ).hexdigest()
                expected = manifest.get("file_index_sha256")
                if digest != expected:
                    raise BackupError(
                        "file_index_sha256 mismatch "
                        f"(archive={digest[:12]}… manifest={str(expected)[:12]}…)"
                    )

                includes = manifest.get("includes") or {}
                if includes.get("projects") and not has_projects:
                    messages.append("projects included but no project files packed (empty ok)")
                if includes.get("config") and not has_config:
                    messages.append("config included but no config files packed (empty ok)")
                if includes.get("corpus") and not has_corpus:
                    messages.append("corpus included but no corpus files packed (empty ok)")

                return VerifyResult(ok=True, manifest=manifest, messages=messages)
        except zipfile.BadZipFile as exc:
            raise BackupError(f"not a valid zip archive: {exc}") from exc

    def restore_backup(
        self,
        runtime: RuntimePaths,
        archive: Path,
        *,
        safety: bool = True,
        dry_run: bool = False,
        safety_options: BackupOptions | None = None,
    ) -> RestoreResult:
        archive = Path(archive)
        verify = self.verify_backup(archive)
        self._refuse_busy(runtime)

        includes = verify.manifest.get("includes") or {}
        messages = list(verify.messages)
        messages.append(
            "restore will replace: projects, data/config, data/corpus"
            + (", inbox" if includes.get("inbox") else "")
            + (", exports" if includes.get("exports") else "")
        )

        if dry_run:
            return RestoreResult(
                ok=True,
                safety_archive=None,
                verify=verify,
                doctor=None,
                messages=messages + ["dry_run: no changes written"],
                dry_run=True,
            )

        safety_archive: Path | None = None
        if safety:
            safety_dest = default_safety_dest(runtime)
            safety_archive = self.create_backup(
                runtime,
                safety_dest,
                safety_options or BackupOptions(),
            ).archive_path
            messages.append(f"safety backup written to {safety_archive}")

        with zipfile.ZipFile(archive, mode="r") as zf:
            members = [
                info
                for info in zf.infolist()
                if not info.filename.endswith("/") and info.filename != MANIFEST_NAME
            ]
            for info in members:
                self._assert_safe_member(info.filename)

            self._clear_directory_children(runtime.projects_dir)
            runtime.projects_dir.mkdir(parents=True, exist_ok=True)
            self._extract_prefix(zf, members, "projects/", runtime.projects_dir)

            config_dest = runtime.data_dir / "config"
            corpus_dest = runtime.data_dir / "corpus"
            self._replace_tree_from_zip(zf, members, "data/config/", config_dest)
            self._replace_tree_from_zip(zf, members, "data/corpus/", corpus_dest)

            ledger_member = "data/ocr_preference_ledger.json"
            ledger_dest = runtime.data_dir / "ocr_preference_ledger.json"
            member_names = {info.filename for info in members}
            if ledger_member in member_names:
                ledger_dest.parent.mkdir(parents=True, exist_ok=True)
                ledger_dest.write_bytes(zf.read(ledger_member))

            if includes.get("inbox"):
                self._replace_tree_from_zip(zf, members, "inbox/", runtime.inbox_dir)
            if includes.get("exports"):
                self._replace_tree_from_zip(
                    zf,
                    members,
                    "exports/",
                    runtime.export_dir,
                    preserve_relative={"backups"},
                )

        cache_dir = runtime.data_dir / "cache"
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            messages.append("removed data/cache (archive FTS will rebuild)")

        doctor = CorpusDoctorService(CorpusPaths.from_runtime(runtime)).run(
            deep=True, per_notebook=True
        )
        if not doctor.ok:
            messages.append("corpus doctor reported errors after restore")
        else:
            messages.append("corpus doctor ok after restore")

        return RestoreResult(
            ok=doctor.ok,
            safety_archive=safety_archive,
            verify=verify,
            doctor=doctor,
            messages=messages,
            dry_run=False,
        )

    def _refuse_busy(self, runtime: RuntimePaths) -> None:
        corpus = CorpusPaths.from_runtime(runtime)
        lock_path = corpus.lock_path
        if lock_path.exists():
            probe = FileLock(lock_path, timeout=0.0)
            if not probe.acquire(blocking=False):
                raise BackupError("corpus lock is held; finish import/OCR batch work first")
            probe.release()

        projects = runtime.projects_dir
        if not projects.is_dir():
            return
        for project_json in projects.rglob("project.json"):
            root = project_json.parent
            if job_lock_held(root / ".transcribe.job.lock"):
                raise BackupError(f"OCR job lock held for notebook at {root}")
            if analysis_lock_held(root / ".transcribe.analysis.lock"):
                raise BackupError(f"analysis job lock held for notebook at {root}")

    def _collect_tree(
        self,
        root: Path,
        *,
        prefix: str,
        skip_paths: set[Path],
    ) -> list[tuple[str, Path]]:
        out: list[tuple[str, Path]] = []
        root = root.resolve()
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved in skip_paths:
                continue
            rel = path.relative_to(root).as_posix()
            parts = Path(rel).parts
            if any(part in EXCLUDE_DIR_NAMES for part in parts):
                continue
            if path.name.endswith(".lock") or path.suffix == ".lock":
                continue
            if path.name.startswith(".") and path.name.endswith(".lock"):
                continue
            member = f"{prefix}/{rel}" if prefix else rel
            self._assert_safe_member(member)
            out.append((member, path))
        return out

    @staticmethod
    def _assert_safe_member(name: str) -> None:
        if not name or name.startswith("/") or name.startswith("\\"):
            raise BackupError(f"unsafe zip member path: {name!r}")
        if "\\" in name:
            raise BackupError(f"unsafe zip member path: {name!r}")
        parts = name.split("/")
        if ".." in parts:
            raise BackupError(f"zip-slip member rejected: {name!r}")
        if name != MANIFEST_NAME and parts[0] not in ROLE_TOP_LEVEL:
            raise BackupError(f"unexpected top-level member: {name!r}")

    @staticmethod
    def _count_notebooks(projects_root: Path) -> int:
        if not projects_root.is_dir():
            return 0
        return sum(1 for p in projects_root.rglob("project.json") if p.is_file())

    @staticmethod
    def _clear_directory_children(directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for child in directory.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    def _replace_tree_from_zip(
        self,
        zf: zipfile.ZipFile,
        members: Iterable[zipfile.ZipInfo],
        prefix: str,
        dest_root: Path,
        *,
        preserve_relative: set[str] | None = None,
    ) -> None:
        preserve_relative = preserve_relative or set()
        preserved: dict[str, Path] = {}
        dest_root.mkdir(parents=True, exist_ok=True)
        if preserve_relative:
            for name in list(preserve_relative):
                src = dest_root / name
                if src.exists():
                    tmp = dest_root / f".preserve-{name}"
                    if tmp.exists():
                        if tmp.is_dir():
                            shutil.rmtree(tmp)
                        else:
                            tmp.unlink()
                    src.rename(tmp)
                    preserved[name] = tmp

        for child in list(dest_root.iterdir()):
            if child.name.startswith(".preserve-"):
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

        self._extract_prefix(zf, members, prefix, dest_root)

        for name, tmp in preserved.items():
            target = dest_root / name
            if target.exists():
                if tmp.is_dir():
                    shutil.rmtree(tmp)
                else:
                    tmp.unlink()
            else:
                tmp.rename(target)

    @staticmethod
    def _extract_prefix(
        zf: zipfile.ZipFile,
        members: Iterable[zipfile.ZipInfo],
        prefix: str,
        dest_root: Path,
    ) -> None:
        dest_root = dest_root.resolve()
        for info in members:
            name = info.filename
            if not name.startswith(prefix):
                continue
            rel = name[len(prefix) :]
            if not rel:
                continue
            target = (dest_root / rel).resolve()
            try:
                target.relative_to(dest_root)
            except ValueError as exc:
                raise BackupError(f"zip-slip extract rejected: {name!r}") from exc
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info))
