"""Portable export writers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from transcribe import __version__
from transcribe.domain.models import Project
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import write_bytes_atomic, write_json_atomic
from transcribe.services.project import ProjectService


class ExportService:
    def __init__(self, paths: ProjectPaths, projects: ProjectService) -> None:
        self.paths = paths
        self.projects = projects

    def export_all(self, project: Project, dest_dir: Path | None = None) -> dict[str, Path]:
        out = Path(dest_dir) if dest_dir else self.paths.exports_dir
        out.mkdir(parents=True, exist_ok=True)
        notebook = self.build_notebook(project)
        md = self.build_markdown(project)
        txt = self.build_plaintext(project)
        paths = {
            "notebook": out / "notebook.transcribe.json",
            "markdown": out / "notebook.md",
            "text": out / "notebook.txt",
        }
        write_json_atomic(paths["notebook"], notebook)
        write_bytes_atomic(paths["markdown"], md.encode("utf-8"))
        write_bytes_atomic(paths["text"], txt.encode("utf-8"))
        return paths

    def build_notebook(self, project: Project) -> dict[str, Any]:
        pages_out: list[dict[str, Any]] = []
        for global_index, page in enumerate(project.pages):
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
                    "tags": list(page.tags),
                }
            )
        return {
            "format": "transcribe.notebook",
            "schema_version": 1,
            "application_version": __version__,
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

    def build_markdown(self, project: Project) -> str:
        parts: list[str] = [f"# {project.title}\n"]
        for i, page in enumerate(project.pages):
            result = self.projects.load_page_result(page.page_id)
            text = (result.effective_text() if result else None) or ""
            parts.append(f"## Page {i + 1}\n\n{text.strip()}\n")
        return "\n".join(parts).rstrip() + "\n"

    def build_plaintext(self, project: Project) -> str:
        parts: list[str] = []
        for i, page in enumerate(project.pages):
            result = self.projects.load_page_result(page.page_id)
            text = (result.effective_text() if result else None) or ""
            parts.append(f"----- Page {i + 1} -----\n{text.strip()}")
        return "\n\n".join(parts).rstrip() + "\n"
