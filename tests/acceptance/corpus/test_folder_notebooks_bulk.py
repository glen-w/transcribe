"""Folder-per-notebook bulk import: multi-folder plan, skip, overwrite gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.corpus.adapters import (
    OVERWRITE_CONFIRM_PHRASE,
    ON_EXISTING_OVERWRITE,
    ON_EXISTING_SKIP,
    plan_from_folders,
    scan_folder_notebooks,
)
from transcribe.corpus.folder_overwrite import prepare_folder_overwrite
from transcribe.corpus import CorpusPaths, ImportOrchestrator
from transcribe.errors import ValidationError
from transcribe.persistence.atomic import read_json
from transcribe.services.project import open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def _corpus(tmp_path: Path) -> CorpusPaths:
    paths = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    paths.projects_dir.mkdir(parents=True)
    return paths


def _child_with_pngs(parent: Path, name: str, *, colors: list[tuple[int, int, int]]) -> Path:
    folder = parent / name
    folder.mkdir()
    for i, color in enumerate(colors, start=1):
        (folder / f"{i:02d}.png").write_bytes(_png_bytes(color=color))
    return folder


def test_plan_from_folders_creates_one_notebook_per_child(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    parent = tmp_path / "dumps"
    parent.mkdir()
    _child_with_pngs(parent, "Alpha", colors=[(1, 1, 1), (2, 2, 2)])
    _child_with_pngs(parent, "Beta", colors=[(3, 3, 3)])
    (parent / "empty").mkdir()
    (parent / "loose.png").write_bytes(_png_bytes(color=(9, 9, 9)))

    ids = SequentialIds("multi")
    plan, scan = plan_from_folders(
        parent,
        ids=ids,
        corpus_paths=corpus,
        on_existing=ON_EXISTING_SKIP,
    )
    assert len(scan.new_folders) == 2
    assert scan.empty_skipped and scan.empty_skipped[0].name == "empty"
    assert not scan.already_imported

    notebook_ids = {item.notebook_id for item in plan.items}
    assert len(notebook_ids) == 2
    titles = {
        (item.provenance or {}).get("title")
        for item in plan.items
        if item.op == "create_notebook"
    }
    assert titles == {"Alpha", "Beta"}
    assert sum(1 for i in plan.items if i.op == "create_notebook") == 2
    assert sum(1 for i in plan.items if i.op == "import_into_notebook") == 1

    clock = FakeClock()
    orch = ImportOrchestrator(corpus, clock=clock, ids=SequentialIds("run"))
    # Re-plan with fresh ids for commit (plan already used SequentialIds)
    plan2, _ = plan_from_folders(
        parent,
        ids=SequentialIds("commit"),
        corpus_paths=corpus,
        on_existing=ON_EXISTING_SKIP,
    )
    run = orch.create_run_from_plan(plan2)
    completed = orch.commit_run(run.import_run_id)
    assert completed.status == "complete"
    alpha = open_project_paths(corpus.projects_dir / "Alpha")
    beta = open_project_paths(corpus.projects_dir / "Beta")
    alpha_proj = read_json(alpha.manifest)
    beta_proj = read_json(beta.manifest)
    assert alpha_proj["title"] == "Alpha"
    assert beta_proj["title"] == "Beta"
    assert len(alpha_proj["pages"]) == 2
    assert len(beta_proj["pages"]) == 1


def test_scan_detects_already_imported_and_skip_omits(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    parent = tmp_path / "dumps"
    parent.mkdir()
    _child_with_pngs(parent, "Keep", colors=[(1, 1, 1)])
    _child_with_pngs(parent, "Fresh", colors=[(4, 4, 4)])

    orch = ImportOrchestrator(corpus, clock=FakeClock(), ids=SequentialIds("first"))
    plan, _ = plan_from_folders(
        parent,
        ids=SequentialIds("p1"),
        corpus_paths=corpus,
        on_existing=ON_EXISTING_SKIP,
    )
    run = orch.create_run_from_plan(plan)
    assert orch.commit_run(run.import_run_id).status == "complete"
    old_keep_id = read_json((corpus.projects_dir / "Keep" / "project.json"))["id"]

    # Add another page into source Keep folder for a potential overwrite later
    (parent / "Keep" / "02.png").write_bytes(_png_bytes(color=(5, 5, 5)))

    scan = scan_folder_notebooks(parent, corpus)
    assert {c.managed_relpath for c in scan.already_imported} == {"Keep", "Fresh"}
    assert not scan.new_folders

    with pytest.raises(ValidationError, match="already imported"):
        plan_from_folders(
            parent,
            ids=SequentialIds("p2"),
            corpus_paths=corpus,
            on_existing=ON_EXISTING_SKIP,
        )

    # Only Fresh remains if we remove Keep from parent... instead add brand-new folder
    _child_with_pngs(parent, "NewOne", colors=[(8, 8, 8)])
    plan_skip, scan2 = plan_from_folders(
        parent,
        ids=SequentialIds("p3"),
        corpus_paths=corpus,
        on_existing=ON_EXISTING_SKIP,
    )
    assert [p.name for p in scan2.new_folders] == ["NewOne"]
    assert {c.managed_relpath for c in scan2.already_imported} == {"Keep", "Fresh"}
    titles = {
        (i.provenance or {}).get("title")
        for i in plan_skip.items
        if i.op == "create_notebook"
    }
    assert titles == {"NewOne"}
    assert (corpus.projects_dir / "Keep" / "project.json").is_file()
    assert read_json(corpus.projects_dir / "Keep" / "project.json")["id"] == old_keep_id


def test_overwrite_with_confirm_replaces_notebook(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    parent = tmp_path / "dumps"
    parent.mkdir()
    _child_with_pngs(parent, "Nb", colors=[(1, 1, 1)])

    orch = ImportOrchestrator(corpus, clock=FakeClock(), ids=SequentialIds("ow1"))
    plan1, _ = plan_from_folders(
        parent, ids=SequentialIds("c1"), corpus_paths=corpus
    )
    run1 = orch.create_run_from_plan(plan1)
    assert orch.commit_run(run1.import_run_id).status == "complete"
    old_id = read_json(corpus.projects_dir / "Nb" / "project.json")["id"]
    assert len(read_json(corpus.projects_dir / "Nb" / "project.json")["pages"]) == 1

    (parent / "Nb" / "02.png").write_bytes(_png_bytes(color=(2, 2, 2)))
    scan = scan_folder_notebooks(parent, corpus)
    assert len(scan.already_imported) == 1

    with pytest.raises(ValidationError, match="OVERWRITE ALL"):
        prepare_folder_overwrite(
            scan.already_imported, corpus, confirm="overwrite all"
        )
    assert (corpus.projects_dir / "Nb" / "project.json").is_file()
    assert read_json(corpus.projects_dir / "Nb" / "project.json")["id"] == old_id

    with pytest.raises(ValidationError, match="OVERWRITE ALL"):
        prepare_folder_overwrite(scan.already_imported, corpus, confirm="")

    plan2, scan2 = plan_from_folders(
        parent,
        ids=SequentialIds("c2"),
        corpus_paths=corpus,
        on_existing=ON_EXISTING_OVERWRITE,
    )
    assert len(scan2.already_imported) == 1
    prepare_folder_overwrite(
        scan2.already_imported,
        corpus,
        confirm=OVERWRITE_CONFIRM_PHRASE,
    )
    assert not (corpus.projects_dir / "Nb").exists()

    run2 = orch.create_run_from_plan(plan2)
    assert orch.commit_run(run2.import_run_id).status == "complete"
    new_proj = read_json(corpus.projects_dir / "Nb" / "project.json")
    assert new_proj["id"] != old_id
    assert new_proj["title"] == "Nb"
    assert len(new_proj["pages"]) == 2


def test_plan_from_folders_empty_parent_errors(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    parent = tmp_path / "empty-parent"
    parent.mkdir()
    (parent / "nope").mkdir()
    with pytest.raises(ValidationError, match="no importable child"):
        plan_from_folders(
            parent, ids=SequentialIds("e"), corpus_paths=corpus
        )


def test_inbox_and_cli_wire_folders_surfaces() -> None:
    inbox = Path("src/transcribe/ui/import_inbox.py").read_text(encoding="utf-8")
    main = Path("src/transcribe/__main__.py").read_text(encoding="utf-8")
    assert "plan_from_folders" in main
    assert '"folders"' in main or "'folders'" in main
    assert "--on-existing" in main
    assert "OVERWRITE ALL" in main
    assert "plan_from_folders" in inbox
    assert "OVERWRITE ALL" in inbox or "OVERWRITE_CONFIRM_PHRASE" in inbox
    assert "on_existing" in inbox or "import_inbox_on_existing" in inbox
