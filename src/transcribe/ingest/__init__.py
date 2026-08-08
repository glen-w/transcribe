"""Source ingestion with attempt staging and ownership isolation."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image, ImageOps

from transcribe.domain.fingerprint import sha256_bytes
from transcribe.domain.models import PageIndex, Project, RenderProvenance, SourceDocument
from transcribe.domain.validation import validate_project
from transcribe.errors import IngestError, ProjectError, ValidationError
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import read_json, write_bytes_atomic, write_json_atomic
from transcribe.persistence.locks import mutation_lock
from transcribe.persistence.schema import require_format
from transcribe.ports import Clock, IdGenerator, to_iso

# Safety bounds
MAX_SOURCE_BYTES = 80 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_IMAGE_PIXELS = 40_000_000
MAX_DIMENSION = 12_000
MAX_RENDERED_BYTES = 512 * 1024 * 1024
MIN_FREE_DISK_BYTES = 256 * 1024 * 1024
DEFAULT_RENDER_DPI = 200
JOURNAL_FORMAT = "transcribe.ingest-journal"
JOURNAL_SCHEMA_VERSION = 1

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def sanitize_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\-()+ ]+", "_", base, flags=re.UNICODE).strip(" .")
    return base or "source"


@dataclass
class _StagedPage:
    page_id: str
    page_index: int
    render_id: str
    staged_path: Path
    width: int
    height: int
    png_sha: str
    pdf_page_index: int | None


@dataclass
class _AttemptCreated:
    paths: list[Path]

    def add(self, path: Path) -> None:
        self.paths.append(path)

    def rollback(self) -> None:
        for path in reversed(self.paths):
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                elif path.exists():
                    path.unlink()
            except OSError:
                pass


def _detect_media(data: bytes, filename: str) -> str:
    try:
        with Image.open(BytesIO(data)) as img:
            img.load()
            fmt = (img.format or "").upper()
            if fmt in {"JPEG", "JPG"}:
                return "image/jpeg"
            if fmt == "PNG":
                return "image/png"
            raise IngestError(f"unsupported image format: {fmt or 'unknown'}")
    except IngestError:
        raise
    except Exception:
        pass
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
        try:
            if doc.is_encrypted:
                raise IngestError("encrypted PDFs are not supported")
            if doc.page_count < 1:
                raise IngestError("PDF has no pages")
            return "application/pdf"
        finally:
            doc.close()
    except IngestError:
        raise
    except Exception as exc:
        raise IngestError(
            f"could not decode '{filename}' as JPEG/PNG/PDF: {exc}"
        ) from exc


def _load_image_bytes(data: bytes) -> tuple[bytes, int, int, str]:
    try:
        image = Image.open(BytesIO(data))
        image = ImageOps.exif_transpose(image)
        image.load()
    except Image.DecompressionBombError as exc:
        raise IngestError("image exceeds maximum pixel limits") from exc
    except Exception as exc:
        raise IngestError(f"invalid image: {exc}") from exc
    width, height = image.size
    if width < 1 or height < 1:
        raise IngestError("invalid image dimensions")
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise IngestError(
            f"image dimensions {width}x{height} exceed maximum {MAX_DIMENSION}"
        )
    if width * height > MAX_IMAGE_PIXELS:
        raise IngestError("image exceeds maximum pixel limits")
    if image.mode not in ("RGB", "RGBA", "L"):
        image = image.convert("RGB")
    out = BytesIO()
    image.save(out, format="PNG")
    png = out.getvalue()
    return png, width, height, sha256_bytes(png)


def _render_pdf_page(doc: pymupdf.Document, page_index: int, dpi: int) -> tuple[bytes, int, int]:
    page = doc[page_index]
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    if pix.width > MAX_DIMENSION or pix.height > MAX_DIMENSION:
        raise IngestError(
            f"rendered page {page_index} dimensions exceed maximum {MAX_DIMENSION}"
        )
    if pix.width * pix.height > MAX_IMAGE_PIXELS:
        raise IngestError(f"rendered page {page_index} exceeds maximum pixel limits")
    return pix.tobytes("png"), pix.width, pix.height


def _free_disk_bytes(path: Path) -> int:
    usage = shutil.disk_usage(path)
    return int(usage.free)


def _ensure_disk_budget(root: Path, *, additional: int = 0) -> None:
    free = _free_disk_bytes(root)
    if free - additional < MIN_FREE_DISK_BYTES:
        raise IngestError(
            f"insufficient free disk space ({free} bytes free; "
            f"need at least {MIN_FREE_DISK_BYTES} bytes headroom)"
        )


def _promote_replace(staged: Path, final: Path) -> None:
    final.parent.mkdir(parents=True, exist_ok=True)
    os.replace(str(staged), str(final))


class IngestService:
    def __init__(
        self,
        paths: ProjectPaths,
        *,
        clock: Clock,
        ids: IdGenerator,
        default_dpi: int = DEFAULT_RENDER_DPI,
    ) -> None:
        self.paths = paths
        self.clock = clock
        self.ids = ids
        self.default_dpi = default_dpi

    def import_path(self, path: Path, *, render_dpi: int | None = None) -> Project:
        data = Path(path).read_bytes()
        return self.import_bytes(Path(path).name, data, render_dpi=render_dpi)

    def import_bytes(
        self,
        filename: str,
        data: bytes,
        *,
        render_dpi: int | None = None,
    ) -> Project:
        if len(data) > MAX_SOURCE_BYTES:
            raise IngestError(
                f"source exceeds maximum size of {MAX_SOURCE_BYTES} bytes"
            )
        dpi = render_dpi or self.default_dpi
        if dpi < 72 or dpi > 600:
            raise IngestError("render_dpi must be between 72 and 600")

        self.recover_incomplete_ingest()
        _ensure_disk_budget(self.paths.root, additional=len(data))

        media = _detect_media(data, filename)
        attempt_id = self.ids.new_id()
        staging = self.paths.staging_attempt_dir(attempt_id)
        staging.mkdir(parents=True, exist_ok=True)
        created = _AttemptCreated([staging])
        source_id = self.ids.new_id()
        safe_name = sanitize_filename(filename)
        source_sha = sha256_bytes(data)
        rendered_budget = 0

        try:
            staged_source = staging / safe_name
            write_bytes_atomic(staged_source, data)
            created.add(staged_source)

            staged_pages: list[_StagedPage] = []

            if media.startswith("image/"):
                png, width, height, png_sha = _load_image_bytes(data)
                rendered_budget += len(png)
                if rendered_budget > MAX_RENDERED_BYTES:
                    raise IngestError(
                        f"rendered output exceeds maximum of {MAX_RENDERED_BYTES} bytes"
                    )
                _ensure_disk_budget(self.paths.root, additional=len(png))
                page_id = self.ids.new_id()
                render_id = self.ids.new_id()
                staged_png = staging / f"0000-{render_id}.png"
                write_bytes_atomic(staged_png, png)
                created.add(staged_png)
                del png
                staged_pages.append(
                    _StagedPage(
                        page_id=page_id,
                        page_index=0,
                        render_id=render_id,
                        staged_path=staged_png,
                        width=width,
                        height=height,
                        png_sha=png_sha,
                        pdf_page_index=None,
                    )
                )
            else:
                doc = pymupdf.open(stream=data, filetype="pdf")
                try:
                    if doc.is_encrypted:
                        raise IngestError("encrypted PDFs are not supported")
                    if doc.page_count > MAX_PDF_PAGES:
                        raise IngestError(
                            f"PDF has {doc.page_count} pages; maximum is {MAX_PDF_PAGES}"
                        )
                    for page_index in range(doc.page_count):
                        png, width, height = _render_pdf_page(doc, page_index, dpi)
                        rendered_budget += len(png)
                        if rendered_budget > MAX_RENDERED_BYTES:
                            raise IngestError(
                                f"rendered output exceeds maximum of "
                                f"{MAX_RENDERED_BYTES} bytes"
                            )
                        _ensure_disk_budget(self.paths.root, additional=len(png))
                        png_sha = sha256_bytes(png)
                        page_id = self.ids.new_id()
                        render_id = self.ids.new_id()
                        staged_png = staging / f"{page_index:04d}-{render_id}.png"
                        write_bytes_atomic(staged_png, png)
                        created.add(staged_png)
                        del png
                        staged_pages.append(
                            _StagedPage(
                                page_id=page_id,
                                page_index=page_index,
                                render_id=render_id,
                                staged_path=staged_png,
                                width=width,
                                height=height,
                                png_sha=png_sha,
                                pdf_page_index=page_index,
                            )
                        )
                finally:
                    doc.close()

            renderer_version = getattr(pymupdf, "VersionBind", "unknown")
            pillow_version = getattr(Image, "__version__", "unknown")
            now = to_iso(self.clock.now())
            is_pdf = media == "application/pdf"

            final_source = self.paths.sources_dir / f"{source_id}-{safe_name}"
            source_rel = self.paths.relativize(final_source)

            page_entries: list[dict[str, Any]] = []
            for sp in staged_pages:
                final_png = self.paths.page_render_path(
                    source_id, sp.page_index, sp.render_id
                )
                page_entries.append(
                    {
                        "page_id": sp.page_id,
                        "page_index": sp.page_index,
                        "render_id": sp.render_id,
                        "width": sp.width,
                        "height": sp.height,
                        "png_sha": sp.png_sha,
                        "pdf_page_index": sp.pdf_page_index,
                        "staged_rel": self.paths.relativize(sp.staged_path),
                        "final_rel": self.paths.relativize(final_png),
                        "renderer": "pymupdf" if is_pdf else "pillow",
                        "renderer_version": (
                            str(renderer_version) if is_pdf else str(pillow_version)
                        ),
                        "source_sha256": source_sha,
                        "render_dpi": dpi,
                    }
                )

            journal: dict[str, Any] = {
                "format": JOURNAL_FORMAT,
                "schema_version": JOURNAL_SCHEMA_VERSION,
                "attempt_id": attempt_id,
                "state": "staged",
                "source": {
                    "source_id": source_id,
                    "original_filename": safe_name,
                    "media_type": media,
                    "sha256": source_sha,
                    "page_count": len(page_entries),
                    "imported_at": now,
                    "render_dpi": dpi,
                    "staged_rel": self.paths.relativize(staged_source),
                    "final_rel": source_rel,
                },
                "pages": page_entries,
            }
            write_json_atomic(self.paths.ingest_journal, journal)

            committed = False
            with mutation_lock(self.paths.mutation_lock):
                journal["state"] = "promoting"
                write_json_atomic(self.paths.ingest_journal, journal)

                _promote_replace(staged_source, final_source)
                created.add(final_source)
                for entry in page_entries:
                    staged = self.paths.resolve_contained(entry["staged_rel"])
                    final = self.paths.resolve_contained(entry["final_rel"])
                    _promote_replace(staged, final)
                    created.add(final)

                journal["state"] = "manifest_pending"
                write_json_atomic(self.paths.ingest_journal, journal)

                payload = require_format(
                    read_json(self.paths.manifest), "transcribe.project"
                )
                project = Project.from_dict(payload)
                validate_project(project)

                new_pages: list[PageIndex] = []
                new_renders: dict[str, RenderProvenance] = {}
                for entry in page_entries:
                    rid = entry["render_id"]
                    new_renders[rid] = RenderProvenance(
                        render_id=rid,
                        source_sha256=entry["source_sha256"],
                        pdf_page_index=entry["pdf_page_index"],
                        render_dpi=entry["render_dpi"],
                        renderer=entry["renderer"],
                        renderer_version=entry["renderer_version"],
                        rendered_image_sha256=entry["png_sha"],
                        width=entry["width"],
                        height=entry["height"],
                        image_relpath=entry["final_rel"],
                    )
                    new_pages.append(
                        PageIndex(
                            page_id=entry["page_id"],
                            source_id=source_id,
                            page_index=entry["page_index"],
                            active_render_id=rid,
                            width=entry["width"],
                            height=entry["height"],
                        )
                    )

                source_doc = SourceDocument(
                    source_id=source_id,
                    original_filename=safe_name,
                    stored_relpath=source_rel,
                    media_type=media,
                    sha256=source_sha,
                    page_count=len(new_pages),
                    imported_at=now,
                    render_dpi=dpi,
                )
                project.sources.append(source_doc)
                project.pages.extend(new_pages)
                project.renders.update(new_renders)
                project.updated_at = now
                validate_project(project, paths=self.paths)
                write_json_atomic(self.paths.manifest, project.as_dict())
                committed = True
                if self.paths.ingest_journal.exists():
                    self.paths.ingest_journal.unlink()

            if committed:
                created.paths = [staging]
            created.rollback()
            return project
        except Exception:
            if not locals().get("committed"):
                created.rollback()
                if self.paths.ingest_journal.exists():
                    try:
                        self.paths.ingest_journal.unlink()
                    except OSError:
                        pass
            raise

    def recover_incomplete_ingest(self) -> None:
        """Roll back or finish a crash-interrupted ingest using the durable journal."""
        journal_path = self.paths.ingest_journal
        if not journal_path.exists():
            return

        with mutation_lock(self.paths.mutation_lock):
            if not journal_path.exists():
                return
            try:
                journal = read_json(journal_path)
            except Exception:
                journal_path.unlink(missing_ok=True)
                return
            if journal.get("format") != JOURNAL_FORMAT:
                journal_path.unlink(missing_ok=True)
                return

            state = journal.get("state")
            source = journal.get("source") or {}
            pages = journal.get("pages") or []
            attempt_id = journal.get("attempt_id")
            source_id = source.get("source_id")

            project: Project | None = None
            if self.paths.manifest.exists():
                try:
                    payload = require_format(
                        read_json(self.paths.manifest), "transcribe.project"
                    )
                    project = Project.from_dict(payload)
                except (
                    OSError,
                    ValueError,
                    KeyError,
                    TypeError,
                    ValidationError,
                    ProjectError,
                ):
                    project = None

            already_committed = bool(
                project
                and source_id
                and any(s.source_id == source_id for s in project.sources)
            )

            if (
                state == "manifest_pending"
                and not already_committed
                and project is not None
            ):
                try:
                    self._apply_journal_to_project(project, journal)
                    validate_project(project, paths=self.paths)
                    write_json_atomic(self.paths.manifest, project.as_dict())
                    already_committed = True
                except Exception:
                    already_committed = False

            if not already_committed:
                for entry in pages:
                    final_rel = entry.get("final_rel")
                    if not final_rel:
                        continue
                    try:
                        final = self.paths.resolve_contained(final_rel)
                    except ValueError:
                        continue
                    if final.exists():
                        try:
                            final.unlink()
                        except OSError:
                            pass
                final_rel = source.get("final_rel")
                if final_rel:
                    try:
                        final = self.paths.resolve_contained(final_rel)
                        if final.exists():
                            final.unlink()
                    except (ValueError, OSError):
                        pass

            if attempt_id:
                staging = self.paths.staging_attempt_dir(str(attempt_id))
                shutil.rmtree(staging, ignore_errors=True)
            try:
                journal_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _apply_journal_to_project(
        self, project: Project, journal: dict[str, Any]
    ) -> None:
        source = journal["source"]
        source_id = source["source_id"]
        if any(s.source_id == source_id for s in project.sources):
            return
        new_pages: list[PageIndex] = []
        new_renders: dict[str, RenderProvenance] = {}
        for entry in journal["pages"]:
            rid = entry["render_id"]
            new_renders[rid] = RenderProvenance(
                render_id=rid,
                source_sha256=entry["source_sha256"],
                pdf_page_index=entry["pdf_page_index"],
                render_dpi=entry["render_dpi"],
                renderer=entry["renderer"],
                renderer_version=entry["renderer_version"],
                rendered_image_sha256=entry["png_sha"],
                width=entry["width"],
                height=entry["height"],
                image_relpath=entry["final_rel"],
            )
            new_pages.append(
                PageIndex(
                    page_id=entry["page_id"],
                    source_id=source_id,
                    page_index=entry["page_index"],
                    active_render_id=rid,
                    width=entry["width"],
                    height=entry["height"],
                )
            )
        project.sources.append(
            SourceDocument(
                source_id=source_id,
                original_filename=source["original_filename"],
                stored_relpath=source["final_rel"],
                media_type=source["media_type"],
                sha256=source["sha256"],
                page_count=int(source["page_count"]),
                imported_at=source["imported_at"],
                render_dpi=int(source["render_dpi"]),
            )
        )
        project.pages.extend(new_pages)
        project.renders.update(new_renders)
        project.updated_at = to_iso(self.clock.now())

    def cleanup_staging(self) -> None:
        self.recover_incomplete_ingest()
        staging = self.paths.staging_dir
        if not staging.exists():
            return
        for child in staging.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
            except OSError:
                pass
