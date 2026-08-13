"""Fine-tune dataset export (images + preferred/active text). No in-app training."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transcribe.domain.models import OCRAttempt, PageResult
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import write_json_atomic
from transcribe.services.export import ExportService
from transcribe.services.project import ProjectService


@dataclass(frozen=True)
class FinetuneExportOptions:
    include_edited_pages: bool = True
    require_preferred: bool = False
    prefer_effective_text: bool = True
    include_rejected_candidates: bool = False
    image_mode: str = "copy"  # copy | hardlink


def _pick_training_text(
    result: PageResult,
    *,
    prefer_effective_text: bool,
) -> tuple[str, OCRAttempt | None, bool]:
    """Return (text, source_attempt, had_human_edit)."""
    had_edit = result.edited_text is not None
    if prefer_effective_text and had_edit:
        return (
            result.edited_text or "",
            result.preferred_attempt() or result.active_attempt(),
            True,
        )
    preferred = result.preferred_attempt()
    if preferred is not None and preferred.status == "succeeded" and preferred.raw_text:
        return preferred.raw_text, preferred, False
    active = result.active_attempt()
    if active is not None and active.status == "succeeded" and active.raw_text:
        return active.raw_text, active, False
    return "", None, False


class FinetuneExportService:
    def __init__(self, paths: ProjectPaths, projects: ProjectService) -> None:
        self.paths = paths
        self.projects = projects
        self._export = ExportService(paths, projects)

    def export(
        self,
        dest_dir: Path | None = None,
        *,
        options: FinetuneExportOptions | None = None,
    ) -> Path:
        opts = options or FinetuneExportOptions()
        if opts.image_mode not in ("copy", "hardlink"):
            raise ValueError(f"invalid image_mode: {opts.image_mode!r}")
        snapshot = self._export.capture_snapshot()
        project = snapshot.project
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = Path(dest_dir) if dest_dir else (self.paths.exports_dir / f"finetune_export_{stamp}")
        out.mkdir(parents=True, exist_ok=True)
        images_dir = out / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        samples: list[dict[str, Any]] = []
        model_counts: dict[str, int] = {}
        for page in project.pages:
            result = snapshot.results.get(page.page_id)
            if result is None:
                continue
            if opts.require_preferred and not result.preferred_attempt_id:
                continue
            text, source_attempt, had_edit = _pick_training_text(
                result, prefer_effective_text=opts.prefer_effective_text
            )
            if not text.strip():
                continue
            if had_edit and not opts.include_edited_pages:
                continue
            render = project.renders.get(page.active_render_id)
            if render is None:
                continue
            src_image = self.paths.resolve_contained(render.image_relpath)
            if not src_image.is_file():
                continue
            dest_image = images_dir / f"{page.page_id}.png"
            self._link_or_copy(src_image, dest_image, mode=opts.image_mode)
            model_name = ""
            model_digest = None
            attempt_id = ""
            attempt_kind = "vision"
            if source_attempt is not None:
                attempt_id = source_attempt.attempt_id
                attempt_kind = source_attempt.attempt_kind or "vision"
                if source_attempt.provenance:
                    model_name = source_attempt.provenance.model_name
                    model_digest = source_attempt.provenance.model_digest
            if model_name:
                model_counts[model_name] = model_counts.get(model_name, 0) + 1
            row: dict[str, Any] = {
                "id": f"{project.id}:{page.page_id}",
                "image": f"images/{page.page_id}.png",
                "text": text,
                "source": {
                    "notebook_id": project.id,
                    "page_id": page.page_id,
                    "attempt_id": attempt_id,
                    "model_name": model_name,
                    "model_digest": model_digest,
                    "attempt_kind": attempt_kind,
                    "had_human_edit": had_edit,
                },
            }
            if opts.include_rejected_candidates:
                rejected = []
                for attempt in result.attempts:
                    if attempt.status != "succeeded":
                        continue
                    if (attempt.attempt_kind or "vision") != "vision":
                        continue
                    if attempt.attempt_id == attempt_id:
                        continue
                    if not (attempt.raw_text or "").strip():
                        continue
                    rejected.append(
                        {
                            "attempt_id": attempt.attempt_id,
                            "model_name": (
                                attempt.provenance.model_name if attempt.provenance else ""
                            ),
                            "text": attempt.raw_text,
                        }
                    )
                row["rejected"] = rejected
            samples.append(row)

        samples_path = out / "samples.jsonl"
        with samples_path.open("w", encoding="utf-8") as fh:
            for row in samples:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        manifest = {
            "format": "transcribe.finetune-export-manifest",
            "schema_version": 1,
            "notebook_id": project.id,
            "notebook_title": project.title,
            "sample_count": len(samples),
            "model_counts": model_counts,
            "options": {
                "include_edited_pages": opts.include_edited_pages,
                "require_preferred": opts.require_preferred,
                "prefer_effective_text": opts.prefer_effective_text,
                "include_rejected_candidates": opts.include_rejected_candidates,
                "image_mode": opts.image_mode,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json_atomic(out / "manifest.json", manifest)
        (out / "README.txt").write_text(
            "Transcribe fine-tune export package.\n"
            "See docs/finetune_export.md for how to use samples.jsonl + images/\n"
            "with an external trainer (Ollama / Unsloth / TRL). Training is not\n"
            "performed inside Transcribe.\n",
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
