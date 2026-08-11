"""Deepened corpus coverage: folder adapter, other-notebook skip, CLI/Inbox wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.corpus.adapters import plan_from_folder
from transcribe.corpus.duplicates import (
    CLASS_SAME_BYTES_OTHER_NOTEBOOK,
    should_skip_for_policy,
)
from transcribe.corpus import (
    CorpusIndexStore,
    CorpusPaths,
    ImportOrchestrator,
    ImportPlan,
    ImportPlanItem,
    POLICY_CREATE_DUPLICATE_V1,
    POLICY_SKIP_EXISTING_V1,
)
from transcribe.domain.fingerprint import sha256_bytes
from transcribe.errors import ValidationError
from transcribe.ingest import IngestService
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def test_plan_from_folder_multi_file_and_unicode(tmp_path: Path) -> None:
    folder = tmp_path / "scans"
    folder.mkdir()
    (folder / "01.png").write_bytes(_png_bytes(color=(1, 1, 1)))
    (folder / "café-02.png").write_bytes(_png_bytes(color=(2, 2, 2)))
    ids = SequentialIds("fold")
    plan = plan_from_folder(folder, ids=ids, title="Unicode batch")
    assert len(plan.items) == 2
    assert plan.items[0].op == "create_notebook"
    assert plan.items[1].op == "import_into_notebook"
    assert plan.items[0].notebook_id == plan.items[1].notebook_id
    assert plan.items[1].original_filename == "café-02.png"
    assert plan.fingerprint()


def test_plan_from_folder_refuses_duplicate_basenames(tmp_path: Path) -> None:
    folder = tmp_path / "bad"
    folder.mkdir()
    (folder / "a.png").write_bytes(_png_bytes(color=(1, 1, 1)))
    # Case-insensitive duplicate via hard conflict on same lower name is hard on
    # case-sensitive FS; simulate by two files that normalize equal in adapter.
    # Adapter compares lowercased names — create A.PNG and a.png when possible.
    upper = folder / "A.PNG"
    try:
        upper.write_bytes(_png_bytes(color=(3, 3, 3)))
    except OSError:
        pytest.skip("filesystem cannot hold A.PNG alongside a.png")
    if upper.resolve() == (folder / "a.png").resolve():
        pytest.skip("case-insensitive filesystem")
    with pytest.raises(ValidationError, match="ordering ambiguity"):
        plan_from_folder(folder, ids=SequentialIds("dup"))


def test_skip_existing_does_not_skip_other_notebook_bytes(tmp_path: Path) -> None:
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    data = _png_bytes(color=(7, 8, 9))
    clock, ids = FakeClock(), SequentialIds("oth")
    paths = open_project_paths(corpus.projects_dir / "donor")
    donor = ProjectService(paths, clock=clock, ids=ids).create("donor")
    IngestService(paths, clock=clock, ids=ids).import_bytes("note.png", data)
    CorpusIndexStore(corpus, clock=clock).register_notebook(
        notebook_id=donor.id,
        managed_relpath="donor",
        project_id=donor.id,
    )

    item = ImportPlanItem(
        item_id="item1",
        op="create_notebook",
        notebook_id="nb-new",
        source_sha256=sha256_bytes(data),
        media_type="image/png",
        page_indexes=[0],
        source_id="src-new",
        page_ids=["page-new"],
        render_ids=["render-new"],
        provenance={
            "source_path": str(tmp_path / "copy.png"),
            "title": "copy",
            "managed_relpath": "copy-nb",
        },
        original_filename="copy.png",
    )
    (tmp_path / "copy.png").write_bytes(data)
    assert not should_skip_for_policy(
        __import__(
            "transcribe.corpus.duplicates", fromlist=["classify_duplicate"]
        ).classify_duplicate(corpus, item),
        POLICY_SKIP_EXISTING_V1,
    )
    orch = ImportOrchestrator(corpus, clock=clock, ids=ids)
    run = orch.create_run_from_plan(
        ImportPlan(
            plan_id="plan-other",
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            items=[item],
        )
    )
    completed = orch.commit_run(run.import_run_id)
    assert completed.status == "complete"
    assert completed.items[0].state == "committed"
    assert completed.items[0].skip_classification == CLASS_SAME_BYTES_OTHER_NOTEBOOK
    loaded = ProjectService(
        open_project_paths(corpus.projects_dir / "copy-nb"),
        clock=clock,
        ids=ids,
    ).load(reconcile=False)
    assert len(loaded.sources) == 1
    assert loaded.sources[0].source_id == "src-new"


def test_inbox_and_cli_wire_bulk_import_surfaces() -> None:
    shell = Path("src/transcribe/ui/shell.py").read_text(encoding="utf-8")
    app = Path("src/transcribe/ui/app.py").read_text(encoding="utf-8")
    main = Path("src/transcribe/__main__.py").read_text(encoding="utf-8")
    assert '"Inbox"' in shell
    assert "render_import_inbox" in app
    assert 'mode == "Inbox"' in app
    assert "bulk-import" in main
    assert "corpus-doctor" in main
    assert "plan_from_folder" in main
