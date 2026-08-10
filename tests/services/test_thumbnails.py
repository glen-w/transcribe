"""Thumbnail generation preserves source aspect within a max edge."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from transcribe.ingest import IngestService
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.thumbnails import ThumbnailService
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
    wide_thumb = thumbs.ensure_thumb(project, wide.pages[0].page_id)
    tall_thumb = thumbs.ensure_thumb(project, tall.pages[1].page_id)
    assert wide_thumb is not None and tall_thumb is not None

    with Image.open(wide_thumb) as a, Image.open(tall_thumb) as b:
        assert a.size == (256, 64)
        assert b.size == (64, 256)

    assert thumbs.cover_page_id(project) == project.pages[0].page_id
