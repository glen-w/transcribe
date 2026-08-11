from __future__ import annotations

from pathlib import Path

import pymupdf

from transcribe.ingest import IngestService
from transcribe.persistence.atomic import read_json
from transcribe.services.export import ExportService
from transcribe.services.export_document import bundle_revision_hex, build_document
from transcribe.services.export_options import ExportOptions, ExportTypography
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


def _notebook_with_edit(tmp_path: Path, title: str = "Notebook") -> tuple:
    paths = open_project_paths(tmp_path / title.replace(" ", "_").lower())
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create(title)
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    settings = project.settings
    settings.model_name = "fake-vision"
    project = projects.save_settings(project, settings)
    coord = JobCoordinator(
        paths, projects, FakeVisionOCRProvider(), clock=clock, ids=ids
    )
    coord.run_blocking()
    projects.save_user_edit(project.pages[0].page_id, f"edited {title}")
    return paths, projects


def test_export_portable_no_absolute_paths(tmp_path: Path):
    paths, projects = _notebook_with_edit(tmp_path)
    export = ExportService(paths, projects)
    written = export.export_all(dest_dir=tmp_path / "out")
    assert written["manifest"].exists()
    notebook = export.build_notebook(projects.load())
    assert notebook["format"] == "transcribe.notebook"
    blob = str(notebook)
    assert str(paths.root) not in blob
    assert notebook["pages"][0]["edited"] is True
    assert notebook["pages"][0]["text"] == "edited Notebook"


def test_export_all_formats_share_revision(tmp_path: Path):
    paths, projects = _notebook_with_edit(tmp_path)
    export = ExportService(paths, projects)
    out = tmp_path / "out"
    written = export.export_all(
        dest_dir=out,
        options=ExportOptions(
            formats=frozenset({"json", "markdown", "text", "html", "pdf", "epub"})
        ),
    )
    manifest = read_json(written["manifest"])
    rev = manifest["content_revision"]
    assert rev
    assert manifest["bundle_revision"]
    assert rev in written["markdown"].read_text(encoding="utf-8")
    assert rev in written["text"].read_text(encoding="utf-8")
    assert rev in written["html"].read_text(encoding="utf-8")
    assert written["pdf"].read_bytes()[:4] == b"%PDF"
    assert written["epub"].read_bytes()[:2] == b"PK"
    notebook = read_json(written["notebook"])
    assert notebook["content_revision"] == rev


def test_typography_does_not_change_content_revision(tmp_path: Path):
    paths, projects = _notebook_with_edit(tmp_path)
    export = ExportService(paths, projects)
    snap = export.capture_snapshot()
    a = build_document([snap], ExportOptions())
    b = build_document(
        [snap],
        ExportOptions(
            typography=ExportTypography(body_size_pt=18.0, body_font="sans")
        ),
    )
    assert a.bundle_revision == b.bundle_revision
    assert a.parts[0].content_revision == snap.content_revision


def test_pdf_metadata_includes_revision(tmp_path: Path):
    paths, projects = _notebook_with_edit(tmp_path)
    export = ExportService(paths, projects)
    written = export.export_all(
        dest_dir=tmp_path / "pdfout",
        options=ExportOptions(formats=frozenset({"pdf", "json"})),
    )
    manifest = read_json(written["manifest"])
    doc = pymupdf.open(written["pdf"])
    try:
        meta = doc.metadata
        assert manifest["content_revision"] in (meta.get("subject") or "")
        assert doc.page_count >= 1
    finally:
        doc.close()


def test_multi_notebook_anthology(tmp_path: Path):
    paths_a, projects_a = _notebook_with_edit(tmp_path / "a", "Alpha")
    paths_b, projects_b = _notebook_with_edit(tmp_path / "b", "Beta")
    snap_a = ExportService.capture_snapshot_at(paths_a, projects_a)
    snap_b = ExportService.capture_snapshot_at(paths_b, projects_b)
    export = ExportService(paths_a, projects_a)
    written = export.export_snapshots(
        [snap_a, snap_b],
        dest_dir=tmp_path / "bundle",
        options=ExportOptions(
            formats=frozenset({"json", "markdown", "html", "pdf", "epub"})
        ),
        title="Two notebooks",
    )
    manifest = read_json(written["manifest"])
    assert len(manifest["notebooks"]) == 2
    expected = bundle_revision_hex(
        [
            (snap_a.project.id, snap_a.content_revision),
            (snap_b.project.id, snap_b.content_revision),
        ]
    )
    assert manifest["bundle_revision"] == expected
    assert written["bundle"].exists()
    bundle = read_json(written["bundle"])
    assert bundle["format"] == "transcribe.export-bundle"
    assert "Two notebooks" in written["markdown"].read_text(encoding="utf-8")
    assert "Alpha" in written["markdown"].read_text(encoding="utf-8")
    assert "Beta" in written["markdown"].read_text(encoding="utf-8")


def test_export_profile_compact_options():
    from transcribe.config.defaults import builtin_profile_config
    from transcribe.services.export_options import ExportOptions

    overlay = builtin_profile_config("export", "compact")
    assert overlay is not None
    opts = ExportOptions.from_dict(overlay["export"])
    assert opts.typography.body_size_pt == 10.0
    assert opts.page_breaks == "continuous"
