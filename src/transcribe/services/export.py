"""Portable export writers with coherent snapshot semantics."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Sequence

from transcribe import __version__
from transcribe.domain.content_revision import content_revision_hex
from transcribe.domain.fingerprint import sha256_bytes
from transcribe.domain.models import PageResult, Project
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import write_bytes_atomic, write_json_atomic
from transcribe.persistence.locks import mutation_lock
from transcribe.services.export_document import (
    ExportDocument,
    ExportSnapshot,
    build_document,
)
from transcribe.services.export_epub import EpubDependencyError, write_epub
from transcribe.services.export_html import build_html, write_html
from transcribe.services.export_options import ExportOptions
from transcribe.services.export_pdf import write_pdf
from transcribe.services.project import ProjectService

__all__ = [
    "ExportService",
    "ExportSnapshot",
    "ExportOptions",
    "ExportDocument",
    "EpubDependencyError",
]


class ExportService:
    def __init__(self, paths: ProjectPaths, projects: ProjectService) -> None:
        self.paths = paths
        self.projects = projects

    def capture_snapshot(self, project: Project | None = None) -> ExportSnapshot:
        """Load one coherent Project + page-result view under the mutation lock.

        Caller-supplied ``project`` is ignored for authority; disk is re-read so
        all export formats share one frozen moment.
        """
        del project  # authority is always the on-disk project under lock
        with mutation_lock(self.paths.mutation_lock):
            snap_project = self.projects._load_unlocked(reconcile=False)
            results: dict[str, PageResult | None] = {}
            for page in snap_project.pages:
                results[page.page_id] = self.projects._load_page_result_unlocked(page.page_id)
            rev = content_revision_hex(snap_project, results)
            return ExportSnapshot(project=snap_project, results=results, content_revision=rev)

    @staticmethod
    def capture_snapshot_at(paths: ProjectPaths, projects: ProjectService) -> ExportSnapshot:
        """Capture a snapshot for an arbitrary project (multi-notebook export)."""
        return ExportService(paths, projects).capture_snapshot()

    def export_all(
        self,
        project: Project | None = None,
        dest_dir: Path | None = None,
        *,
        options: ExportOptions | None = None,
    ) -> dict[str, Path]:
        opts = options or ExportOptions()
        snapshot = self.capture_snapshot(project)
        return self.export_snapshots([snapshot], dest_dir=dest_dir, options=opts)

    def export_snapshots(
        self,
        snapshots: Sequence[ExportSnapshot],
        *,
        dest_dir: Path | None = None,
        options: ExportOptions | None = None,
        title: str | None = None,
    ) -> dict[str, Path]:
        if not snapshots:
            raise ValueError("export requires at least one snapshot")
        opts = options or ExportOptions()
        out = Path(dest_dir) if dest_dir else self.paths.exports_dir
        out.mkdir(parents=True, exist_ok=True)
        document = build_document(
            snapshots,
            opts,
            application_version=__version__,
            title=title,
        )
        return self._write_bundle(document, snapshots, out, opts)

    def _write_bundle(
        self,
        document: ExportDocument,
        snapshots: Sequence[ExportSnapshot],
        out: Path,
        opts: ExportOptions,
    ) -> dict[str, Path]:
        staging = Path(tempfile.mkdtemp(prefix=".export-", dir=str(out)))
        try:
            staged: dict[str, Path] = {}
            file_names: dict[str, str] = {}

            if opts.wants("json"):
                if len(snapshots) == 1:
                    notebook = self.build_notebook(snapshots[0])
                    staged["notebook"] = staging / "notebook.transcribe.json"
                    write_json_atomic(staged["notebook"], notebook)
                    file_names["notebook"] = "notebook.transcribe.json"
                else:
                    notebooks_dir = staging / "notebooks"
                    notebooks_dir.mkdir(parents=True, exist_ok=True)
                    for part, snap in zip(document.parts, snapshots, strict=True):
                        nb = self.build_notebook(snap)
                        path = notebooks_dir / part.slug / "notebook.transcribe.json"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        write_json_atomic(path, nb)
                        key = f"notebook:{part.slug}"
                        staged[key] = path
                        file_names[key] = f"notebooks/{part.slug}/notebook.transcribe.json"
                    bundle_index = {
                        "format": "transcribe.export-bundle",
                        "schema_version": 1,
                        "application_version": __version__,
                        "title": document.title,
                        "bundle_revision": document.bundle_revision,
                        "notebooks": [
                            {
                                "project_id": p.project_id,
                                "title": p.title,
                                "slug": p.slug,
                                "content_revision": p.content_revision,
                                "path": f"notebooks/{p.slug}/notebook.transcribe.json",
                            }
                            for p in document.parts
                        ],
                    }
                    staged["bundle"] = staging / "bundle.transcribe.json"
                    write_json_atomic(staged["bundle"], bundle_index)
                    file_names["bundle"] = "bundle.transcribe.json"

            if opts.wants("markdown"):
                md = self.build_markdown_document(document, opts)
                staged["markdown"] = staging / "notebook.md"
                write_bytes_atomic(staged["markdown"], md.encode("utf-8"))
                file_names["markdown"] = "notebook.md"

            if opts.wants("text"):
                txt = self.build_plaintext_document(document, opts)
                staged["text"] = staging / "notebook.txt"
                write_bytes_atomic(staged["text"], txt.encode("utf-8"))
                file_names["text"] = "notebook.txt"

            if opts.wants("html"):
                staged["html"] = staging / "notebook.html"
                write_html(staged["html"], document, opts)
                file_names["html"] = "notebook.html"

            if opts.wants("pdf"):
                staged["pdf"] = staging / "notebook.pdf"
                write_pdf(staged["pdf"], document, opts)
                file_names["pdf"] = "notebook.pdf"

            if opts.wants("epub"):
                staged["epub"] = staging / "notebook.epub"
                write_epub(staged["epub"], document, opts)
                file_names["epub"] = "notebook.epub"

            checksums = {name: sha256_bytes(path.read_bytes()) for name, path in staged.items()}
            primary_id = document.primary_project_id
            primary_updated = snapshots[0].project.updated_at if snapshots else None
            manifest = {
                "format": "transcribe.export-manifest",
                "schema_version": 1,
                "application_version": __version__,
                "project_id": primary_id,
                "project_updated_at": primary_updated,
                "content_revision": document.stamp_revision,
                "bundle_revision": document.bundle_revision,
                "notebooks": [
                    {
                        "project_id": p.project_id,
                        "title": p.title,
                        "content_revision": p.content_revision,
                    }
                    for p in document.parts
                ],
                "export_options": opts.as_dict(),
                "files": file_names,
                "sha256": checksums,
            }
            write_json_atomic(staging / "export.manifest.json", manifest)

            final: dict[str, Path] = {"manifest": out / "export.manifest.json"}
            for key, staged_path in staged.items():
                rel = file_names[key]
                dest = out / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                staged_path.replace(dest)
                final[key] = dest
            (staging / "export.manifest.json").replace(final["manifest"])
            return final
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def build_notebook(self, snapshot: ExportSnapshot | Project) -> dict[str, Any]:
        snap = snapshot if isinstance(snapshot, ExportSnapshot) else None
        project = snapshot.project if snap else snapshot  # type: ignore[assignment]
        pages_out: list[dict[str, Any]] = []
        for global_index, page in enumerate(project.pages):
            if snap is not None:
                result = snap.results.get(page.page_id)
            else:
                result = self.projects.load_page_result(page.page_id)
            attempt = result.active_attempt() if result else None
            pages_out.append(
                {
                    "page_id": page.page_id,
                    "global_index": global_index,
                    "source_id": page.source_id,
                    "page_index": page.page_index,
                    "status": result.status if result else "pending",
                    "text": result.effective_text() if result else None,
                    "raw_text": attempt.raw_text if attempt else None,
                    "edited": bool(result and result.edited_text is not None),
                    "edited_text": result.edited_text if result else None,
                    "input_fingerprint": attempt.input_fingerprint if attempt else None,
                    "active_attempt_id": result.active_attempt_id if result else None,
                    "provenance": (
                        attempt.provenance.as_dict() if attempt and attempt.provenance else None
                    ),
                    "provider_metadata": attempt.provider_metadata if attempt else None,
                    "date": page.date.as_dict() if page.date else None,
                    "date_approved": page.date_approved,
                    "date_source": page.date_source,
                    "tags": list(page.tags),
                }
            )
        rev = (
            snap.content_revision
            if snap is not None and snap.content_revision
            else content_revision_hex(
                project,
                {
                    p.page_id: (
                        snap.results.get(p.page_id)
                        if snap is not None
                        else self.projects.load_page_result(p.page_id)
                    )
                    for p in project.pages
                },
            )
        )
        return {
            "format": "transcribe.notebook",
            "schema_version": 1,
            "application_version": __version__,
            "content_revision": rev,
            "project": {
                "id": project.id,
                "title": project.title,
                "created_at": project.created_at,
                "updated_at": project.updated_at,
                "tags": list(project.tags),
                "cover_page_id": project.cover_page_id,
                "date_start": (project.date_start.as_dict() if project.date_start else None),
                "date_end": project.date_end.as_dict() if project.date_end else None,
            },
            "sources": [
                {
                    "source_id": s.source_id,
                    "original_filename": s.original_filename,
                    "sha256": s.sha256,
                    "media_type": s.media_type,
                    "page_count": s.page_count,
                }
                for s in project.sources
            ],
            "pages": pages_out,
        }

    def build_markdown(self, snapshot: ExportSnapshot | Project) -> str:
        """Backward-compatible single-notebook markdown builder."""
        if isinstance(snapshot, Project):
            snap = self.capture_snapshot(snapshot)
        else:
            snap = snapshot
        document = build_document([snap], ExportOptions(), application_version=__version__)
        return self.build_markdown_document(document, ExportOptions())

    def build_plaintext(self, snapshot: ExportSnapshot | Project) -> str:
        """Backward-compatible single-notebook plaintext builder."""
        if isinstance(snapshot, Project):
            snap = self.capture_snapshot(snapshot)
        else:
            snap = snapshot
        document = build_document([snap], ExportOptions(), application_version=__version__)
        return self.build_plaintext_document(document, ExportOptions())

    @staticmethod
    def build_markdown_document(document: ExportDocument, options: ExportOptions) -> str:
        parts: list[str] = []
        parts.append(f"<!-- transcribe.content_revision: {document.stamp_revision} -->\n")
        parts.append(f"# {document.title}\n")
        for part in document.parts:
            if document.is_bundle:
                parts.append(f"## {part.title}\n")
                if options.include_dates and (part.date_start_label or part.date_end_label):
                    span = " – ".join(x for x in (part.date_start_label, part.date_end_label) if x)
                    parts.append(f"*{span}*\n")
            for section in part.sections:
                heading_level = "###" if document.is_bundle else "##"
                heading = section.label
                if options.include_dates and section.date_label:
                    heading = f"{heading} · {section.date_label}"
                text = section.text or ("*(blank page)*" if options.include_blank_pages else "")
                if not text and not options.include_blank_pages:
                    continue
                parts.append(f"{heading_level} {heading}\n\n{text}\n")
        return "\n".join(parts).rstrip() + "\n"

    @staticmethod
    def build_plaintext_document(document: ExportDocument, options: ExportOptions) -> str:
        parts: list[str] = []
        parts.append(f"# transcribe.content_revision: {document.stamp_revision}")
        if document.is_bundle:
            parts.append(document.title)
        for part in document.parts:
            if document.is_bundle:
                parts.append(f"===== {part.title} =====")
            for section in part.sections:
                label = section.label
                if options.include_dates and section.date_label:
                    label = f"{label} · {section.date_label}"
                text = section.text
                if not text and not options.include_blank_pages:
                    continue
                parts.append(f"----- {label} -----\n{text}")
        return "\n\n".join(parts).rstrip() + "\n"

    def build_html(
        self, snapshot: ExportSnapshot | Project, options: ExportOptions | None = None
    ) -> str:
        opts = options or ExportOptions()
        if isinstance(snapshot, Project):
            snap = self.capture_snapshot(snapshot)
        else:
            snap = snapshot
        document = build_document([snap], opts, application_version=__version__)
        return build_html(document, opts)
