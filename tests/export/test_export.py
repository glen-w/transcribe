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


def test_export_profile_large_print_options():
    from transcribe.config.defaults import builtin_profile_config

    overlay = builtin_profile_config("export", "large_print")
    assert overlay is not None
    opts = ExportOptions.from_dict(overlay["export"])
    assert opts.typography.body_size_pt == 14.0
    assert opts.typography.margin_in == 1.0


def test_format_subset_omits_unselected(tmp_path: Path):
    paths, projects = _notebook_with_edit(tmp_path)
    export = ExportService(paths, projects)
    written = export.export_all(
        dest_dir=tmp_path / "subset",
        options=ExportOptions(formats=frozenset({"json", "markdown"})),
    )
    assert "notebook" in written
    assert "markdown" in written
    assert "pdf" not in written
    assert "epub" not in written
    assert "html" not in written
    manifest = read_json(written["manifest"])
    assert set(manifest["files"]) == {"notebook", "markdown"}


def test_blank_pages_can_be_excluded(tmp_path: Path):
    paths, projects = _notebook_with_edit(tmp_path)
    from tests.conftest import FakeClock, SequentialIds
    from transcribe.ingest import IngestService
    from transcribe.services.job import JobCoordinator
    from tests.fakes import FakeVisionOCRProvider

    clock, ids = FakeClock(), SequentialIds()
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("b.png", _png_bytes())
    settings = project.settings
    settings.model_name = "fake-vision"
    project = projects.save_settings(project, settings)
    JobCoordinator(paths, projects, FakeVisionOCRProvider(), clock=clock, ids=ids).run_blocking()
    page2 = projects.load().pages[1].page_id
    projects.save_user_edit(page2, "   ")

    snap = ExportService(paths, projects).capture_snapshot()
    with_blanks = build_document([snap], ExportOptions(include_blank_pages=True))
    without = build_document([snap], ExportOptions(include_blank_pages=False))
    assert len(with_blanks.parts[0].sections) == 2
    assert len(without.parts[0].sections) == 1


def test_html_embeds_typography_css(tmp_path: Path):
    paths, projects = _notebook_with_edit(tmp_path)
    export = ExportService(paths, projects)
    html = export.build_html(
        export.capture_snapshot(),
        ExportOptions(
            typography=ExportTypography(body_font="mono", body_size_pt=13.0)
        ),
    )
    assert "13.0pt" in html or "13pt" in html
    assert "monospace" in html
    assert "transcribe.content_revision:" in html


def test_pdf_per_page_breaks_increase_page_count(tmp_path: Path):
    paths, projects = _notebook_with_edit(tmp_path)
    from tests.conftest import FakeClock, SequentialIds
    from transcribe.ingest import IngestService
    from transcribe.services.job import JobCoordinator
    from tests.fakes import FakeVisionOCRProvider

    clock, ids = FakeClock(), SequentialIds()
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("b.png", _png_bytes())
    settings = project.settings
    settings.model_name = "fake-vision"
    projects.save_settings(project, settings)
    JobCoordinator(paths, projects, FakeVisionOCRProvider(), clock=clock, ids=ids).run_blocking()
    pages = projects.load().pages
    projects.save_user_edit(pages[0].page_id, "first page text")
    projects.save_user_edit(pages[1].page_id, "second page text")

    export = ExportService(paths, projects)
    per = export.export_all(
        dest_dir=tmp_path / "per",
        options=ExportOptions(
            formats=frozenset({"pdf"}),
            page_breaks="per_page",
            title_page=False,
        ),
    )
    cont = export.export_all(
        dest_dir=tmp_path / "cont",
        options=ExportOptions(
            formats=frozenset({"pdf"}),
            page_breaks="continuous",
            title_page=False,
        ),
    )
    d_per = pymupdf.open(per["pdf"])
    d_cont = pymupdf.open(cont["pdf"])
    try:
        assert d_per.page_count >= d_cont.page_count
        assert d_per.page_count >= 2
    finally:
        d_per.close()
        d_cont.close()


def test_epub_skipped_when_dependency_missing(tmp_path: Path, monkeypatch):
    paths, projects = _notebook_with_edit(tmp_path)
    export = ExportService(paths, projects)

    def boom(*_a, **_k):
        from transcribe.services.export_epub import EpubDependencyError

        raise EpubDependencyError("missing")

    monkeypatch.setattr("transcribe.services.export.write_epub", boom)
    written = export.export_all(
        dest_dir=tmp_path / "skip",
        options=ExportOptions(formats=frozenset({"json", "epub"})),
    )
    assert "notebook" in written
    assert "epub" not in written
    manifest = read_json(written["manifest"])
    assert "epub" in manifest.get("skipped_formats", [])


def test_epub_only_raises_when_dependency_missing(tmp_path: Path, monkeypatch):
    import pytest

    paths, projects = _notebook_with_edit(tmp_path)
    export = ExportService(paths, projects)

    def boom(*_a, **_k):
        from transcribe.services.export_epub import EpubDependencyError

        raise EpubDependencyError("missing")

    monkeypatch.setattr("transcribe.services.export.write_epub", boom)
    with pytest.raises(Exception):
        export.export_all(
            dest_dir=tmp_path / "epubonly",
            options=ExportOptions(formats=frozenset({"epub"})),
        )


def test_cli_export_format_flags(tmp_path: Path):
    from transcribe.__main__ import main

    paths, _projects = _notebook_with_edit(tmp_path)
    dest = tmp_path / "cli_out"
    rc = main(
        [
            "export",
            str(paths.root),
            str(dest),
            "--format",
            "json",
            "--format",
            "html",
            "--body-font",
            "sans",
        ]
    )
    assert rc == 0
    assert (dest / "notebook.transcribe.json").exists()
    assert (dest / "notebook.html").exists()
    assert not (dest / "notebook.pdf").exists()
    html = (dest / "notebook.html").read_text(encoding="utf-8")
    assert "sans-serif" in html


def test_export_config_round_trip_in_workspace(tmp_path: Path, monkeypatch):
    from transcribe.config.models import ProfileActivations
    from transcribe.config.persistence import load_workspace_settings, save_workspace_settings
    from transcribe.runtime_paths import build_runtime_paths
    from transcribe.services.export_options import ExportConfig

    data = tmp_path / "data"
    data.mkdir(parents=True)
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(data))
    monkeypatch.setenv("TRANSCRIBE_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("TRANSCRIBE_INBOX_DIR", str(tmp_path / "inbox"))
    monkeypatch.setenv("TRANSCRIBE_EXPORT_DIR", str(tmp_path / "exports"))
    runtime = build_runtime_paths()
    cfg = {
        "analysis": {},
        "llm": {},
        "ocr": {},
        "ingest": {},
        "export": ExportConfig(
            formats=("pdf", "html"),
            typography=ExportTypography(body_font="sans", body_size_pt=12.0),
        ).as_dict(),
    }
    save_workspace_settings(
        config=cfg, activations=ProfileActivations(export="default"), runtime=runtime
    )
    loaded = load_workspace_settings(runtime=runtime)
    assert set(loaded.config["export"]["formats"]) == {"html", "pdf"}
    assert loaded.activations.export == "default"
