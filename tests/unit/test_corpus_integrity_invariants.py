"""Source/render integrity invariants and journal quarantine."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.domain.models import (
    PageIndex,
    Project,
    RenderProvenance,
    SourceDocument,
)
from transcribe.domain.validation import validate_project
from transcribe.errors import ValidationError
from transcribe.ingest import IngestService
from transcribe.services.doctor import DoctorService
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def _base_project(**kwargs) -> Project:
    data = {
        "format": "transcribe.project",
        "schema_version": 1,
        "id": "proj1",
        "title": "t",
        "created_at": "2026-01-01T00:00:00.000Z",
        "updated_at": "2026-01-01T00:00:00.000Z",
        "settings": {
            "model_name": "m",
            "base_url": "http://localhost:11434",
            "prompt_id": "p",
            "prompt_version": "1",
            "preprocess_profile": "none",
            "max_workers": 1,
            "generation_options": {"temperature": 0.0},
        },
        "sources": [],
        "pages": [],
        "renders": {},
    }
    data.update(kwargs)
    return Project.from_dict(data)


def test_validate_rejects_duplicate_source_page_index():
    source = SourceDocument(
        source_id="s1",
        original_filename="a.png",
        stored_relpath="sources/s1-a.png",
        media_type="image/png",
        sha256="a" * 64,
        page_count=2,
        imported_at="2026-01-01T00:00:00.000Z",
        render_dpi=200,
    )
    renders = {
        "r0": RenderProvenance(
            render_id="r0",
            source_sha256="a" * 64,
            pdf_page_index=None,
            render_dpi=200,
            renderer="pillow",
            renderer_version="1",
            rendered_image_sha256="b" * 64,
            width=10,
            height=10,
            image_relpath="pages/s1/0000/r0.png",
        ),
        "r1": RenderProvenance(
            render_id="r1",
            source_sha256="a" * 64,
            pdf_page_index=None,
            render_dpi=200,
            renderer="pillow",
            renderer_version="1",
            rendered_image_sha256="c" * 64,
            width=10,
            height=10,
            image_relpath="pages/s1/0000/r1.png",
        ),
    }
    pages = [
        PageIndex(
            page_id="p0",
            source_id="s1",
            page_index=0,
            active_render_id="r0",
            width=10,
            height=10,
        ),
        PageIndex(
            page_id="p1",
            source_id="s1",
            page_index=0,
            active_render_id="r1",
            width=10,
            height=10,
        ),
    ]
    project = _base_project(
        sources=[source.as_dict()],
        pages=[p.as_dict() for p in pages],
        renders={k: v.as_dict() for k, v in renders.items()},
    )
    with pytest.raises(ValidationError, match="duplicate \\(source_id, page_index\\)"):
        validate_project(project)


def test_validate_rejects_gapped_page_indices():
    source = SourceDocument(
        source_id="s1",
        original_filename="a.pdf",
        stored_relpath="sources/s1-a.pdf",
        media_type="application/pdf",
        sha256="a" * 64,
        page_count=2,
        imported_at="2026-01-01T00:00:00.000Z",
        render_dpi=200,
    )
    renders = {
        "r0": RenderProvenance(
            render_id="r0",
            source_sha256="a" * 64,
            pdf_page_index=0,
            render_dpi=200,
            renderer="pymupdf",
            renderer_version="1",
            rendered_image_sha256="b" * 64,
            width=10,
            height=10,
            image_relpath="pages/s1/0000/r0.png",
        ),
        "r2": RenderProvenance(
            render_id="r2",
            source_sha256="a" * 64,
            pdf_page_index=2,
            render_dpi=200,
            renderer="pymupdf",
            renderer_version="1",
            rendered_image_sha256="c" * 64,
            width=10,
            height=10,
            image_relpath="pages/s1/0002/r2.png",
        ),
    }
    pages = [
        PageIndex(
            page_id="p0",
            source_id="s1",
            page_index=0,
            active_render_id="r0",
            width=10,
            height=10,
        ),
        PageIndex(
            page_id="p2",
            source_id="s1",
            page_index=2,
            active_render_id="r2",
            width=10,
            height=10,
        ),
    ]
    project = _base_project(
        sources=[source.as_dict()],
        pages=[p.as_dict() for p in pages],
        renders={k: v.as_dict() for k, v in renders.items()},
    )
    with pytest.raises(ValidationError, match="must equal"):
        validate_project(project)


def test_corrupt_ingest_journal_is_quarantined(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    paths.ingest_journal.write_text("{not-json", encoding="utf-8")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.recover_incomplete_ingest()
    assert not paths.ingest_journal.exists()
    quarantined = list(paths.root.glob(".ingest-journal.json.*"))
    assert len(quarantined) == 1
    report = DoctorService(paths, projects).run()
    assert not report.ok
    assert any(f.code == "ingest_journal_quarantined" for f in report.findings)


def test_import_bytes_still_validates(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("note.png", _png_bytes())
    validate_project(project, paths=paths)
