from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from transcribe.errors import IngestError
from transcribe.ingest import IngestService
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds


def _png_bytes(color=(20, 40, 60), size=(64, 48)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pdf_bytes(pages: int = 2) -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=200, height=200)
        page.insert_text((20, 40), f"Page {i}")
    data = doc.tobytes()
    doc.close()
    return data


def test_import_bytes_png(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes(project, "note.png", _png_bytes())
    assert len(project.pages) == 1
    assert project.pages[0].page_id.startswith("id")
    render = project.renders[project.pages[0].active_render_id]
    assert paths.resolve_contained(render.image_relpath).exists()
    # user-facing original is copied under sources/
    assert paths.resolve_contained(project.sources[0].stored_relpath).exists()


def test_import_pdf(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes(project, "scan.pdf", _pdf_bytes(3), render_dpi=100)
    assert len(project.pages) == 3
    assert project.pages[0].page_index == 0
    assert "pages/" in project.renders[project.pages[0].active_render_id].image_relpath


def test_import_path_does_not_modify_user_file(tmp_path: Path):
    user = tmp_path / "original.png"
    user.write_bytes(_png_bytes())
    before = user.read_bytes()
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_path(project, user)
    assert user.read_bytes() == before


def test_rejects_escape_filename_traversal(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes(project, "../../evil.png", _png_bytes())
    stored = project.sources[0].stored_relpath
    assert ".." not in stored
    assert stored.startswith("sources/")


def test_oversized_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from transcribe import ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "MAX_SOURCE_BYTES", 10)
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    with pytest.raises(IngestError):
        ingest.import_bytes(project, "big.png", _png_bytes())
