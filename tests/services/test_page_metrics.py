"""Page metrics service: publish, cache identity, stale-on-render-change."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from transcribe.domain.fingerprint import sha256_bytes
from transcribe.ingest import IngestService
from transcribe.page_metrics import ALGORITHM_VERSION, PageMetricsService
from transcribe.page_metrics.storage import PageMetricsStorage
from transcribe.persistence.schema import require_format
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds


def _png_bytes(*, blank: bool = True, color=(20, 50, 180)) -> bytes:
    img = Image.new("RGB", (120, 160), (245, 240, 230))
    if not blank:
        draw = ImageDraw.Draw(img)
        for y in range(10, 150, 4):
            draw.line((8, y, 112, y), fill=color, width=3)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _project_with_pages(tmp_path: Path, n: int = 2, *, blank: bool = False):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("metrics-nb")
    ingest = IngestService(paths, clock=clock, ids=ids)
    project = None
    for i in range(n):
        project = ingest.import_bytes(f"p{i}.png", _png_bytes(blank=blank))
    assert project is not None
    return paths, projects, project, clock


def test_recompute_publishes_success(tmp_path: Path) -> None:
    paths, projects, project, clock = _project_with_pages(tmp_path, n=2, blank=False)
    svc = PageMetricsService(projects, clock=clock)
    doc = svc.recompute(project)
    assert doc.outcome == "success"
    assert doc.algorithm_version == ALGORITHM_VERSION
    assert doc.project_id == project.id
    assert len(doc.pages) == 2
    assert doc.rollup.page_count == 2
    assert doc.rollup.mean_ink_coverage_pct is not None
    assert doc.rollup.mean_ink_coverage_pct > 5.0
    assert sum(doc.rollup.hue_counts.values()) == 2

    raw = PageMetricsStorage(paths).read_published_raw()
    assert raw is not None
    require_format(raw, "transcribe.page-metrics")
    assert (paths.page_metrics_dir / "published.json").is_file()


def test_ensure_fresh_is_stable_until_render_changes(tmp_path: Path) -> None:
    paths, projects, project, clock = _project_with_pages(tmp_path, n=1, blank=False)
    svc = PageMetricsService(projects, clock=clock)
    first = svc.ensure_fresh(project)
    assert svc.is_fresh(project)
    second = svc.ensure_fresh(project)
    assert first.cache_identity == second.cache_identity
    assert first.computed_at == second.computed_at

    page = project.pages[0]
    render = project.renders[page.active_render_id]
    img_path = paths.resolve_contained(render.image_relpath)
    # Mutate pixels and SHA so identity changes.
    new_bytes = _png_bytes(blank=True)
    img_path.write_bytes(new_bytes)
    render.rendered_image_sha256 = sha256_bytes(new_bytes)
    # Persist mutated provenance via project rewrite helper path: save manifest.
    from transcribe.persistence.atomic import write_json_atomic
    from transcribe.persistence.locks import mutation_lock

    with mutation_lock(paths.mutation_lock):
        write_json_atomic(paths.manifest, project.as_dict())

    project = projects.load(reconcile=False)
    assert not svc.is_fresh(project)
    third = svc.ensure_fresh(project)
    assert third.cache_identity != first.cache_identity
    assert third.pages[0].ink_coverage_pct < first.pages[0].ink_coverage_pct


def test_empty_project_insufficient_data(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "empty")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("empty")
    svc = PageMetricsService(projects, clock=clock)
    doc = svc.recompute(project)
    assert doc.outcome == "insufficient_data"
    assert doc.pages == ()
    assert doc.rollup.page_count == 0
    assert doc.rollup.mean_ink_coverage_pct is None


def test_force_recompute_updates_timestamp(tmp_path: Path) -> None:
    _paths, projects, project, clock = _project_with_pages(tmp_path, n=1)
    svc = PageMetricsService(projects, clock=clock)
    a = svc.ensure_fresh(project)
    b = svc.ensure_fresh(project, force=True)
    assert a.cache_identity == b.cache_identity
    assert a.computed_at != b.computed_at
