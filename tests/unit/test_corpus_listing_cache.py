"""Session corpus listing cache helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.corpus.paths import CorpusPaths
from transcribe.ui.corpus_listing_cache import (
    corpus_listing_token,
    get_cached_listing,
    invalidate_listing_key_prefix,
    invalidate_listing_keys,
)


def test_corpus_listing_token_stable_until_project_mtime_changes(tmp_path: Path) -> None:
    import os

    projects = tmp_path / "projects"
    data = tmp_path / "data"
    projects.mkdir()
    data.mkdir()
    nb = projects / "nb1"
    nb.mkdir()
    manifest = nb / "project.json"
    manifest.write_text("{}", encoding="utf-8")
    corpus = CorpusPaths(data_dir=data, projects_dir=projects)
    t1 = corpus_listing_token(corpus)
    t2 = corpus_listing_token(corpus)
    assert t1 == t2
    os.utime(manifest, (1_700_000_000, 1_700_000_000))
    t3 = corpus_listing_token(corpus)
    assert t3 != t1


def test_get_cached_listing_respects_force_and_invalidate() -> None:
    state: dict = {}
    calls = {"n": 0}

    def loader() -> list[int]:
        calls["n"] += 1
        return [calls["n"]]

    first = get_cached_listing(
        state,
        cache_key="c",
        token_key="t",
        token="tok-a",
        loader=loader,
    )
    second = get_cached_listing(
        state,
        cache_key="c",
        token_key="t",
        token="tok-a",
        loader=loader,
    )
    assert first == second == [1]
    assert calls["n"] == 1
    forced = get_cached_listing(
        state,
        cache_key="c",
        token_key="t",
        token="tok-a",
        loader=loader,
        force=True,
    )
    assert forced == [2]
    assert calls["n"] == 2
    invalidate_listing_keys(state, "c", "t")
    third = get_cached_listing(
        state,
        cache_key="c",
        token_key="t",
        token="tok-a",
        loader=loader,
    )
    assert third == [3]
    assert calls["n"] == 3


def test_get_cached_listing_reloads_when_token_changes() -> None:
    state: dict = {}
    calls = {"n": 0}

    def loader() -> list[str]:
        calls["n"] += 1
        return [f"v{calls['n']}"]

    assert get_cached_listing(
        state,
        cache_key="c",
        token_key="t",
        token="tok-1",
        loader=loader,
    ) == ["v1"]
    assert get_cached_listing(
        state,
        cache_key="c",
        token_key="t",
        token="tok-1",
        loader=loader,
    ) == ["v1"]
    assert calls["n"] == 1
    assert get_cached_listing(
        state,
        cache_key="c",
        token_key="t",
        token="tok-2",
        loader=loader,
    ) == ["v2"]
    assert calls["n"] == 2
    assert state["t"] == "tok-2"


def test_invalidate_listing_key_prefix() -> None:
    state = {
        "tx_batch_import_enriched:run-a": [1],
        "tx_batch_import_enriched:run-a:token": "t",
        "tx_batch_import_enriched:run-b": [2],
        "other": [3],
    }
    invalidate_listing_key_prefix(state, "tx_batch_import_enriched")
    assert "other" in state
    assert state["other"] == [3]
    assert not any(str(k).startswith("tx_batch_import_enriched") for k in state)


def test_invalidate_batch_ocr_caches_clears_run_lists_and_enrich(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import transcribe.ui.run_transcribe as rt

    state: dict = {
        rt._OCR_CANDIDATES_KEY: ["c"],
        rt._OCR_CANDIDATES_TOKEN_KEY: "tok",
        rt._LIGHT_PICKER_KEY: ["p"],
        rt._LIGHT_PICKER_TOKEN_KEY: "tok",
        rt._IMPORT_RUNS_KEY: ["r"],
        rt._IMPORT_RUNS_TOKEN_KEY: "tok",
        rt._RECENT_OCR_RUNS_KEY: ["recent"],
        rt._RECENT_OCR_RUNS_TOKEN_KEY: "tok",
        f"{rt._IMPORT_ENRICHED_PREFIX}:imp-1": ["e"],
        f"{rt._IMPORT_ENRICHED_PREFIX}:imp-1:token": "tok",
        "unrelated": True,
    }
    monkeypatch.setattr(rt.st, "session_state", state)
    rt.invalidate_batch_ocr_caches()
    assert "unrelated" in state
    for key in (
        rt._OCR_CANDIDATES_KEY,
        rt._IMPORT_RUNS_KEY,
        rt._RECENT_OCR_RUNS_KEY,
        f"{rt._IMPORT_ENRICHED_PREFIX}:imp-1",
    ):
        assert key not in state


def test_invalidate_ocr_and_analyse_listings_clears_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import transcribe.ui.run_analysis_batch as ax
    import transcribe.ui.run_transcribe as rt

    state: dict = {
        rt._IMPORT_RUNS_KEY: ["r"],
        ax._PENDING_SCAN_KEY: ["scan"],
        ax._IMPORT_RUNS_KEY: ["ar"],
        ax._RECENT_ANALYSE_RUNS_KEY: ["rr"],
        "keep": 1,
    }
    monkeypatch.setattr(rt.st, "session_state", state)
    monkeypatch.setattr(ax.st, "session_state", state)
    rt._invalidate_ocr_and_analyse_listings()
    assert "keep" in state
    assert rt._IMPORT_RUNS_KEY not in state
    assert ax._PENDING_SCAN_KEY not in state
    assert ax._IMPORT_RUNS_KEY not in state
    assert ax._RECENT_ANALYSE_RUNS_KEY not in state
