"""Source ingestion with attempt staging and ownership isolation."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from transcribe.domain.fingerprint import sha256_bytes
from transcribe.domain.models import PageIndex, Project, RenderProvenance, SourceDocument
from transcribe.errors import IngestError
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import write_bytes_atomic, write_json_atomic
from transcribe.persistence.locks import mutation_lock
from transcribe.ports import Clock, IdGenerator, to_iso

# Safety bounds
MAX_SOURCE_BYTES = 80 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_IMAGE_PIXELS = 40_000_000
MAX_DIMENSION = 12_000
DEFAULT_RENDER_DPI = 200

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def sanitize_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\-()+ ]+", "_", base, flags=re.UNICODE).strip(" .")
    return base or "source"


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
    lower = filename.lower()
    # Try image first
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
    # Try PDF
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

    def import_path(self, project: Project, path: Path, *, render_dpi: int | None = None) -> Project:
        data = Path(path).read_bytes()
        return self.import_bytes(
            project, Path(path).name, data, render_dpi=render_dpi
        )

    def import_bytes(
        self,
        project: Project,
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

        media = _detect_media(data, filename)
        attempt_id = self.ids.new_id()
        staging = self.paths.staging_attempt_dir(attempt_id)
        staging.mkdir(parents=True, exist_ok=True)
        created = _AttemptCreated([staging])
        source_id = self.ids.new_id()
        safe_name = sanitize_filename(filename)
        source_sha = sha256_bytes(data)

        try:
            staged_source = staging / safe_name
            write_bytes_atomic(staged_source, data)
            created.add(staged_source)

            pages_meta: list[tuple[str, int, str, bytes, int, int, str]] = []
            # tuples: page_id, page_index, render_id, png_bytes, w, h, png_sha

            if media.startswith("image/"):
                png, width, height, png_sha = _load_image_bytes(data)
                page_id = self.ids.new_id()
                render_id = self.ids.new_id()
                pages_meta.append((page_id, 0, render_id, png, width, height, png_sha))
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
                        png_sha = sha256_bytes(png)
                        page_id = self.ids.new_id()
                        render_id = self.ids.new_id()
                        pages_meta.append(
                            (page_id, page_index, render_id, png, width, height, png_sha)
                        )
                finally:
                    doc.close()

            # Stage page PNGs
            for page_id, page_index, render_id, png, width, height, png_sha in pages_meta:
                staged_png = staging / f"{page_index:04d}-{render_id}.png"
                write_bytes_atomic(staged_png, png)
                created.add(staged_png)

            renderer_version = getattr(pymupdf, "VersionBind", "unknown")
            now = to_iso(self.clock.now())

            with mutation_lock(self.paths.mutation_lock):
                # Re-load is caller's responsibility for freshness; we mutate given project
                # Install source
                final_source = self.paths.sources_dir / f"{source_id}-{safe_name}"
                write_bytes_atomic(final_source, data)
                created.add(final_source)
                source_rel = self.paths.relativize(final_source)

                new_pages: list[PageIndex] = []
                new_renders: dict[str, RenderProvenance] = {}
                for page_id, page_index, render_id, png, width, height, png_sha in pages_meta:
                    final_png = self.paths.page_render_path(source_id, page_index, render_id)
                    write_bytes_atomic(final_png, png)
                    created.add(final_png)
                    rel = self.paths.relativize(final_png)
                    new_renders[render_id] = RenderProvenance(
                        render_id=render_id,
                        source_sha256=source_sha,
                        pdf_page_index=page_index if media == "application/pdf" else None,
                        render_dpi=dpi if media == "application/pdf" else dpi,
                        renderer="pymupdf" if media == "application/pdf" else "pillow",
                        renderer_version=(
                            str(renderer_version)
                            if media == "application/pdf"
                            else getattr(Image, "__version__", "unknown")
                        ),
                        rendered_image_sha256=png_sha,
                        width=width,
                        height=height,
                        image_relpath=rel,
                    )
                    new_pages.append(
                        PageIndex(
                            page_id=page_id,
                            source_id=source_id,
                            page_index=page_index,
                            active_render_id=render_id,
                            width=width,
                            height=height,
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
                write_json_atomic(self.paths.manifest, project.as_dict())

            # Commit succeeded — clear rollback list for durable files, remove staging
            created.paths = [staging]
            created.rollback()
            return project
        except Exception:
            created.rollback()
            raise

    def cleanup_staging(self) -> None:
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
