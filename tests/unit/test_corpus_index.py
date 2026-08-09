"""Corpus index and ImportRun foundation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.corpus import (
    CorpusIndexStore,
    CorpusPaths,
    ImportRun,
    ImportRunStore,
    validate_entry_matches_project,
)
from transcribe.errors import CorpusError, ValidationError
from transcribe.persistence.atomic import write_json_atomic
from tests.conftest import FakeClock


def test_corpus_index_register_and_order(tmp_path: Path):
    runtime_data = tmp_path / "data"
    projects = runtime_data / "projects"
    projects.mkdir(parents=True)
    paths = CorpusPaths(data_dir=runtime_data, projects_dir=projects)
    store = CorpusIndexStore(paths, clock=FakeClock())

    nb = projects / "nb-a"
    nb.mkdir()
    write_json_atomic(
        nb / "project.json",
        {
            "format": "transcribe.project",
            "schema_version": 1,
            "id": "notebook-aaa",
            "title": "A",
            "created_at": "2026-01-01T00:00:00.000Z",
            "updated_at": "2026-01-01T00:00:00.000Z",
            "settings": {},
            "sources": [],
            "pages": [],
            "renders": {},
        },
    )

    index = store.register_notebook(
        notebook_id="notebook-aaa",
        managed_relpath="nb-a",
        project_id="notebook-aaa",
    )
    assert [e.notebook_id for e in index.entries] == ["notebook-aaa"]

    store.register_notebook(
        notebook_id="notebook-bbb",
        managed_relpath="nb-b",
        project_id="notebook-bbb",
    )
    (projects / "nb-b").mkdir(exist_ok=True)
    loaded = store.load()
    assert loaded is not None
    assert loaded.notebook_ids() == ["notebook-aaa", "notebook-bbb"]


def test_corpus_index_rejects_notebook_id_mismatch():
    with pytest.raises(ValidationError):
        validate_entry_matches_project(
            notebook_id="a", project_id="b"
        )


def test_corpus_index_rejects_path_escape(tmp_path: Path):
    paths = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    paths.projects_dir.mkdir(parents=True)
    store = CorpusIndexStore(paths, clock=FakeClock())
    with pytest.raises((CorpusError, ValidationError, ValueError)):
        store.register_notebook(
            notebook_id="x",
            managed_relpath="../outside",
            project_id="x",
        )


def test_import_run_roundtrip(tmp_path: Path):
    paths = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    store = ImportRunStore(paths)
    run = ImportRun(
        import_run_id="run1",
        plan_id="plan1",
        plan_fingerprint="a" * 64,
        import_policy_id="skip_existing_v1",
        created_at="2026-01-01T00:00:00.000Z",
        updated_at="2026-01-01T00:00:00.000Z",
        status="complete",
    )
    store.save(run)
    loaded = store.load("run1")
    assert loaded.plan_id == "plan1"
    assert loaded.status == "complete"
