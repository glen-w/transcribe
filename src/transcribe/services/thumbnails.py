"""Bounded page thumbnails for archive/notebook browsing."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from transcribe.domain.models import Project
from transcribe.paths import ProjectPaths

DEFAULT_MAX_EDGE = 256


class ThumbnailService:
    def __init__(self, paths: ProjectPaths, *, max_edge: int = DEFAULT_MAX_EDGE) -> None:
        self.paths = paths
        self.max_edge = max_edge

    def thumb_path(self, page_id: str) -> Path:
        return self.paths.thumb_path(page_id)

    def _source_image(self, project: Project, page_id: str) -> Path | None:
        page = next((p for p in project.pages if p.page_id == page_id), None)
        if page is None:
            return None
        render = project.renders.get(page.active_render_id)
        if render is None:
            return None
        src = self.paths.resolve_contained(render.image_relpath)
        if not src.exists():
            return None
        return src

    def ensure_thumb(self, project: Project, page_id: str) -> Path | None:
        """Return cached or freshly generated JPEG thumb path; None if page/render missing.

        Preserves source aspect ratio, bounded by ``max_edge``.
        """
        src = self._source_image(project, page_id)
        if src is None:
            return None
        self.paths.thumbs_dir.mkdir(parents=True, exist_ok=True)
        dest = self.thumb_path(page_id)
        src_mtime = src.stat().st_mtime
        if dest.exists() and dest.stat().st_mtime >= src_mtime:
            return dest
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((self.max_edge, self.max_edge), Image.Resampling.LANCZOS)
            im.save(dest, format="JPEG", quality=82, optimize=True)
        return dest

    def cover_page_id(self, project: Project) -> str | None:
        """Explicit cover if valid; otherwise first page in notebook order."""
        if project.cover_page_id and any(p.page_id == project.cover_page_id for p in project.pages):
            return project.cover_page_id
        if not project.pages:
            return None
        return project.pages[0].page_id
