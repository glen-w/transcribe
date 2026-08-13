"""Phase 5 product hardening: provenance-aware export under content_revision."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from transcribe.domain.content_revision import content_revision_hex
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import read_json
from transcribe.services.export import ExportService
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds


def _png_bytes() -> bytes:
    from io import BytesIO

    img = Image.new("RGB", (32, 32), (10, 20, 30))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _project(tmp_path: Path, texts: list[str]):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("p5")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, _ in enumerate(texts):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    return projects, paths


def test_export_artifacts_share_content_revision(tmp_path: Path):
    projects, paths = _project(
        tmp_path,
        [
            "Export provenance page one with enough text for a stable revision.",
            "Export provenance page two also carries enough text content here.",
        ],
    )
    service = ExportService(paths, projects)
    snap = service.capture_snapshot()
    expected = content_revision_hex(snap.project, snap.results)
    assert snap.content_revision == expected

    written = service.export_all(dest_dir=tmp_path / "out")
    notebook = read_json(written["notebook"])
    manifest = read_json(written["manifest"])
    md = written["markdown"].read_text(encoding="utf-8")
    txt = written["text"].read_text(encoding="utf-8")

    assert notebook["content_revision"] == expected
    assert manifest["content_revision"] == expected
    assert manifest["format"] == "transcribe.export-manifest"
    assert md.startswith(f"<!-- transcribe.content_revision: {expected} -->")
    assert txt.startswith(f"# transcribe.content_revision: {expected}")


def test_export_revision_changes_after_edit(tmp_path: Path):
    projects, paths = _project(
        tmp_path,
        ["Export edit sensitivity text with enough words for hashing identity."],
    )
    service = ExportService(paths, projects)
    first = service.export_all(dest_dir=tmp_path / "out1")
    rev1 = read_json(first["notebook"])["content_revision"]

    project = projects.load(reconcile=False)
    projects.save_user_edit(
        project.pages[0].page_id,
        "Export edit sensitivity text CHANGED with enough words for hashing identity.",
    )
    second = service.export_all(dest_dir=tmp_path / "out2")
    rev2 = read_json(second["notebook"])["content_revision"]
    assert rev1 != rev2
