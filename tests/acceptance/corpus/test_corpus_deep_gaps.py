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


def test_many_notebooks_many_pages_fixture(tmp_path: Path) -> None:
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    clock, ids = FakeClock(), SequentialIds("many")
    items: list[ImportPlanItem] = []
    for nb in range(3):
        for pg in range(2):
            path = tmp_path / f"nb{nb}-p{pg}.png"
            data = _png_bytes(color=(nb + 1, pg + 1, 9))
            path.write_bytes(data)
            notebook_id = f"nb-many-{nb}"
            op = "create_notebook" if pg == 0 else "import_into_notebook"
            items.append(
                ImportPlanItem(
                    item_id=f"item-{nb}-{pg}",
                    op=op,
                    notebook_id=notebook_id,
                    source_sha256=sha256_bytes(data),
                    media_type="image/png",
                    page_indexes=[0],
                    source_id=f"src-{nb}-{pg}",
                    page_ids=[f"page-{nb}-{pg}"],
                    render_ids=[f"render-{nb}-{pg}"],
                    provenance={
                        "source_path": str(path),
                        "title": f"Notebook {nb}",
                        "managed_relpath": f"nb-many-{nb}",
                    },
                    original_filename=path.name,
                )
            )
    orch = ImportOrchestrator(corpus, clock=clock, ids=ids)
    run = orch.create_run_from_plan(
        ImportPlan(
            plan_id="plan-many",
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            items=items,
        )
    )
    completed = orch.commit_run(run.import_run_id)
    assert completed.status == "complete"
    assert all(item.state == "committed" for item in completed.items)
    index = CorpusIndexStore(corpus, clock=clock).load()
    assert index is not None
    assert len(index.entries) == 3
    for nb in range(3):
        project = ProjectService(
            open_project_paths(corpus.projects_dir / f"nb-many-{nb}"),
            clock=clock,
            ids=ids,
        ).load(reconcile=False)
        assert len(project.pages) == 2
        assert len(project.sources) == 2


def test_cancel_before_commit_and_with_commits(tmp_path: Path) -> None:
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    clock, ids = FakeClock(), SequentialIds("can")
    paths_data = []
    for i in range(2):
        path = tmp_path / f"c{i}.png"
        data = _png_bytes(color=(10 + i, 20, 30))
        path.write_bytes(data)
        paths_data.append((path, data))

    items = [
        ImportPlanItem(
            item_id=f"c-item-{i}",
            op="create_notebook" if i == 0 else "import_into_notebook",
            notebook_id="nb-cancel",
            source_sha256=sha256_bytes(data),
            media_type="image/png",
            page_indexes=[0],
            source_id=f"src-c-{i}",
            page_ids=[f"page-c-{i}"],
            render_ids=[f"render-c-{i}"],
            provenance={
                "source_path": str(path),
                "title": "Cancel me",
                "managed_relpath": "nb-cancel",
            },
            original_filename=path.name,
        )
        for i, (path, data) in enumerate(paths_data)
    ]
    orch = ImportOrchestrator(corpus, clock=clock, ids=ids)

    cancelled = orch.create_run_from_plan(
        ImportPlan(
            plan_id="plan-cancel-early",
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            items=items,
        )
    )
    early = orch.commit_run(cancelled.import_run_id, cancel=True)
    assert early.status == "cancelled"
    assert all(item.state == "cancelled_pending" for item in early.items)
    assert not (corpus.projects_dir / "nb-cancel").exists()

    orch2 = ImportOrchestrator(corpus, clock=clock, ids=SequentialIds("can2"))
    running = orch2.create_run_from_plan(
        ImportPlan(
            plan_id="plan-cancel-mid",
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            items=items,
        )
    )

    def crash_after_first(name: str) -> None:
        if name == "import_run_item_commit":
            raise RuntimeError("stop after first commit")

    from transcribe.corpus.orchestrator import CrashHookTriggered

    with pytest.raises(CrashHookTriggered):
        orch2.commit_run(running.import_run_id, crash_hook=crash_after_first)

    mid = orch2.commit_run(running.import_run_id, cancel=True)
    assert mid.status == "cancelled_with_commits"
    assert mid.items[0].state == "committed"
    assert mid.items[1].state == "cancelled_pending"
    project = ProjectService(
        open_project_paths(corpus.projects_dir / "nb-cancel"),
        clock=clock,
        ids=ids,
    ).load(reconcile=False)
    assert len(project.pages) == 1


def test_pdf_multipage_plan_commit_provenance(tmp_path: Path) -> None:
    from transcribe.corpus.adapters import plan_from_folder

    fixture = Path("tests/fixtures/mini_multipage.pdf")
    if not fixture.is_file():
        pytest.skip("mini_multipage.pdf fixture missing")
    folder = tmp_path / "pdf-scans"
    folder.mkdir()
    target = folder / "mini_multipage.pdf"
    target.write_bytes(fixture.read_bytes())
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    clock, ids = FakeClock(), SequentialIds("pdf")
    plan = plan_from_folder(folder, ids=ids, title="PDF batch")
    assert len(plan.items) == 1
    assert plan.items[0].media_type == "application/pdf"
    assert len(plan.items[0].page_indexes) >= 2
    orch = ImportOrchestrator(corpus, clock=clock, ids=ids)
    run = orch.create_run_from_plan(plan)
    completed = orch.commit_run(run.import_run_id)
    assert completed.status == "complete"
    assert completed.items[0].state == "committed"
    # Resolve managed path from index
    index = CorpusIndexStore(corpus, clock=clock).load()
    assert index is not None and len(index.entries) == 1
    root = corpus.projects_dir / index.entries[0].managed_relpath
    project = ProjectService(open_project_paths(root), clock=clock, ids=ids).load(
        reconcile=False
    )
    assert len(project.pages) == len(plan.items[0].page_indexes)
    assert len(project.sources) == 1
    assert project.sources[0].media_type == "application/pdf"


def test_resume_after_external_source_rename(tmp_path: Path) -> None:
    from transcribe.corpus.orchestrator import CrashHookTriggered

    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    clock, ids = FakeClock(), SequentialIds("ren")
    path = tmp_path / "before.png"
    data = _png_bytes(color=(4, 5, 6))
    path.write_bytes(data)
    item = ImportPlanItem(
        item_id="ren-item",
        op="create_notebook",
        notebook_id="nb-rename",
        source_sha256=sha256_bytes(data),
        media_type="image/png",
        page_indexes=[0],
        source_id="src-ren",
        page_ids=["page-ren"],
        render_ids=["render-ren"],
        provenance={
            "source_path": str(path),
            "title": "Rename",
            "managed_relpath": "nb-rename",
        },
        original_filename=path.name,
    )
    orch = ImportOrchestrator(corpus, clock=clock, ids=ids)
    run = orch.create_run_from_plan(
        ImportPlan(
            plan_id="plan-ren",
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            items=[item],
        )
    )

    def crash_after_source(name: str) -> None:
        if name == "source_promotion":
            raise RuntimeError("boom after source")

    with pytest.raises(CrashHookTriggered):
        orch.commit_run(run.import_run_id, crash_hook=crash_after_source)

    renamed = tmp_path / "after-rename.png"
    path.rename(renamed)
    completed = orch.commit_run(run.import_run_id)
    assert completed.status == "complete"
    assert completed.items[0].state == "committed"
    project = ProjectService(
        open_project_paths(corpus.projects_dir / "nb-rename"),
        clock=clock,
        ids=ids,
    ).load(reconcile=False)
    assert len(project.sources) == 1
    assert project.sources[0].source_id == "src-ren"


def test_bulk_cover_filename_sets_cover_page_id(tmp_path: Path) -> None:
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    clock, ids = FakeClock(), SequentialIds("cov")
    cover = tmp_path / "cover.jpg"
    other = tmp_path / "page-2.png"
    cover_data = _png_bytes(color=(200, 100, 50))
    other_data = _png_bytes(color=(50, 100, 200))
    # JPEG extension with PNG bytes is fine for media detect? Use PNG named cover.png
    cover = tmp_path / "cover.png"
    cover.write_bytes(cover_data)
    other.write_bytes(other_data)
    items = [
        ImportPlanItem(
            item_id="cov-0",
            op="create_notebook",
            notebook_id="nb-cover",
            source_sha256=sha256_bytes(cover_data),
            media_type="image/png",
            page_indexes=[0],
            source_id="src-cover",
            page_ids=["page-cover"],
            render_ids=["render-cover"],
            provenance={
                "source_path": str(cover),
                "title": "Covered",
                "managed_relpath": "nb-cover",
            },
            original_filename="cover.png",
        ),
        ImportPlanItem(
            item_id="cov-1",
            op="import_into_notebook",
            notebook_id="nb-cover",
            source_sha256=sha256_bytes(other_data),
            media_type="image/png",
            page_indexes=[0],
            source_id="src-other",
            page_ids=["page-other"],
            render_ids=["render-other"],
            provenance={"source_path": str(other), "managed_relpath": "nb-cover"},
            original_filename="page-2.png",
        ),
    ]
    orch = ImportOrchestrator(corpus, clock=clock, ids=ids)
    run = orch.create_run_from_plan(
        ImportPlan(
            plan_id="plan-cover",
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            items=items,
        )
    )
    completed = orch.commit_run(run.import_run_id)
    assert completed.status == "complete"
    project = ProjectService(
        open_project_paths(corpus.projects_dir / "nb-cover"),
        clock=clock,
        ids=ids,
    ).load(reconcile=False)
    assert project.cover_page_id == "page-cover"
