"""Import adapters that emit a canonical ImportPlan (no notebook identity from paths)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
from transcribe.ports import IdGenerator

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
_PDF_SUFFIXES = {".pdf"}


def _list_importable(folder: Path) -> list[Path]:
    files = sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in (_IMAGE_SUFFIXES | _PDF_SUFFIXES)
    )
    if not files:
        raise ValidationError(f"no importable images/PDFs in {folder}")
    return files


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
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise ValidationError(f"not a directory: {root}")
    files = _list_importable(root)
    names = [f.name.lower() for f in files]
    if len(names) != len(set(names)):
        raise ValidationError("ordering ambiguity: duplicate filenames in folder")

    plan_id = ids.new_id()
    items: list[ImportPlanItem] = []
    nb_id = notebook_id or ids.new_id()
    rel = managed_relpath or root.name

    for path in files:
        data = path.read_bytes()
        media = _detect_media(data, path.name)
        # Page count: 1 for images; PDF page count via pymupdf
        page_indexes = _page_indexes_for(path, data, media)
        source_id = ids.new_id()
        page_ids = [ids.new_id() for _ in page_indexes]
        render_ids = [ids.new_id() for _ in page_indexes]
        provenance: dict[str, Any] = {
            "source_path": str(path),
            "title": title or root.name,
            "managed_relpath": rel if op == OP_CREATE_NOTEBOOK else None,
        }
        if provenance["managed_relpath"] is None:
            provenance.pop("managed_relpath")
        items.append(
            ImportPlanItem(
                item_id=ids.new_id(),
                op=op,
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
        # Subsequent items for the same notebook must import_into_notebook
        op = OP_IMPORT_INTO_NOTEBOOK

    plan = ImportPlan(
        plan_id=plan_id,
        import_policy_id=import_policy_id,
        items=items,
    )
    validate_import_plan(plan)
    return plan


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
