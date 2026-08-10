"""Portable export writers with coherent snapshot semantics."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcribe import __version__
from transcribe.domain.content_revision import content_revision_hex
from transcribe.domain.fingerprint import sha256_bytes
from transcribe.domain.models import PageResult, Project
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import write_bytes_atomic, write_json_atomic
from transcribe.persistence.locks import mutation_lock
from transcribe.services.project import ProjectService


@dataclass(frozen=True)
class ExportSnapshot:
    project: Project
    results: dict[str, PageResult | None]
    content_revision: str = ""


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
                results[page.page_id] = self.projects._load_page_result_unlocked(
                    page.page_id
                )
            rev = content_revision_hex(snap_project, results)
            return ExportSnapshot(
                project=snap_project, results=results, content_revision=rev
            )

    def export_all(
        self, project: Project | None = None, dest_dir: Path | None = None
    ) -> dict[str, Path]:
        out = Path(dest_dir) if dest_dir else self.paths.exports_dir
        out.mkdir(parents=True, exist_ok=True)
        snapshot = self.capture_snapshot(project)
        notebook = self.build_notebook(snapshot)
        md = self.build_markdown(snapshot)
        txt = self.build_plaintext(snapshot)

        staging = Path(tempfile.mkdtemp(prefix=".export-", dir=str(out)))
        try:
            staged = {
                "notebook": staging / "notebook.transcribe.json",
                "markdown": staging / "notebook.md",
                "text": staging / "notebook.txt",
            }
            write_json_atomic(staged["notebook"], notebook)
            write_bytes_atomic(staged["markdown"], md.encode("utf-8"))
            write_bytes_atomic(staged["text"], txt.encode("utf-8"))
            checksums = {
                name: sha256_bytes(path.read_bytes()) for name, path in staged.items()
            }
            manifest = {
                "format": "transcribe.export-manifest",
                "schema_version": 1,
                "application_version": __version__,
                "project_id": snapshot.project.id,
                "project_updated_at": snapshot.project.updated_at,
                "content_revision": snapshot.content_revision,
                "files": {
                    "notebook": "notebook.transcribe.json",
                    "markdown": "notebook.md",
                    "text": "notebook.txt",
                },
                "sha256": checksums,
            }
            write_json_atomic(staging / "export.manifest.json", manifest)

            final = {
                "notebook": out / "notebook.transcribe.json",
                "markdown": out / "notebook.md",
                "text": out / "notebook.txt",
                "manifest": out / "export.manifest.json",
            }
            for key, staged_path in staged.items():
                staged_path.replace(final[key])
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
                    "provenance": attempt.provenance.as_dict()
                    if attempt and attempt.provenance
                    else None,
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
                "date_start": project.date_start.as_dict() if project.date_start else None,
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
        snap = snapshot if isinstance(snapshot, ExportSnapshot) else None
        project = snapshot.project if snap else snapshot  # type: ignore[assignment]
        rev = (
            snap.content_revision
            if snap is not None and snap.content_revision
            else ""
        )
        if not rev and snap is not None:
            rev = content_revision_hex(project, snap.results)
        parts: list[str] = []
        if rev:
            parts.append(f"<!-- transcribe.content_revision: {rev} -->\n")
        parts.append(f"# {project.title}\n")
        for i, page in enumerate(project.pages):
            if snap is not None:
                result = snap.results.get(page.page_id)
            else:
                result = self.projects.load_page_result(page.page_id)
            text = (result.effective_text() if result else None) or ""
            parts.append(f"## Page {i + 1}\n\n{text.strip()}\n")
        return "\n".join(parts).rstrip() + "\n"

    def build_plaintext(self, snapshot: ExportSnapshot | Project) -> str:
        snap = snapshot if isinstance(snapshot, ExportSnapshot) else None
        project = snapshot.project if snap else snapshot  # type: ignore[assignment]
        rev = (
            snap.content_revision
            if snap is not None and snap.content_revision
            else ""
        )
        if not rev and snap is not None:
            rev = content_revision_hex(project, snap.results)
        parts: list[str] = []
        if rev:
            parts.append(f"# transcribe.content_revision: {rev}")
        for i, page in enumerate(project.pages):
            if snap is not None:
                result = snap.results.get(page.page_id)
            else:
                result = self.projects.load_page_result(page.page_id)
            text = (result.effective_text() if result else None) or ""
            parts.append(f"----- Page {i + 1} -----\n{text.strip()}")
        return "\n\n".join(parts).rstrip() + "\n"
