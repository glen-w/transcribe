"""Thumbnail generation preserves source aspect within a max edge."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from transcribe.ingest import IngestService
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.thumbnails import (
    DEFAULT_MAX_EDGE,
    GRID_MAX_EDGE,
    ThumbnailService,
)
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def test_thumb_preserves_aspect_bounded_by_max_edge(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("covers")
    ingest = IngestService(paths, clock=clock, ids=ids)

    wide = ingest.import_bytes("wide.png", _png_bytes(size=(400, 100)))
    tall = ingest.import_bytes("tall.png", _png_bytes(size=(100, 400)))
    project = tall

    thumbs = ThumbnailService(paths)
    # Import already warms thumbs; delete so we exercise ensure paths.
    for page in project.pages:
        paths.thumb_path(page.page_id).unlink(missing_ok=True)
        paths.grid_thumb_path(page.page_id).unlink(missing_ok=True)

    wide_thumb = thumbs.ensure_thumb(project, wide.pages[0].page_id)
    tall_thumb = thumbs.ensure_thumb(project, tall.pages[1].page_id)
    assert wide_thumb is not None and tall_thumb is not None

    with Image.open(wide_thumb) as a, Image.open(tall_thumb) as b:
        assert a.size == (DEFAULT_MAX_EDGE, DEFAULT_MAX_EDGE // 4)
        assert b.size == (DEFAULT_MAX_EDGE // 4, DEFAULT_MAX_EDGE)

    assert thumbs.cover_page_id(project) == project.pages[0].page_id


def test_grid_thumb_is_smaller_than_cover(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("grid")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("page.png", _png_bytes(size=(400, 200)))
    page_id = project.pages[0].page_id

    # Import warms both; verify sizes.
    cover = paths.thumb_path(page_id)
    grid = paths.grid_thumb_path(page_id)
    assert cover.exists() and grid.exists()
    with Image.open(cover) as c, Image.open(grid) as g:
        assert c.size == (DEFAULT_MAX_EDGE, DEFAULT_MAX_EDGE // 2)
        assert g.size == (GRID_MAX_EDGE, GRID_MAX_EDGE // 2)
        assert g.size[0] < c.size[0]


def test_force_regenerate_rewrites_existing_thumbs(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("regen")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("page.png", _png_bytes(size=(200, 200)))
    page_id = project.pages[0].page_id
    cover = paths.thumb_path(page_id)
    grid = paths.grid_thumb_path(page_id)
    assert cover.exists() and grid.exists()
    # Corrupt so rewrite is observable.
    cover.write_bytes(b"x")
    grid.write_bytes(b"y")

    thumbs = ThumbnailService(paths)
    stats = thumbs.regenerate_thumbs(project)
    assert stats.pages_total == 1
    assert stats.pages_written == 1
    assert stats.pages_missing == 0
    assert stats.pages_error == 0
    assert cover.read_bytes() != b"x"
    assert grid.read_bytes() != b"y"
    with Image.open(cover) as c, Image.open(grid) as g:
        assert max(c.size) <= DEFAULT_MAX_EDGE
        assert max(g.size) <= GRID_MAX_EDGE
        assert max(g.size) <= max(c.size)


def test_ensure_page_thumbs_skips_fresh_files(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("fresh")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("page.png", _png_bytes(size=(200, 200)))
    page_id = project.pages[0].page_id
    cover = paths.thumb_path(page_id)
    grid = paths.grid_thumb_path(page_id)
    cover_mtime = cover.stat().st_mtime
    grid_mtime = grid.stat().st_mtime

    thumbs = ThumbnailService(paths)
    thumbs.ensure_page_thumbs(project, page_id)
    assert cover.stat().st_mtime == cover_mtime
    assert grid.stat().st_mtime == grid_mtime
