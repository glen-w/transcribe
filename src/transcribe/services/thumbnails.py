"""Bounded page thumbnails for archive/notebook browsing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from transcribe.domain.models import Project
from transcribe.paths import ProjectPaths

DEFAULT_MAX_EDGE = 256
GRID_MAX_EDGE = 128
_COVER_JPEG_QUALITY = 82
_GRID_JPEG_QUALITY = 72


@dataclass(frozen=True)
class ThumbRegenStats:
    pages_total: int
    pages_written: int
    pages_missing: int
    pages_error: int


class ThumbnailService:
    def __init__(
        self,
        paths: ProjectPaths,
        *,
        max_edge: int = DEFAULT_MAX_EDGE,
        grid_max_edge: int = GRID_MAX_EDGE,
    ) -> None:
        self.paths = paths
        self.max_edge = max_edge
        self.grid_max_edge = grid_max_edge

    def thumb_path(self, page_id: str) -> Path:
        return self.paths.thumb_path(page_id)

    def grid_thumb_path(self, page_id: str) -> Path:
        return self.paths.grid_thumb_path(page_id)

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

    def _thumb_fresh(self, dest: Path, src_mtime: float) -> bool:
        return dest.exists() and dest.stat().st_mtime >= src_mtime

    def _write_thumb(
        self,
        im: Image.Image,
        dest: Path,
        *,
        max_edge: int,
        quality: int,
    ) -> None:
        out = im.copy()
        out.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        out.save(dest, format="JPEG", quality=quality, optimize=True)

    def ensure_thumb(self, project: Project, page_id: str) -> Path | None:
        """Return cached or freshly generated cover JPEG thumb; None if missing.

        Preserves source aspect ratio, bounded by ``max_edge`` (default 256).
        """
        cover, _grid = self.ensure_page_thumbs(project, page_id, cover=True, grid=False)
        return cover

    def ensure_grid_thumb(self, project: Project, page_id: str) -> Path | None:
        """Return cached or freshly generated small grid JPEG; None if missing.

        Bounded by ``grid_max_edge`` (default 128) for dense page grids.
        """
        _cover, grid = self.ensure_page_thumbs(project, page_id, cover=False, grid=True)
        return grid

    def ensure_page_thumbs(
        self,
        project: Project,
        page_id: str,
        *,
        cover: bool = True,
        grid: bool = True,
        force: bool = False,
    ) -> tuple[Path | None, Path | None]:
        """Ensure cover and/or grid thumbs from one source decode when needed."""
        src = self._source_image(project, page_id)
        if src is None:
            return None, None
        self.paths.thumbs_dir.mkdir(parents=True, exist_ok=True)
        cover_dest = self.thumb_path(page_id) if cover else None
        grid_dest = self.grid_thumb_path(page_id) if grid else None
        src_mtime = src.stat().st_mtime
        need_cover = cover_dest is not None and (
            force or not self._thumb_fresh(cover_dest, src_mtime)
        )
        need_grid = grid_dest is not None and (
            force or not self._thumb_fresh(grid_dest, src_mtime)
        )
        if not need_cover and not need_grid:
            return cover_dest, grid_dest
        with Image.open(src) as im:
            rgb = im.convert("RGB")
            if need_cover and cover_dest is not None:
                self._write_thumb(
                    rgb,
                    cover_dest,
                    max_edge=self.max_edge,
                    quality=_COVER_JPEG_QUALITY,
                )
            if need_grid and grid_dest is not None:
                self._write_thumb(
                    rgb,
                    grid_dest,
                    max_edge=self.grid_max_edge,
                    quality=_GRID_JPEG_QUALITY,
                )
        return cover_dest, grid_dest

    def ensure_thumbs_for_pages(
        self,
        project: Project,
        page_ids: list[str] | tuple[str, ...] | None = None,
        *,
        cover: bool = True,
        grid: bool = True,
        force: bool = False,
    ) -> None:
        """Best-effort warm of thumbs for the given pages (or all notebook pages)."""
        ids = list(page_ids) if page_ids is not None else [p.page_id for p in project.pages]
        for page_id in ids:
            try:
                self.ensure_page_thumbs(
                    project, page_id, cover=cover, grid=grid, force=force
                )
            except OSError:
                continue

    def regenerate_thumbs(
        self,
        project: Project,
        page_ids: list[str] | tuple[str, ...] | None = None,
        *,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> ThumbRegenStats:
        """Force-rewrite cover + grid thumbs for pages; returns counts."""
        ids = list(page_ids) if page_ids is not None else [p.page_id for p in project.pages]
        total = len(ids)
        written = 0
        missing = 0
        errors = 0
        for i, page_id in enumerate(ids):
            if on_progress is not None:
                on_progress(i, total, page_id[:8])
            try:
                cover, grid = self.ensure_page_thumbs(
                    project, page_id, cover=True, grid=True, force=True
                )
                if cover is None and grid is None:
                    missing += 1
                else:
                    written += 1
            except OSError:
                errors += 1
        if on_progress is not None:
            on_progress(total, total, "done")
        return ThumbRegenStats(
            pages_total=total,
            pages_written=written,
            pages_missing=missing,
            pages_error=errors,
        )

    def cover_page_id(self, project: Project) -> str | None:
        """Explicit cover if valid; otherwise first page in notebook order."""
        if project.cover_page_id and any(p.page_id == project.cover_page_id for p in project.pages):
            return project.cover_page_id
        if not project.pages:
            return None
        return project.pages[0].page_id
