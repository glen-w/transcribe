"""Session rerun caches for Streamlit shell / Review / View hot paths."""

from __future__ import annotations

from pathlib import Path

from transcribe.ui.rerun_cache import (
    archive_generation_token,
    cached_notebook_has_published_analysis,
    get_cached_review_queue_index,
    get_cached_view_health,
    invalidate_analysis_ui_caches,
    invalidate_published_analysis_cache,
    invalidate_review_queue_cache,
    invalidate_view_health_cache,
    review_queue_token,
    review_repairs_current,
    view_health_fs_token,
)
from transcribe.ui.review_queue import ReviewQueueIndex


def test_archive_generation_token_reads_file(tmp_path: Path) -> None:
    data = tmp_path / "data"
    cache = data / "cache"
    cache.mkdir(parents=True)
    (cache / "archive.generation").write_text("42\n", encoding="utf-8")
    assert archive_generation_token(data) == "42"
    assert archive_generation_token(tmp_path / "missing") == "0"


def test_cached_published_analysis_hits_until_generation_changes(
    tmp_path: Path, monkeypatch
) -> None:
    import transcribe.ui.rerun_cache as rc

    root = tmp_path / "nb"
    root.mkdir()
    calls = {"n": 0}

    def fake_has(path) -> bool:
        calls["n"] += 1
        return True

    monkeypatch.setattr(rc, "notebook_has_published_analysis", fake_has)
    state: dict = {}
    assert cached_notebook_has_published_analysis(state, root, generation="1") is True
    assert cached_notebook_has_published_analysis(state, root, generation="1") is True
    assert calls["n"] == 1
    assert cached_notebook_has_published_analysis(state, root, generation="2") is True
    assert calls["n"] == 2
    invalidate_published_analysis_cache(state, root)
    assert cached_notebook_has_published_analysis(state, root, generation="2") is True
    assert calls["n"] == 3


def _seed_notebook(tmp_path: Path):
    from transcribe.ingest import IngestService
    from transcribe.ports import to_iso
    from transcribe.services.project import ProjectService, open_project_paths
    from tests.conftest import FakeClock, SequentialIds
    from tests.ingest.test_ingest import _png_bytes

    paths = open_project_paths(tmp_path / "nb")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("Rerun cache")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("0.png", _png_bytes(color=(1, 2, 3)))
    project = projects.load(reconcile=False)
    return projects, project, paths


def test_review_queue_token_changes_with_result_mtime(tmp_path: Path) -> None:
    import os

    projects, project, paths = _seed_notebook(tmp_path)
    page_id = project.pages[0].page_id
    result = paths.result_path(page_id)
    result.write_text("{}", encoding="utf-8")
    t1 = review_queue_token(project, results_dir=paths.results_dir)
    os.utime(result, (1_700_000_000, 1_700_000_000))
    t2 = review_queue_token(project, results_dir=paths.results_dir)
    assert t1 != t2


def test_get_cached_review_queue_index_repairs_once(tmp_path: Path) -> None:
    projects, project, paths = _seed_notebook(tmp_path)
    page_id = project.pages[0].page_id
    repairs = {"n": 0}
    loads = {"n": 0}

    def repair(pid: str) -> None:
        repairs["n"] += 1

    def load_result(pid: str):
        loads["n"] += 1
        return None

    state: dict = {}
    idx1 = get_cached_review_queue_index(
        state,
        root=paths.root,
        project=project,
        results_dir=paths.results_dir,
        base_page_ids=[page_id],
        load_page_result=load_result,
        repair_page=repair,
    )
    assert isinstance(idx1, ReviewQueueIndex)
    assert repairs["n"] == 1
    loads_after_first = loads["n"]
    idx2 = get_cached_review_queue_index(
        state,
        root=paths.root,
        project=project,
        results_dir=paths.results_dir,
        base_page_ids=[page_id],
        load_page_result=load_result,
        repair_page=repair,
    )
    assert idx2 is idx1
    assert repairs["n"] == 1
    assert loads["n"] == loads_after_first
    token = review_queue_token(project, results_dir=paths.results_dir)
    assert review_repairs_current(state, paths.root, token)
    invalidate_review_queue_cache(state, paths.root)
    get_cached_review_queue_index(
        state,
        root=paths.root,
        project=project,
        results_dir=paths.results_dir,
        base_page_ids=[page_id],
        load_page_result=load_result,
        repair_page=repair,
    )
    assert repairs["n"] == 2


def test_view_health_cache_hit_and_invalidate(tmp_path: Path) -> None:
    root = tmp_path / "nb"
    root.mkdir()
    (root / "project.json").write_text("{}", encoding="utf-8")
    results = root / "results"
    results.mkdir()
    (results / "p1.json").write_text("{}", encoding="utf-8")
    state: dict = {}
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return {"batch_health": {"status": "healthy"}, "ids": {}}

    first = get_cached_view_health(
        state, root=root, active_run_status=None, loader=loader
    )
    second = get_cached_view_health(
        state, root=root, active_run_status=None, loader=loader
    )
    assert first == second
    assert calls["n"] == 1
    # Run status change must miss
    get_cached_view_health(
        state, root=root, active_run_status="running", loader=loader
    )
    assert calls["n"] == 2
    invalidate_view_health_cache(state, root)
    get_cached_view_health(
        state, root=root, active_run_status="running", loader=loader
    )
    assert calls["n"] == 3
    token = view_health_fs_token(root, active_run_status="running")
    assert "run=running" in token


def test_invalidate_analysis_ui_caches_clears_both(tmp_path: Path, monkeypatch) -> None:
    import transcribe.ui.rerun_cache as rc

    root = tmp_path / "nb"
    root.mkdir()
    monkeypatch.setattr(rc, "notebook_has_published_analysis", lambda _p: True)
    state: dict = {}
    cached_notebook_has_published_analysis(state, root, generation="1")
    get_cached_view_health(
        state,
        root=root,
        active_run_status=None,
        loader=lambda: {"ok": True},
    )
    invalidate_analysis_ui_caches(state, root)
    assert root.as_posix() not in state.get("tx_nav_published_by_root", {})
    assert f"tx_view_health:{root}" not in state
