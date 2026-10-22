"""Detection fine-tune export (images + labelled findings). No in-app training."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transcribe.detection.api import DetectionService
from transcribe.persistence.atomic import write_json_atomic
from transcribe.services.export import ExportService
from transcribe.services.project import ProjectService


@dataclass(frozen=True)
class DetectionFinetuneExportOptions:
    include_unreviewed: bool = False
    detector_ids: tuple[str, ...] = ()
    finding_types: tuple[str, ...] = ()
    image_mode: str = "copy"  # copy | hardlink


class DetectionFinetuneExportService:
    def __init__(self, projects: ProjectService) -> None:
        self.projects = projects
        self.paths = projects.paths
        self._export = ExportService(self.paths, projects)
        self._detection = DetectionService(projects)

    def export(
        self,
        dest_dir: Path | None = None,
        *,
        options: DetectionFinetuneExportOptions | None = None,
    ) -> Path:
        opts = options or DetectionFinetuneExportOptions()
        if opts.image_mode not in ("copy", "hardlink"):
            raise ValueError(f"invalid image_mode: {opts.image_mode!r}")

        snapshot = self._export.capture_snapshot()
        project = snapshot.project
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = (
            Path(dest_dir)
            if dest_dir
            else (self.paths.exports_dir / f"detection_finetune_export_{stamp}")
        )
        out.mkdir(parents=True, exist_ok=True)
        images_dir = out / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        wanted_detectors = {d for d in opts.detector_ids if d}
        wanted_types = {t for t in opts.finding_types if t}
        allow_status = {"approved", "rejected"}
        if opts.include_unreviewed:
            allow_status.add("unreviewed")

        samples: list[dict[str, Any]] = []
        detector_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        copied_pages: set[str] = set()

        for finding in self._detection.list_all_findings():
            if finding.review_status not in allow_status:
                continue
            if wanted_detectors and finding.detector_id not in wanted_detectors:
                continue
            if wanted_types and finding.finding_type not in wanted_types:
                continue
            page_id = finding.start_page_id
            page = next((p for p in project.pages if p.page_id == page_id), None)
            if page is None:
                continue
            result = snapshot.results.get(page_id)
            text = ""
            if result is not None:
                text = result.effective_text() or ""
            render = project.renders.get(page.active_render_id)
            if render is None:
                continue
            src_image = self.paths.resolve_contained(render.image_relpath)
            if not src_image.is_file():
                continue
            dest_image = images_dir / f"{page_id}.png"
            if page_id not in copied_pages:
                self._link_or_copy(src_image, dest_image, mode=opts.image_mode)
                copied_pages.add(page_id)

            snippets = []
            if isinstance(finding.evidence, dict):
                raw_snips = finding.evidence.get("snippets") or []
                if isinstance(raw_snips, list):
                    snippets = [str(s) for s in raw_snips if str(s).strip()]
            prompt = finding.prompt_provenance if isinstance(finding.prompt_provenance, dict) else {}
            row = {
                "id": f"{project.id}:{finding.finding_id}",
                "image": f"images/{page_id}.png",
                "text": text,
                "label": finding.review_status,
                "finding": {
                    "finding_id": finding.finding_id,
                    "detector_id": finding.detector_id,
                    "detector_version": finding.detector_version,
                    "finding_type": finding.finding_type,
                    "start_page_id": finding.start_page_id,
                    "end_page_id": finding.end_page_id,
                    "confidence": finding.confidence,
                    "snippets": snippets,
                    "detector_data": dict(finding.detector_data or {}),
                    "prompt_id": prompt.get("prompt_id"),
                    "prompt_version": prompt.get("version"),
                },
                "source": {
                    "notebook_id": project.id,
                    "page_id": page_id,
                },
            }
            samples.append(row)
            detector_counts[finding.detector_id] = detector_counts.get(finding.detector_id, 0) + 1
            status_counts[finding.review_status] = status_counts.get(finding.review_status, 0) + 1

        samples_path = out / "samples.jsonl"
        with samples_path.open("w", encoding="utf-8") as fh:
            for row in samples:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        manifest = {
            "format": "transcribe.detection-finetune-export-manifest",
            "schema_version": 1,
            "notebook_id": project.id,
            "notebook_title": project.title,
            "sample_count": len(samples),
            "detector_counts": detector_counts,
            "status_counts": status_counts,
            "options": {
                "include_unreviewed": opts.include_unreviewed,
                "detector_ids": list(opts.detector_ids),
                "finding_types": list(opts.finding_types),
                "image_mode": opts.image_mode,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json_atomic(out / "manifest.json", manifest)
        (out / "README.txt").write_text(
            "Transcribe detection fine-tune export package.\n"
            "Each samples.jsonl row ties a page image + effective text to an\n"
            "approved or rejected detection finding for external training.\n"
            "Unreviewed findings are excluded by default. Transcribe does not train.\n",
            encoding="utf-8",
        )
        return out

    @staticmethod
    def _link_or_copy(src: Path, dest: Path, *, mode: str) -> None:
        if dest.exists():
            dest.unlink()
        if mode == "hardlink":
            try:
                dest.hardlink_to(src)
                return
            except OSError:
                pass
        shutil.copy2(src, dest)
