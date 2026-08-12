"""Import adapters that emit a canonical ImportPlan (no notebook identity from paths)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from transcribe.corpus.index import CorpusIndexStore
from transcribe.corpus.paths import CorpusPaths
from transcribe.corpus.plan import (
    OP_CREATE_NOTEBOOK,
    OP_IMPORT_INTO_NOTEBOOK,
    POLICY_SKIP_EXISTING_V1,
    ImportPlan,
    ImportPlanItem,
    validate_import_plan,
)
from transcribe.domain.fingerprint import sha256_bytes
from transcribe.errors import ValidationError
from transcribe.ingest import _detect_media
from transcribe.persistence.atomic import read_json
from transcribe.persistence.schema import require_format
from transcribe.ports import IdGenerator

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
_PDF_SUFFIXES = {".pdf"}

ON_EXISTING_SKIP = "skip"
ON_EXISTING_OVERWRITE = "overwrite"
OnExistingMode = Literal["skip", "overwrite"]
OVERWRITE_CONFIRM_PHRASE = "OVERWRITE ALL"


@dataclass
class AlreadyImportedFolder:
    """A source child folder that already maps to a managed notebook."""

    source_folder: Path
    managed_relpath: str
    notebook_id: str
    title: str
    project_root: Path


@dataclass
class FolderImportScan:
    """Result of scanning a parent directory for folder-per-notebook import."""

    parent: Path
    new_folders: list[Path] = field(default_factory=list)
    already_imported: list[AlreadyImportedFolder] = field(default_factory=list)
    empty_skipped: list[Path] = field(default_factory=list)


def _list_importable(folder: Path) -> list[Path]:
    files = sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in (_IMAGE_SUFFIXES | _PDF_SUFFIXES)
    )
    if not files:
        raise ValidationError(f"no importable images/PDFs in {folder}")
    return files


def _try_list_importable(folder: Path) -> list[Path] | None:
    try:
        return _list_importable(folder)
    except ValidationError:
        return None


def _items_from_folder(
    folder: Path,
    *,
    ids: IdGenerator,
    title: str | None = None,
    managed_relpath: str | None = None,
    notebook_id: str | None = None,
    op: str = OP_CREATE_NOTEBOOK,
) -> list[ImportPlanItem]:
    """Build plan items for one flat folder (create then import_into)."""
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise ValidationError(f"not a directory: {root}")
    files = _list_importable(root)
    names = [f.name.lower() for f in files]
    if len(names) != len(set(names)):
        raise ValidationError(
            f"ordering ambiguity: duplicate filenames in folder {root.name}"
        )

    items: list[ImportPlanItem] = []
    nb_id = notebook_id or ids.new_id()
    rel = managed_relpath or root.name
    current_op = op

    for path in files:
        data = path.read_bytes()
        media = _detect_media(data, path.name)
        page_indexes = _page_indexes_for(path, data, media)
        source_id = ids.new_id()
        page_ids = [ids.new_id() for _ in page_indexes]
        render_ids = [ids.new_id() for _ in page_indexes]
        provenance: dict[str, Any] = {
            "source_path": str(path),
            "title": title or root.name,
            "managed_relpath": rel if current_op == OP_CREATE_NOTEBOOK else None,
        }
        if provenance["managed_relpath"] is None:
            provenance.pop("managed_relpath")
        items.append(
            ImportPlanItem(
                item_id=ids.new_id(),
                op=current_op,
                notebook_id=nb_id,
                source_sha256=sha256_bytes(data),
                media_type=media,
                page_indexes=page_indexes,
                source_id=source_id,
                page_ids=page_ids,
                render_ids=render_ids,
                provenance=provenance,
                original_filename=path.name,
            )
        )
        current_op = OP_IMPORT_INTO_NOTEBOOK

    return items


def plan_from_folder(
    folder: Path,
    *,
    ids: IdGenerator,
    title: str | None = None,
    managed_relpath: str | None = None,
    import_policy_id: str = POLICY_SKIP_EXISTING_V1,
    notebook_id: str | None = None,
    op: str = OP_CREATE_NOTEBOOK,
) -> ImportPlan:
    """Build a create_notebook or import_into_notebook plan from a flat folder.

    Natural sort (filesystem name order) is the proposed page order. Duplicate
    basenames are refused as ordering ambiguity.
    """
    items = _items_from_folder(
        folder,
        ids=ids,
        title=title,
        managed_relpath=managed_relpath,
        notebook_id=notebook_id,
        op=op,
    )
    plan = ImportPlan(
        plan_id=ids.new_id(),
        import_policy_id=import_policy_id,
        items=items,
    )
    validate_import_plan(plan)
    return plan


def _lookup_existing(
    managed_relpath: str,
    *,
    corpus_paths: CorpusPaths,
) -> AlreadyImportedFolder | None:
    """Return conflict info when managed_relpath already maps to a notebook."""
    index = None
    try:
        index = CorpusIndexStore(corpus_paths).load()
    except Exception:  # noqa: BLE001 — fall back to on-disk detection
        index = None

    if index is not None:
        for entry in index.entries:
            if entry.managed_relpath == managed_relpath:
                root = corpus_paths.resolve_managed(entry.managed_relpath)
                title = managed_relpath
                if (root / "project.json").is_file():
                    try:
                        payload = require_format(
                            read_json(root / "project.json"), "transcribe.project"
                        )
                        title = str(payload.get("title") or managed_relpath)
                    except Exception:  # noqa: BLE001
                        pass
                return AlreadyImportedFolder(
                    source_folder=Path(),  # filled by caller
                    managed_relpath=managed_relpath,
                    notebook_id=entry.notebook_id,
                    title=title,
                    project_root=root,
                )

    on_disk = corpus_paths.projects_dir / managed_relpath
    if on_disk.is_dir() and (on_disk / "project.json").is_file():
        try:
            payload = require_format(
                read_json(on_disk / "project.json"), "transcribe.project"
            )
            notebook_id = str(payload["id"])
            title = str(payload.get("title") or managed_relpath)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(
                f"unreadable existing notebook at {on_disk}: {exc}"
            ) from exc
        return AlreadyImportedFolder(
            source_folder=Path(),
            managed_relpath=managed_relpath,
            notebook_id=notebook_id,
            title=title,
            project_root=on_disk.resolve(),
        )
    return None


def scan_folder_notebooks(
    parent: Path,
    corpus_paths: CorpusPaths,
) -> FolderImportScan:
    """Scan immediate child directories for folder-per-notebook import."""
    root = Path(parent).expanduser().resolve()
    if not root.is_dir():
        raise ValidationError(f"not a directory: {root}")

    scan = FolderImportScan(parent=root)
    children = sorted(p for p in root.iterdir() if p.is_dir())
    for child in children:
        files = _try_list_importable(child)
        if files is None:
            scan.empty_skipped.append(child)
            continue
        names = [f.name.lower() for f in files]
        if len(names) != len(set(names)):
            raise ValidationError(
                f"ordering ambiguity: duplicate filenames in folder {child.name}"
            )
        existing = _lookup_existing(child.name, corpus_paths=corpus_paths)
        if existing is not None:
            existing.source_folder = child
            scan.already_imported.append(existing)
        else:
            scan.new_folders.append(child)
    return scan


def plan_from_folders(
    parent: Path,
    *,
    ids: IdGenerator,
    corpus_paths: CorpusPaths,
    import_policy_id: str = POLICY_SKIP_EXISTING_V1,
    on_existing: OnExistingMode = ON_EXISTING_SKIP,
) -> tuple[ImportPlan, FolderImportScan]:
    """Build one ImportPlan from immediate child folders (folder-per-notebook).

    Planning only — does not delete or mutate the corpus. Callers that choose
    ``overwrite`` must run prepare_folder_overwrite before commit.
    """
    if on_existing not in (ON_EXISTING_SKIP, ON_EXISTING_OVERWRITE):
        raise ValidationError(f"invalid on_existing mode: {on_existing!r}")

    scan = scan_folder_notebooks(parent, corpus_paths)
    folders_to_import: list[Path]
    if on_existing == ON_EXISTING_OVERWRITE:
        folders_to_import = list(scan.new_folders) + [
            c.source_folder for c in scan.already_imported
        ]
        folders_to_import.sort(key=lambda p: p.name)
    else:
        folders_to_import = list(scan.new_folders)

    if not folders_to_import:
        if scan.already_imported and on_existing == ON_EXISTING_SKIP:
            raise ValidationError(
                "all importable child folders were already imported "
                "(use on_existing=overwrite to replace them)"
            )
        raise ValidationError(
            f"no importable child folders under {scan.parent}"
        )

    items: list[ImportPlanItem] = []
    for child in folders_to_import:
        items.extend(
            _items_from_folder(
                child,
                ids=ids,
                title=child.name,
                managed_relpath=child.name,
                op=OP_CREATE_NOTEBOOK,
            )
        )

    plan = ImportPlan(
        plan_id=ids.new_id(),
        import_policy_id=import_policy_id,
        items=items,
    )
    validate_import_plan(plan)
    return plan, scan


def _page_indexes_for(path: Path, data: bytes, media: str) -> list[int]:
    if media == "application/pdf" or path.suffix.lower() == ".pdf":
        import pymupdf

        doc = pymupdf.open(stream=data, filetype="pdf")
        try:
            n = int(doc.page_count)
        finally:
            doc.close()
        if n < 1:
            raise ValidationError(f"PDF has no pages: {path.name}")
        return list(range(n))
    return [0]
