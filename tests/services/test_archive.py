"""Archive query, aggregation, and search tests."""

from __future__ import annotations

from pathlib import Path

from transcribe.domain.dates import ApproximateDate, pages_per_day
from transcribe.domain.models import OCRAttempt, PageResult
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import write_json_atomic
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.archive import ArchiveFilters, ArchiveService
from transcribe.services.export import ExportService
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.thumbnails import ThumbnailService
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def _runtime(tmp_path: Path) -> RuntimePaths:
    data = tmp_path / "data"
    projects = data / "projects"
    runtime = RuntimePaths(
        repo_root=tmp_path,
        data_dir=data,
        projects_dir=projects,
        inbox_dir=data / "inbox",
        export_dir=data / "exports",
    )
    runtime.ensure_layout()
    return runtime


def _make_notebook(
    runtime: RuntimePaths,
    name: str,
    *,
    title: str,
    page_specs: list[dict],
    tags: list[str] | None = None,
) -> tuple[Path, ProjectService]:
    root = runtime.projects_dir / name
    clock, ids = FakeClock(), SequentialIds(prefix=f"{name}_")
    paths = open_project_paths(root)
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create(title)
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, spec in enumerate(page_specs):
        project = ingest.import_bytes(project, f"p{i}.png", _png_bytes())
        page = project.pages[-1]
        if spec.get("text"):
            write_json_atomic(
                paths.result_path(page.page_id),
                PageResult(
                    page_id=page.page_id,
                    active_attempt_id="a1",
                    attempts=[
                        OCRAttempt(
                            attempt_id="a1",
                            status="succeeded",
                            input_fingerprint="x",
                            fingerprint_payload={},
                            raw_text=spec["text"],
                            provenance=None,
                            provider_metadata={},
                            started_at="2026-01-01T00:00:00.000Z",
                            completed_at="2026-01-01T00:00:01.000Z",
                        )
                    ],
                    updated_at="2026-01-01T00:00:01.000Z",
                ).as_dict(),
            )
        project = projects.update_page_metadata(
            page.page_id,
            date=spec.get("date"),
            tags=spec.get("tags", []),
        )
    if tags:
        projects.update_notebook_metadata(tags=tags)
    return root, projects


def test_empty_archive(tmp_path: Path):
    runtime = _runtime(tmp_path)
    archive = ArchiveService(runtime)
    timeline = archive.timeline()
    assert timeline.total == 0
    assert timeline.showing == 0
    assert archive.list_notebooks() == []
    search = archive.search("anything")
    assert search.showing == 0
    assert search.hits == []


def test_date_sorting_undated_and_period_filter(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_notebook(
        runtime,
        "n1",
        title="One",
        page_specs=[
            {"date": ApproximateDate(2018, 5, 1), "text": "alpha beer"},
            {"date": ApproximateDate(2020, 1, 10), "text": "beta"},
            {"date": None, "text": "undated gamma"},
            {"date": ApproximateDate(2018, 12, 1), "text": "delta"},
        ],
        tags=["scans"],
    )
    archive = ArchiveService(runtime)
    oldest = archive.search("", order="oldest")
    assert [h.page_id for h in oldest.hits]
    dates = [h.date.sort_key() if h.date else (9999, 99, 99) for h in oldest.hits]
    assert dates == sorted(dates)

    year_filter = ArchiveFilters(period="year", year=2018, include_undated=False)
    tl = archive.timeline(year_filter)
    assert tl.showing == 2
    assert tl.undated_count == 0
    assert sum(b.count for b in tl.bins) == 2

    with_undated = archive.timeline(ArchiveFilters(period="year", year=2018, include_undated=True))
    # Undated pages are not in 2018, so still 2 when period=year
    assert with_undated.showing == 2

    all_tl = archive.timeline(ArchiveFilters(include_undated=True))
    assert all_tl.total == 4
    assert all_tl.undated_count == 1
    assert all_tl.dated_count == 3
    # Axis labels are real bin keys, never #N/A
    assert all(b.key and "#N/A" not in b.key for b in all_tl.bins)


def test_tag_and_media_filters(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_notebook(
        runtime,
        "tagged",
        title="Tagged",
        page_specs=[
            {"date": ApproximateDate(2019, 1, 1), "text": "one", "tags": ["dream"]},
            {"date": ApproximateDate(2019, 2, 1), "text": "two", "tags": ["note"]},
        ],
        tags=["scans"],
    )
    archive = ArchiveService(runtime)
    dream = archive.timeline(ArchiveFilters(tags=("dream",)))
    assert dream.showing == 1
    media = archive.timeline(ArchiveFilters(media_types=("image",)))
    assert media.showing == 2
    project_tag = archive.timeline(ArchiveFilters(project_tags=("scans",)))
    assert project_tag.showing == 2
    inventory = archive.type_inventory()
    assert any(t.key == "image" and t.kind == "media_type" for t in inventory)
    assert any(t.key == "scans" and t.kind == "project_tag" for t in inventory)


def test_search_ordering_and_identity(tmp_path: Path):
    runtime = _runtime(tmp_path)
    root, projects = _make_notebook(
        runtime,
        "searchable",
        title="Searchable",
        page_specs=[
            {"date": ApproximateDate(2016, 8, 16), "text": "drank beer in SF"},
            {"date": ApproximateDate(2017, 1, 1), "text": "tea only"},
            {"date": ApproximateDate(2015, 1, 1), "text": "another beer night"},
        ],
    )
    archive = ArchiveService(runtime)
    hits = archive.search("beer", order="oldest")
    assert hits.showing == 2
    assert hits.hits[0].date is not None
    assert hits.hits[0].date.year == 2015
    assert hits.hits[1].date.year == 2016
    # Stable identity is page_id, not filename
    project = projects.load(reconcile=False)
    known_ids = {p.page_id for p in project.pages}
    assert {h.page_id for h in hits.hits}.issubset(known_ids)
    newest = archive.search("beer", order="newest")
    assert newest.hits[0].date.year == 2016


def test_notebook_bounds_and_pages_per_day(tmp_path: Path):
    runtime = _runtime(tmp_path)
    root, projects = _make_notebook(
        runtime,
        "rate",
        title="Rate",
        page_specs=[
            {"date": ApproximateDate(2015, 12, 30), "text": "a"},
            {"date": ApproximateDate(2016, 1, 6), "text": "b"},
            {"date": None, "text": "c"},
        ],
    )
    archive = ArchiveService(runtime)
    notebooks = archive.list_notebooks(order="oldest")
    assert len(notebooks) == 1
    nb = notebooks[0]
    assert nb.date_start is not None and nb.date_start.year == 2015
    assert nb.date_end is not None and nb.date_end.year == 2016
    # 3 pages over inclusive span 30/12/2015–06/01/2016 = 8 days → 0.38
    assert nb.pages_per_day == pages_per_day(3, nb.date_start, nb.date_end)
    assert nb.pages_per_day == 0.38
    assert nb.activity  # dated activity only

    # Explicit override both sides
    projects.update_notebook_metadata(
        date_start=ApproximateDate(2015, 1, 1),
        date_end=ApproximateDate(2015, 1, 10),
    )
    archive.invalidate(projects.load(reconcile=False).id)
    nb2 = archive.list_notebooks()[0]
    assert nb2.date_start == ApproximateDate(2015, 1, 1)
    assert nb2.date_end == ApproximateDate(2015, 1, 10)

    # Start-only override still derives end from pages
    projects.update_notebook_metadata(
        date_start=ApproximateDate(2014, 6, 1),
        date_end=None,
    )
    archive.invalidate(projects.load(reconcile=False).id)
    nb3 = archive.list_notebooks()[0]
    assert nb3.date_start == ApproximateDate(2014, 6, 1)
    assert nb3.date_end is not None and nb3.date_end.year == 2016

    # Incomplete dates → no invented precision
    assert pages_per_day(10, None, ApproximateDate(2020, 1, 1)) is None


def test_zero_result_search(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_notebook(
        runtime,
        "z",
        title="Z",
        page_specs=[{"date": ApproximateDate(2020, 1, 1), "text": "hello"}],
    )
    archive = ArchiveService(runtime)
    result = archive.search("zzzz-not-present")
    assert result.showing == 0
    assert result.hits == []
    assert result.total_indexed == 1


def test_thumbnail_and_export_metadata(tmp_path: Path):
    runtime = _runtime(tmp_path)
    root, projects = _make_notebook(
        runtime,
        "thumb",
        title="Thumb",
        page_specs=[{"date": ApproximateDate(2021, 3, 4), "text": "x", "tags": ["memento"]}],
        tags=["scans"],
    )
    project = projects.load(reconcile=False)
    paths = open_project_paths(root)
    thumbs = ThumbnailService(paths)
    cover = thumbs.cover_page_id(project)
    assert cover == project.pages[0].page_id
    thumb_path = thumbs.ensure_thumb(project, cover)
    assert thumb_path is not None and thumb_path.exists()

    notebook = ExportService(paths, projects).build_notebook(project)
    assert notebook["project"]["tags"] == ["scans"]
    assert notebook["pages"][0]["date"] == {"y": 2021, "m": 3, "d": 4}
    assert notebook["pages"][0]["tags"] == ["memento"]


def test_most_pages_ordering(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_notebook(
        runtime,
        "small",
        title="Small",
        page_specs=[{"date": ApproximateDate(2010, 1, 1), "text": "a"}],
    )
    _make_notebook(
        runtime,
        "big",
        title="Big",
        page_specs=[
            {"date": ApproximateDate(2011, 1, 1), "text": "a"},
            {"date": ApproximateDate(2011, 1, 2), "text": "b"},
            {"date": ApproximateDate(2011, 1, 3), "text": "c"},
        ],
    )
    archive = ArchiveService(runtime)
    ordered = archive.list_notebooks(order="most_pages")
    assert [n.title for n in ordered] == ["Big", "Small"]


def test_date_range_filter(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_notebook(
        runtime,
        "rng",
        title="Range",
        page_specs=[
            {"date": ApproximateDate(2017, 1, 1), "text": "early"},
            {"date": ApproximateDate(2018, 6, 1), "text": "mid"},
            {"date": ApproximateDate(2019, 12, 1), "text": "late"},
            {"date": None, "text": "undated"},
        ],
    )
    archive = ArchiveService(runtime)
    filtered = archive.timeline(
        ArchiveFilters(
            period="range",
            range_start=ApproximateDate(2018, 1, 1),
            range_end=ApproximateDate(2018, 12, 31),
            include_undated=True,
        )
    )
    assert filtered.showing == 1
    assert filtered.dated_count == 1


def test_partial_date_ordering(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_notebook(
        runtime,
        "partial",
        title="Partial",
        page_specs=[
            {"date": ApproximateDate(2016), "text": "year only"},
            {"date": ApproximateDate(2016, 3), "text": "month"},
            {"date": ApproximateDate(2016, 3, 15), "text": "day"},
            {"date": ApproximateDate(2015, 12, 1), "text": "prior"},
        ],
    )
    archive = ArchiveService(runtime)
    hits = archive.search("", order="oldest").hits
    keys = [h.date.sort_key() if h.date else None for h in hits]
    assert keys == sorted(keys)
    assert keys[0] == (2015, 12, 1)
    assert keys[-1] == (2016, 3, 15)


def test_index_refreshes_after_text_and_metadata_change(tmp_path: Path):
    runtime = _runtime(tmp_path)
    root, projects = _make_notebook(
        runtime,
        "refresh",
        title="Refresh",
        page_specs=[{"date": ApproximateDate(2020, 1, 1), "text": "before-token"}],
    )
    archive = ArchiveService(runtime)
    assert archive.search("before-token").showing == 1
    assert archive.search("after-token").showing == 0

    project = projects.load(reconcile=False)
    page_id = project.pages[0].page_id
    paths = open_project_paths(root)
    result = projects.load_page_result(page_id)
    assert result is not None
    result.edited_text = "after-token appears here"
    write_json_atomic(paths.result_path(page_id), result.as_dict())
    # Bump manifest updated_at so signature changes even if mtime is coarse.
    projects.update_page_metadata(page_id, tags=["refreshed"])

    archive.ensure_index()
    assert archive.search("after-token").showing == 1
    assert archive.search("before-token").showing == 0
    assert archive.search("after-token").hits[0].tags == ["refreshed"]


def test_approximate_date_helpers():
    d = ApproximateDate(2016, 11)
    assert d.precision == "month"
    assert d.format_display() == "11/2016"
    assert ApproximateDate.from_dict({"y": 2016, "m": 11, "d": 13}).format_display() == (
        "13/11/2016"
    )
    assert pages_per_day(20, ApproximateDate(2015, 12, 30), ApproximateDate(2016, 1, 6)) == 2.5


def test_filled_timeline_preserves_gaps(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_notebook(
        runtime,
        "gaps",
        title="Gaps",
        page_specs=[
            {"date": ApproximateDate(2017, 1, 15), "text": "burst a"},
            {"date": ApproximateDate(2022, 1, 10), "text": "burst b"},
        ],
    )
    archive = ArchiveService(runtime)
    tl = archive.timeline()
    keys = [b.key for b in tl.bins]
    assert "2017-01" in keys or any(k.startswith("2017") for k in keys)
    assert "2022-01" in keys or any(k.startswith("2022") for k in keys)
    # Intervening months/years present as zeros
    assert any(b.count == 0 for b in tl.bins)
    assert len(tl.bins) > 2


def test_year_filter_hides_unrelated_notebooks(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_notebook(
        runtime,
        "y2018",
        title="Y2018",
        page_specs=[{"date": ApproximateDate(2018, 5, 1), "text": "in year"}],
    )
    _make_notebook(
        runtime,
        "y2020",
        title="Y2020",
        page_specs=[{"date": ApproximateDate(2020, 5, 1), "text": "other"}],
    )
    archive = ArchiveService(runtime)
    nbs = archive.list_notebooks(filters=ArchiveFilters(period="year", year=2018))
    assert [n.title for n in nbs] == ["Y2018"]


def test_project_tags_are_or(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_notebook(
        runtime,
        "dreams",
        title="Dreams",
        page_specs=[{"date": ApproximateDate(2019, 1, 1), "text": "d"}],
        tags=["dreams"],
    )
    _make_notebook(
        runtime,
        "notes",
        title="Notes",
        page_specs=[{"date": ApproximateDate(2019, 2, 1), "text": "n"}],
        tags=["notes"],
    )
    archive = ArchiveService(runtime)
    both = archive.timeline(ArchiveFilters(project_tags=("dreams", "notes")))
    assert both.showing == 2
    only = archive.timeline(ArchiveFilters(project_tags=("dreams",)))
    assert only.showing == 1


def test_search_pagination(tmp_path: Path):
    runtime = _runtime(tmp_path)
    specs = [
        {"date": ApproximateDate(2020, 1, i + 1), "text": f"page token {i}"}
        for i in range(5)
    ]
    _make_notebook(runtime, "pages", title="Pages", page_specs=specs)
    archive = ArchiveService(runtime)
    page1 = archive.search("token", limit=2, offset=0)
    assert page1.showing == 2
    assert page1.total_matched == 5
    page2 = archive.search("token", limit=2, offset=2)
    assert page2.showing == 2
    assert {h.page_id for h in page1.hits}.isdisjoint({h.page_id for h in page2.hits})


def test_ensure_index_skips_when_fingerprint_unchanged(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_notebook(
        runtime,
        "ttl",
        title="TTL",
        page_specs=[{"date": ApproximateDate(2021, 1, 1), "text": "hello"}],
    )
    archive = ArchiveService(runtime)
    archive.ensure_index(force=True)
    calls = archive._ensure_calls
    archive.ensure_index()
    archive.ensure_index()
    assert archive._ensure_calls == calls
