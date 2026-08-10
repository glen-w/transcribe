"""Ingest visual declutter wiring and provenance coherence."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from transcribe.declutter import identity_sha256_for
from transcribe.domain.fingerprint import sha256_bytes
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import write_json_atomic
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds


def _paper_png(*, bed: int | None = None) -> bytes:
    paper = Image.new("RGB", (400, 500), (245, 240, 230))
    ImageDraw.Draw(paper).rectangle((30, 30, 90, 90), fill=(20, 40, 180))
    if bed:
        canvas = Image.new("RGB", (400 + bed, 500), (128, 128, 128))
        canvas.paste(paper, (0, 0))
        paper = canvas
    buf = BytesIO()
    paper.save(buf, format="PNG")
    return buf.getvalue()


def test_import_declutter_enabled_crops_and_records_provenance(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    ProjectService(paths, clock=clock, ids=ids).create("t")
    ingest = IngestService(
        paths, clock=clock, ids=ids, visual_declutter_enabled=True
    )
    project = ingest.import_bytes("scan.png", _paper_png(bed=80))
    render = project.renders[project.pages[0].active_render_id]
    assert render.declutter_state == "enabled_cropped"
    assert render.declutter_inset_right and render.declutter_inset_right > 0
    assert render.width < render.declutter_original_width  # type: ignore[operator]
    assert render.declutter_identity_sha256 == identity_sha256_for(enabled=True)
    on_disk = paths.resolve_contained(render.image_relpath).read_bytes()
    assert sha256_bytes(on_disk) == render.rendered_image_sha256


def test_import_declutter_disabled_state(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    ProjectService(paths, clock=clock, ids=ids).create("t")
    ingest = IngestService(
        paths, clock=clock, ids=ids, visual_declutter_enabled=False
    )
    project = ingest.import_bytes("scan.png", _paper_png(bed=80))
    render = project.renders[project.pages[0].active_render_id]
    assert render.declutter_state == "disabled"
    assert render.declutter_ops == []
    assert render.declutter_identity_sha256 == identity_sha256_for(enabled=False)


def test_import_declutter_noop_preserves_raster_sha(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    ProjectService(paths, clock=clock, ids=ids).create("t")
    ingest = IngestService(
        paths, clock=clock, ids=ids, visual_declutter_enabled=True
    )
    from transcribe.ingest import _load_image_bytes

    raw = _paper_png(bed=None)
    normalized, _, _, pre_sha = _load_image_bytes(raw)
    project = ingest.import_bytes("clean.png", raw)
    render = project.renders[project.pages[0].active_render_id]
    assert render.declutter_state == "enabled_noop"
    assert render.rendered_image_sha256 == pre_sha
    assert paths.resolve_contained(render.image_relpath).read_bytes() == normalized


def test_recover_discards_when_promoted_sha_mismatches(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    ProjectService(paths, clock=clock, ids=ids).create("t")
    ingest = IngestService(
        paths, clock=clock, ids=ids, visual_declutter_enabled=True
    )
    project = ingest.import_bytes("scan.png", _paper_png(bed=80))
    source = project.sources[0]
    page = project.pages[0]
    render = project.renders[page.active_render_id]
    bare = ProjectService(paths, clock=clock, ids=ids).load()
    bare.sources.clear()
    bare.pages.clear()
    bare.renders.clear()
    write_json_atomic(paths.manifest, bare.as_dict())
    write_json_atomic(
        paths.ingest_journal,
        {
            "format": "transcribe.ingest-journal",
            "schema_version": 1,
            "attempt_id": "bad-sha",
            "state": "manifest_pending",
            "declutter_identity_sha256": identity_sha256_for(enabled=True),
            "visual_declutter_enabled": True,
            "source": {
                "source_id": source.source_id,
                "original_filename": source.original_filename,
                "media_type": source.media_type,
                "sha256": source.sha256,
                "page_count": 1,
                "imported_at": source.imported_at,
                "render_dpi": source.render_dpi,
                "staged_rel": ".staging/x",
                "final_rel": source.stored_relpath,
            },
            "pages": [
                {
                    "page_id": page.page_id,
                    "page_index": 0,
                    "render_id": render.render_id,
                    "width": page.width,
                    "height": page.height,
                    "png_sha": "0" * 64,
                    "pdf_page_index": None,
                    "staged_rel": ".staging/y",
                    "final_rel": render.image_relpath,
                    "renderer": render.renderer,
                    "renderer_version": render.renderer_version,
                    "source_sha256": render.source_sha256,
                    "render_dpi": render.render_dpi,
                    "declutter_state": render.declutter_state,
                }
            ],
        },
    )
    ingest.recover_incomplete_ingest()
    recovered = ProjectService(paths, clock=clock, ids=ids).load()
    assert recovered.sources == []
    assert not paths.ingest_journal.exists()


def test_recover_discards_journal_on_identity_mismatch(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    ProjectService(paths, clock=clock, ids=ids).create("t")
    write_json_atomic(
        paths.ingest_journal,
        {
            "format": "transcribe.ingest-journal",
            "schema_version": 1,
            "attempt_id": "attempt1",
            "state": "manifest_pending",
            "declutter_identity_sha256": identity_sha256_for(enabled=True),
            "visual_declutter_enabled": True,
            "source": {
                "source_id": "src1",
                "original_filename": "x.png",
                "media_type": "image/png",
                "sha256": "abc",
                "page_count": 1,
                "imported_at": "2020-01-01T00:00:00+00:00",
                "render_dpi": 200,
                "staged_rel": ".staging/attempt1/x.png",
                "final_rel": "sources/src1-x.png",
            },
            "pages": [],
        },
    )
    ingest = IngestService(
        paths, clock=clock, ids=ids, visual_declutter_enabled=False
    )
    ingest.recover_incomplete_ingest()
    assert not paths.ingest_journal.exists()
    project = ProjectService(paths, clock=clock, ids=ids).load()
    assert all(s.source_id != "src1" for s in project.sources)


def test_pdf_import_records_declutter_on_each_page(tmp_path: Path) -> None:
    import pymupdf

    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    ProjectService(paths, clock=clock, ids=ids).create("t")
    ingest = IngestService(
        paths, clock=clock, ids=ids, visual_declutter_enabled=True
    )
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page(width=400, height=500)
        page.draw_rect(page.rect, color=(0.5, 0.5, 0.5), fill=(0.5, 0.5, 0.5))
        # Inner paper-ish white rect leaving grey bed on the right
        page.draw_rect(
            pymupdf.Rect(0, 0, 320, 500), color=(0.95, 0.94, 0.9), fill=(0.95, 0.94, 0.9)
        )
        page.insert_text((40, 80), f"Page {i}")
    pdf = doc.tobytes()
    doc.close()
    project = ingest.import_bytes("scan.pdf", pdf, render_dpi=100)
    assert len(project.pages) == 3
    for page in project.pages:
        render = project.renders[page.active_render_id]
        assert render.declutter_state in {
            "enabled_cropped",
            "enabled_noop",
            "error_fallback",
        }
        assert render.declutter_identity_sha256 == identity_sha256_for(enabled=True)
        assert render.declutter_version is not None


def test_build_coordinator_honours_workspace_declutter_flag(
    tmp_path: Path, monkeypatch
) -> None:
    from types import SimpleNamespace

    from transcribe.services.job import build_coordinator

    fake = SimpleNamespace(
        effective=SimpleNamespace(
            ingest=SimpleNamespace(visual_declutter_enabled=False, render_dpi=175)
        )
    )
    monkeypatch.setattr(
        "transcribe.config.facade.get_config", lambda **_kw: fake
    )
    _paths, _projects, _coord, ingest = build_coordinator(
        tmp_path / "proj_cli", clock=FakeClock(), ids=SequentialIds()
    )
    assert ingest.visual_declutter_enabled is False
    assert ingest.default_dpi == 175
