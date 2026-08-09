"""Page date suggestion, inheritance, concurrency, and OCR isolation."""

from __future__ import annotations

import threading
from pathlib import Path

from transcribe.analysis.adapter import build_page_v1_document
from transcribe.analysis.document import content_fingerprint
from transcribe.domain.dates import ApproximateDate
from transcribe.domain.models import OCRAttempt, PageResult
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import write_json_atomic
from transcribe.ports import to_iso
from transcribe.services.export import ExportService
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


def _seed_page_text(projects: ProjectService, page_id: str, text: str, clock: FakeClock) -> None:
    write_json_atomic(
        projects.paths.result_path(page_id),
        PageResult(
            page_id=page_id,
            active_attempt_id="a1",
            attempts=[
                OCRAttempt(
                    attempt_id="a1",
                    status="succeeded",
                    input_fingerprint="x",
                    fingerprint_payload={},
                    raw_text=text,
                    provenance=None,
                    provider_metadata={},
                    started_at=to_iso(clock.now()),
                    completed_at=to_iso(clock.now()),
                )
            ],
            updated_at=to_iso(clock.now()),
        ).as_dict(),
    )


def test_suggest_extract_and_inherit(tmp_path: Path):
    paths = open_project_paths(tmp_path / "sug")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("S")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    project = ingest.import_bytes("b.png", _png_bytes(color=(1, 2, 3)))
    p0, p1 = project.pages[0].page_id, project.pages[1].page_id
    _seed_page_text(projects, p0, "260523 1504\nhello", clock)
    _seed_page_text(projects, p1, "no stamp here", clock)

    assert projects.suggest_page_date(p0) is True
    page0 = projects.load(reconcile=False).pages[0]
    assert page0.date == ApproximateDate(2026, 5, 23)
    assert page0.date_approved is False
    assert page0.date_source == "extracted"

    assert projects.suggest_page_date(p1) is True
    page1 = projects.load(reconcile=False).pages[1]
    assert page1.date == ApproximateDate(2026, 5, 23)
    assert page1.date_approved is False
    assert page1.date_source == "inherited"


def test_fill_page_dates_ordered_single_write(tmp_path: Path):
    paths = open_project_paths(tmp_path / "fill")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("F")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i in range(3):
        ingest.import_bytes(f"{i}.png", _png_bytes(color=(i, i, i)))
    project = projects.load(reconcile=False)
    ids_pages = [p.page_id for p in project.pages]
    _seed_page_text(projects, ids_pages[0], "260523 note", clock)
    _seed_page_text(projects, ids_pages[1], "plain", clock)
    _seed_page_text(projects, ids_pages[2], "plain", clock)

    n = projects.fill_page_dates_ordered()
    assert n == 3
    pages = projects.load(reconcile=False).pages
    assert [p.date for p in pages] == [ApproximateDate(2026, 5, 23)] * 3
    assert pages[0].date_source == "extracted"
    assert pages[1].date_source == "inherited"
    assert pages[2].date_source == "inherited"


def test_approved_date_not_overwritten_by_suggest(tmp_path: Path):
    paths = open_project_paths(tmp_path / "appr")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("A")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    pid = project.pages[0].page_id
    projects.approve_page_date(pid, ApproximateDate(2019, 1, 1))
    _seed_page_text(projects, pid, "260523 should not win", clock)
    assert projects.suggest_page_date(pid) is False
    page = projects.load(reconcile=False).pages[0]
    assert page.date == ApproximateDate(2019, 1, 1)
    assert page.date_approved is True


def test_concurrency_human_approve_wins(tmp_path: Path):
    paths = open_project_paths(tmp_path / "race")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("R")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    project = ingest.import_bytes("b.png", _png_bytes(color=(9, 9, 9)))
    p0, p1 = project.pages[0].page_id, project.pages[1].page_id
    _seed_page_text(projects, p0, "260523", clock)
    _seed_page_text(projects, p1, "plain", clock)
    human = ApproximateDate(2018, 8, 8)
    errors: list[BaseException] = []

    def suggest() -> None:
        try:
            for _ in range(20):
                projects.suggest_page_date(p0)
                projects.fill_page_dates_ordered()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def approve() -> None:
        try:
            for _ in range(20):
                projects.approve_page_date(p0, human)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=suggest), threading.Thread(target=approve)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    # Final approve after races to assert human path works under contention;
    # then verify approved value is stable against further suggests.
    projects.approve_page_date(p0, human)
    assert projects.suggest_page_date(p0) is False
    projects.fill_page_dates_ordered()
    page = projects.load(reconcile=False).pages[0]
    assert page.date == human
    assert page.date_approved is True
    assert page.date_source is None


def test_ocr_success_despite_suggestion_failure(tmp_path: Path, monkeypatch):
    paths = open_project_paths(tmp_path / "iso")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("I")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    settings = project.settings
    settings.model_name = "fake-vision"
    projects.save_settings(project, settings)

    def boom(_page_id: str) -> bool:
        raise RuntimeError("suggest exploded")

    monkeypatch.setattr(projects, "suggest_page_date", boom)
    coord = JobCoordinator(
        paths, projects, FakeVisionOCRProvider(default_text="260523 hi"), clock=clock, ids=ids
    )
    coord.run_blocking()
    progress = coord.get_progress()
    assert progress.status == "completed"
    assert progress.completed == 1
    assert progress.failed == 0
    result = projects.load_page_result(project.pages[0].page_id)
    assert result is not None
    assert result.active_attempt() is not None
    assert result.active_attempt().status == "succeeded"


def test_analysis_fingerprint_date_value_not_approval(tmp_path: Path):
    paths = open_project_paths(tmp_path / "fp")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("FP")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    pid = project.pages[0].page_id
    _seed_page_text(projects, pid, "day precision page", clock)
    projects.approve_page_date(pid, ApproximateDate(2020, 5, 23))
    doc1 = build_page_v1_document(projects.load(reconcile=False), projects)
    fp1 = content_fingerprint(doc1)

    from transcribe.persistence.atomic import read_json
    from transcribe.persistence.locks import mutation_lock
    from transcribe.persistence.schema import require_format

    with mutation_lock(paths.mutation_lock):
        payload = require_format(read_json(paths.manifest), "transcribe.project")
        payload["pages"][0]["date_approved"] = False
        payload["pages"][0]["date_source"] = "extracted"
        write_json_atomic(paths.manifest, payload)
    doc2 = build_page_v1_document(projects.load(reconcile=False), projects)
    assert content_fingerprint(doc2) == fp1

    projects.approve_page_date(pid, ApproximateDate(2021, 1, 1))
    doc3 = build_page_v1_document(projects.load(reconcile=False), projects)
    assert content_fingerprint(doc3) != fp1


def test_export_always_emits_date_triple(tmp_path: Path):
    paths = open_project_paths(tmp_path / "ex")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("E")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for name in ("a.png", "b.png", "c.png", "d.png"):
        ingest.import_bytes(name, _png_bytes())
    pages = projects.load(reconcile=False).pages
    projects.approve_page_date(pages[0].page_id, None)
    projects.approve_page_date(pages[1].page_id, ApproximateDate(2020, 1, 2))
    _seed_page_text(projects, pages[2].page_id, "260523", clock)
    projects.suggest_page_date(pages[2].page_id)
    _seed_page_text(projects, pages[3].page_id, "plain", clock)
    projects.suggest_page_date(pages[3].page_id)

    notebook = ExportService(paths, projects).build_notebook(projects.load(reconcile=False))
    triples = [
        (p["date"], p["date_approved"], p["date_source"]) for p in notebook["pages"]
    ]
    assert triples[0] == (None, True, None)
    assert triples[1] == ({"y": 2020, "m": 1, "d": 2}, True, None)
    assert triples[2] == ({"y": 2026, "m": 5, "d": 23}, False, "extracted")
    assert triples[3] == ({"y": 2026, "m": 5, "d": 23}, False, "inherited")
