"""Persistence contracts for archive metadata fields."""

from __future__ import annotations

from pathlib import Path

from transcribe.domain.dates import ApproximateDate
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def test_legacy_project_without_archive_fields_loads(tmp_path: Path):
    paths = open_project_paths(tmp_path / "legacy")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("Legacy")
    payload = read_json(paths.manifest)
    # Simulate pre-archive manifest: strip additive fields.
    for key in ("tags", "cover_page_id", "date_start", "date_end"):
        payload.pop(key, None)
    for page in payload.get("pages") or []:
        page.pop("date", None)
        page.pop("tags", None)
    write_json_atomic(paths.manifest, payload)
    loaded = projects.load(reconcile=False)
    assert loaded.tags == []
    assert loaded.cover_page_id is None
    assert loaded.date_start is None
    assert loaded.pages == [] or all(p.date is None and p.tags == [] for p in loaded.pages)


def test_page_and_notebook_metadata_roundtrip(tmp_path: Path):
    paths = open_project_paths(tmp_path / "meta")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("Meta")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    page_id = project.pages[0].page_id
    project = projects.update_page_metadata(
        page_id,
        date=ApproximateDate(2016, 8, 16),
        tags=["Beer", " SF "],
    )
    project = projects.update_notebook_metadata(
        tags=["scans"],
        cover_page_id=page_id,
        date_start=ApproximateDate(2016, 1),
        date_end=ApproximateDate(2016, 12, 31),
    )
    reloaded = projects.load(reconcile=False)
    page = reloaded.pages[0]
    assert page.date == ApproximateDate(2016, 8, 16)
    assert page.tags == ["beer", "sf"]
    assert reloaded.tags == ["scans"]
    assert reloaded.cover_page_id == page_id
    assert reloaded.date_start == ApproximateDate(2016, 1)
    assert reloaded.date_end == ApproximateDate(2016, 12, 31)
