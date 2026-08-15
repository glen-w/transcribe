"""Workspace tag catalog store and TagService host."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import write_json_atomic
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.tags import TagService
from transcribe.tagging.kernel import FORMAT, SCHEMA_VERSION
from transcribe.tagging.store import TagCatalogStore


def _runtime(tmp_path: Path) -> RuntimePaths:
    data = tmp_path / "data"
    projects = tmp_path / "projects"
    inbox = tmp_path / "inbox"
    exports = tmp_path / "exports"
    for path in (data, projects, inbox, exports, data / "config"):
        path.mkdir(parents=True, exist_ok=True)
    return RuntimePaths(
        repo_root=tmp_path,
        data_dir=data,
        projects_dir=projects,
        inbox_dir=inbox,
        export_dir=exports,
    )


def _notebook(runtime: RuntimePaths, name: str, clock: FakeClock, ids: SequentialIds):
    paths = open_project_paths(runtime.projects_dir / name)
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create(name)
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("a.png", _png_bytes())
    ingest.import_bytes("b.png", _png_bytes())
    return projects


def test_store_missing_is_empty_not_recovery(tmp_path: Path):
    runtime = _runtime(tmp_path)
    store = TagCatalogStore(runtime, clock=FakeClock(), ids=SequentialIds("tag"))
    loaded = store.load()
    assert loaded.recovery is False
    assert loaded.catalog.tags == []


def test_store_corrupt_is_fail_closed(tmp_path: Path):
    runtime = _runtime(tmp_path)
    path = runtime.data_dir / "config" / "tag-catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    store = TagCatalogStore(runtime, clock=FakeClock(), ids=SequentialIds("tag"))
    loaded = store.load()
    assert loaded.recovery is True
    assert loaded.catalog.tags == []
    assert path.read_text(encoding="utf-8") == "{not-json"


def test_store_wrong_format_is_fail_closed(tmp_path: Path):
    runtime = _runtime(tmp_path)
    path = runtime.data_dir / "config" / "tag-catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        path,
        {"format": "transcribe.project", "schema_version": 1, "tags": []},
    )
    store = TagCatalogStore(runtime, clock=FakeClock(), ids=SequentialIds("tag"))
    loaded = store.load()
    assert loaded.recovery is True


def test_assign_ensures_catalog_and_rewrite_slug(tmp_path: Path):
    runtime = _runtime(tmp_path)
    clock, ids = FakeClock(), SequentialIds("nb")
    projects = _notebook(runtime, "nb1", clock, ids)
    svc = TagService(runtime, clock=clock, ids=SequentialIds("tag"))
    page_id = projects.load().pages[0].page_id
    svc.assign_page(projects, page_id, [" Poetry ", "travel"])
    svc.assign_notebook(projects, ["scans"])
    reloaded = projects.load(reconcile=False)
    assert reloaded.pages[0].tags == ["poetry", "travel"]
    assert reloaded.tags == ["scans"]
    catalog = svc.load_catalog()
    assert catalog.get_by_slug("poetry") is not None
    assert catalog.get_by_slug("poetry").label == "Poetry"
    payload = svc.store.path.read_text(encoding="utf-8")
    assert FORMAT in payload
    assert str(SCHEMA_VERSION) in payload

    poetry = catalog.get_by_slug("poetry")
    _, result = svc.change_slug(poetry.tag_id, "poems")
    assert result.updated_notebooks == 1
    after = projects.load(reconcile=False)
    assert after.pages[0].tags == ["poems", "travel"]
    assert svc.load_catalog().get_by_slug("poetry") is None
    assert svc.load_catalog().get_by_slug("poems") is not None


def test_legacy_tags_without_catalog_still_assignable(tmp_path: Path):
    runtime = _runtime(tmp_path)
    clock, ids = FakeClock(), SequentialIds("nb")
    projects = _notebook(runtime, "nb1", clock, ids)
    page_id = projects.load().pages[0].page_id
    projects.update_page_metadata(page_id, tags=["orphan"])
    svc = TagService(runtime, clock=clock, ids=SequentialIds("tag"))
    display = svc.display("orphan")
    assert display.slug == "orphan"
    assert display.tag_id == ""
    svc.assign_page(projects, page_id, ["orphan"])
    assert svc.load_catalog().get_by_slug("orphan") is not None


def test_union_page_tags_is_additive(tmp_path: Path):
    runtime = _runtime(tmp_path)
    clock, ids = FakeClock(), SequentialIds("nb")
    projects = _notebook(runtime, "nb1", clock, ids)
    pages = projects.load().pages
    svc = TagService(runtime, clock=clock, ids=SequentialIds("tag"))
    svc.assign_page(projects, pages[0].page_id, ["keep"])
    n = svc.union_page_tags(projects, [p.page_id for p in pages], "poetry", label="Poetry")
    assert n == 2
    n2 = svc.union_page_tags(projects, [p.page_id for p in pages], "poetry")
    assert n2 == 0
    after = projects.load(reconcile=False)
    assert after.pages[0].tags == ["keep", "poetry"]
    assert after.pages[1].tags == ["poetry"]


def test_merge_and_delete_rewrite_corpus(tmp_path: Path, monkeypatch):
    runtime = _runtime(tmp_path)
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(runtime.data_dir))
    monkeypatch.setenv("TRANSCRIBE_PROJECTS_DIR", str(runtime.projects_dir))
    clock, ids = FakeClock(), SequentialIds("nb")
    projects = _notebook(runtime, "nb1", clock, ids)
    svc = TagService(runtime, clock=clock, ids=SequentialIds("tag"))
    pages = projects.load().pages
    svc.assign_page(projects, pages[0].page_id, ["poety", "travel"])
    svc.assign_page(projects, pages[1].page_id, ["poetry"])
    svc.assign_notebook(projects, ["poety"])
    catalog = svc.load_catalog()
    source = catalog.get_by_slug("poety")
    target = catalog.get_by_slug("poetry")
    assert source is not None and target is not None
    _, merge_result = svc.merge(source.tag_id, target.tag_id)
    assert merge_result.updated_notebooks == 1
    after_merge = projects.load(reconcile=False)
    assert after_merge.pages[0].tags == ["poetry", "travel"]
    assert after_merge.pages[1].tags == ["poetry"]
    assert after_merge.tags == ["poetry"]
    assert svc.load_catalog().get_by_slug("poety") is None

    poetry = svc.load_catalog().get_by_slug("poetry")
    assert poetry is not None
    _, delete_result = svc.delete(poetry.tag_id)
    assert delete_result.updated_notebooks == 1
    after_delete = projects.load(reconcile=False)
    assert after_delete.pages[0].tags == ["travel"]
    assert after_delete.pages[1].tags == []
    assert after_delete.tags == []
    assert svc.load_catalog().get_by_slug("poetry") is None


def test_rewrite_skips_notebook_with_job_lock(tmp_path: Path, monkeypatch):
    from transcribe.persistence.locks import JobLock

    runtime = _runtime(tmp_path)
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(runtime.data_dir))
    monkeypatch.setenv("TRANSCRIBE_PROJECTS_DIR", str(runtime.projects_dir))
    clock, ids = FakeClock(), SequentialIds("nb")
    projects = _notebook(runtime, "busy", clock, ids)
    svc = TagService(runtime, clock=clock, ids=SequentialIds("tag"))
    page_id = projects.load().pages[0].page_id
    svc.assign_page(projects, page_id, ["tmp"])
    tag = svc.load_catalog().get_by_slug("tmp")
    assert tag is not None
    held = JobLock(projects.paths.job_lock)
    assert held.try_acquire()
    try:
        _, result = svc.change_slug(tag.tag_id, "renamed")
        assert result.updated_notebooks == 0
        assert any("busy" in root for root in result.skipped_roots)
        still = projects.load(reconcile=False)
        assert still.pages[0].tags == ["tmp"]
        assert svc.load_catalog().get_by_slug("renamed") is not None
    finally:
        held.release()
