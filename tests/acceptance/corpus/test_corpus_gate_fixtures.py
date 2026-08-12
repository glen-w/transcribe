"""Acceptance gate fixture coverage (corpus-integrity.md § acceptance gate #6)."""

from __future__ import annotations

from pathlib import Path

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
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import write_json_atomic
from transcribe.services.corpus_doctor import CorpusDoctorService
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


def _corpus(tmp_path: Path) -> CorpusPaths:
    paths = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    paths.projects_dir.mkdir(parents=True)
    return paths


def _bulk_import_one(
    corpus: CorpusPaths,
    tmp_path: Path,
    *,
    name: str = "scan.png",
    color: tuple[int, int, int] = (11, 22, 33),
    notebook_id: str = "nb-gate",
    managed_relpath: str = "nb-gate",
    source_id: str = "src-gate",
    page_id: str = "page-gate",
    render_id: str = "render-gate",
    policy: str = POLICY_SKIP_EXISTING_V1,
) -> tuple[object, Path, bytes]:
    data = _png_bytes(color=color)
    path = tmp_path / name
    path.write_bytes(data)
    clock, ids = FakeClock(), SequentialIds("gate")
    orch = ImportOrchestrator(corpus, clock=clock, ids=ids)
    item = ImportPlanItem(
        item_id="item-1",
        op="create_notebook",
        notebook_id=notebook_id,
        source_sha256=sha256_bytes(data),
        media_type="image/png",
        page_indexes=[0],
        source_id=source_id,
        page_ids=[page_id],
        render_ids=[render_id],
        provenance={
            "source_path": str(path),
            "title": "Gate",
            "managed_relpath": managed_relpath,
        },
        original_filename=path.name,
    )
    run = orch.create_run_from_plan(
        ImportPlan(plan_id=f"plan-{name}", import_policy_id=policy, items=[item])
    )
    completed = orch.commit_run(run.import_run_id)
    assert completed.status == "complete"
    assert completed.items[0].state == "committed"
    return completed, path, data


def test_missing_managed_source_fails_deep_doctor(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    _bulk_import_one(corpus, tmp_path)
    root = corpus.projects_dir / "nb-gate"
    project = ProjectService(
        open_project_paths(root), clock=FakeClock(), ids=SequentialIds("load")
    ).load(reconcile=False)
    source_path = root / project.sources[0].stored_relpath
    assert source_path.is_file()
    source_path.unlink()

    report = CorpusDoctorService(corpus).run(deep=True)
    assert not report.ok
    assert any(
        "missing source" in f.message.lower() or f.code.endswith("project_invalid")
        for f in report.findings
    ), report.findings


def test_reordered_pages_preserve_identity(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("ord")
    # Two pages in one notebook
    items: list[ImportPlanItem] = []
    for i, color in enumerate(((1, 2, 3), (4, 5, 6))):
        path = tmp_path / f"p{i}.png"
        data = _png_bytes(color=color)
        path.write_bytes(data)
        items.append(
            ImportPlanItem(
                item_id=f"ord-{i}",
                op="create_notebook" if i == 0 else "import_into_notebook",
                notebook_id="nb-ord",
                source_sha256=sha256_bytes(data),
                media_type="image/png",
                page_indexes=[0],
                source_id=f"src-ord-{i}",
                page_ids=[f"page-ord-{i}"],
                render_ids=[f"render-ord-{i}"],
                provenance={
                    "source_path": str(path),
                    "title": "Ordered",
                    "managed_relpath": "nb-ord",
                },
                original_filename=path.name,
            )
        )
    orch = ImportOrchestrator(corpus, clock=clock, ids=ids)
    run = orch.create_run_from_plan(
        ImportPlan(
            plan_id="plan-ord",
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            items=items,
        )
    )
    assert orch.commit_run(run.import_run_id).status == "complete"

    paths = open_project_paths(corpus.projects_dir / "nb-ord")
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.load(reconcile=False)
    before_ids = [p.page_id for p in project.pages]
    assert before_ids == ["page-ord-0", "page-ord-1"]

    # Permute list order only — never change page_id
    project.pages = list(reversed(project.pages))
    write_json_atomic(paths.manifest, project.as_dict())

    reloaded = projects.load(reconcile=False)
    assert [p.page_id for p in reloaded.pages] == ["page-ord-1", "page-ord-0"]
    assert {s.source_id for s in reloaded.sources} == {"src-ord-0", "src-ord-1"}
    doctor = CorpusDoctorService(corpus).run(deep=True)
    assert doctor.ok, doctor.findings


def test_failed_ocr_does_not_lose_import_identity(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("ocr")
    items: list[ImportPlanItem] = []
    for i in range(2):
        path = tmp_path / f"ocr{i}.png"
        data = _png_bytes(color=(i + 1, 10, 20))
        path.write_bytes(data)
        items.append(
            ImportPlanItem(
                item_id=f"ocr-item-{i}",
                op="create_notebook" if i == 0 else "import_into_notebook",
                notebook_id="nb-ocr",
                source_sha256=sha256_bytes(data),
                media_type="image/png",
                page_indexes=[0],
                source_id=f"src-ocr-{i}",
                page_ids=[f"page-ocr-{i}"],
                render_ids=[f"render-ocr-{i}"],
                provenance={
                    "source_path": str(path),
                    "title": "OCR",
                    "managed_relpath": "nb-ocr",
                },
                original_filename=path.name,
            )
        )
    orch = ImportOrchestrator(corpus, clock=clock, ids=ids)
    run = orch.create_run_from_plan(
        ImportPlan(
            plan_id="plan-ocr",
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            items=items,
        )
    )
    completed = orch.commit_run(run.import_run_id)
    assert completed.status == "complete"
    assert all(item.state == "committed" for item in completed.items)

    paths = open_project_paths(corpus.projects_dir / "nb-ocr")
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.load(reconcile=False)
    settings = project.settings
    settings.model_name = "fake-vision"
    settings.max_workers = 1
    projects.save_settings(project, settings)

    provider = FakeVisionOCRProvider(fail_times=1)
    progress = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids
    ).run_blocking()
    assert progress.failed == 1
    assert progress.completed == 1

    # Import identity intact; doctor green despite OCR failure on one page
    reloaded = projects.load(reconcile=False)
    assert {p.page_id for p in reloaded.pages} == {"page-ocr-0", "page-ocr-1"}
    assert {s.source_id for s in reloaded.sources} == {"src-ocr-0", "src-ocr-1"}
    statuses = []
    for page in reloaded.pages:
        result = projects.load_page_result(page.page_id)
        assert result is not None
        attempt = result.active_attempt()
        assert attempt is not None
        statuses.append(attempt.status)
    assert statuses.count("failed") == 1
    assert statuses.count("succeeded") == 1
    doctor = CorpusDoctorService(corpus).run(deep=True)
    assert doctor.ok, doctor.findings


def test_reimport_skip_and_create_duplicate(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("re")
    data = _png_bytes(color=(7, 7, 7))
    path = tmp_path / "same.png"
    path.write_bytes(data)

    def _item(
        *,
        item_id: str,
        source_id: str,
        page_id: str,
        render_id: str,
        op: str = "create_notebook",
        notebook_id: str = "nb-re",
    ) -> ImportPlanItem:
        return ImportPlanItem(
            item_id=item_id,
            op=op,
            notebook_id=notebook_id,
            source_sha256=sha256_bytes(data),
            media_type="image/png",
            page_indexes=[0],
            source_id=source_id,
            page_ids=[page_id],
            render_ids=[render_id],
            provenance={
                "source_path": str(path),
                "title": "Reimport",
                "managed_relpath": "nb-re",
            },
            original_filename=path.name,
        )

    orch = ImportOrchestrator(corpus, clock=clock, ids=ids)
    first = orch.create_run_from_plan(
        ImportPlan(
            plan_id="plan-re-1",
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            items=[
                _item(
                    item_id="re-1",
                    source_id="src-re-1",
                    page_id="page-re-1",
                    render_id="render-re-1",
                )
            ],
        )
    )
    assert orch.commit_run(first.import_run_id).status == "complete"

    # Same bytes under skip_existing → skipped; planned skip IDs not written
    skip_run = orch.create_run_from_plan(
        ImportPlan(
            plan_id="plan-re-skip",
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            items=[
                _item(
                    item_id="re-skip",
                    source_id="src-re-skip",
                    page_id="page-re-skip",
                    render_id="render-re-skip",
                    op="import_into_notebook",
                    notebook_id="nb-re",
                )
            ],
        )
    )
    skipped = orch.commit_run(skip_run.import_run_id)
    assert skipped.items[0].state == "skipped"

    dup_run = orch.create_run_from_plan(
        ImportPlan(
            plan_id="plan-re-dup",
            import_policy_id=POLICY_CREATE_DUPLICATE_V1,
            items=[
                _item(
                    item_id="re-dup",
                    source_id="src-re-dup",
                    page_id="page-re-dup",
                    render_id="render-re-dup",
                    op="import_into_notebook",
                    notebook_id="nb-re",
                )
            ],
        )
    )
    duplicated = orch.commit_run(dup_run.import_run_id)
    assert duplicated.items[0].state == "committed"

    project = ProjectService(
        open_project_paths(corpus.projects_dir / "nb-re"),
        clock=clock,
        ids=ids,
    ).load(reconcile=False)
    assert {s.source_id for s in project.sources} >= {"src-re-1", "src-re-dup"}
    assert {p.page_id for p in project.pages} >= {"page-re-1", "page-re-dup"}
    assert "src-re-skip" not in {s.source_id for s in project.sources}
    assert CorpusDoctorService(corpus).run(deep=True).ok


def test_legacy_v1_notebook_without_import_run_linkage(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("leg")
    paths = open_project_paths(corpus.projects_dir / "legacy-nb")
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("Legacy")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = ingest.import_bytes("legacy.png", _png_bytes(color=(1, 1, 1)))
    # Simulate pre-corpus source: strip optional linkage fields if present
    for source in project.sources:
        source.import_run_id = None
        source.original_path = None
        source.source_size_bytes = None
    write_json_atomic(paths.manifest, project.as_dict())
    CorpusIndexStore(corpus, clock=clock).register_notebook(
        notebook_id=project.id,
        managed_relpath="legacy-nb",
        project_id=project.id,
    )

    doctor = CorpusDoctorService(corpus).run(deep=True)
    assert doctor.ok, doctor.findings

    # Bulk import alongside legacy notebook does not invent new IDs for it
    data = _png_bytes(color=(2, 2, 2))
    path = tmp_path / "new.png"
    path.write_bytes(data)
    orch = ImportOrchestrator(corpus, clock=clock, ids=ids)
    run = orch.create_run_from_plan(
        ImportPlan(
            plan_id="plan-leg-new",
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            items=[
                ImportPlanItem(
                    item_id="leg-new",
                    op="create_notebook",
                    notebook_id="nb-beside-legacy",
                    source_sha256=sha256_bytes(data),
                    media_type="image/png",
                    page_indexes=[0],
                    source_id="src-beside",
                    page_ids=["page-beside"],
                    render_ids=["render-beside"],
                    provenance={
                        "source_path": str(path),
                        "title": "Beside",
                        "managed_relpath": "beside-legacy",
                    },
                    original_filename="new.png",
                )
            ],
        )
    )
    completed = orch.commit_run(run.import_run_id)
    assert completed.status == "complete"

    legacy = projects.load(reconcile=False)
    assert legacy.id == project.id
    assert all(s.import_run_id is None for s in legacy.sources)
    assert CorpusDoctorService(corpus).run(deep=True).ok
