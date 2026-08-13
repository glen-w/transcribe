"""Compute and publish page ink / blankness / hue metrics."""

from __future__ import annotations

from collections import Counter
from typing import Sequence

from transcribe.domain.fingerprint import canonical_json_bytes, sha256_bytes
from transcribe.domain.models import Project
from transcribe.page_metrics.algorithm import ALGORITHM_VERSION, analyse_image_path
from transcribe.page_metrics.models import (
    PageMetricsRollup,
    PageMetricsRow,
    PublishedPageMetrics,
)
from transcribe.page_metrics.storage import PageMetricsStorage
from transcribe.paths import ProjectPaths
from transcribe.ports import Clock, to_iso
from transcribe.services.project import ProjectService


def cache_identity_payload(
    *,
    project_id: str,
    algorithm_version: str,
    page_render_pairs: Sequence[tuple[str, str]],
) -> dict:
    return {
        "algorithm_version": algorithm_version,
        "project_id": project_id,
        "pages": [{"page_id": pid, "render_sha256": sha} for pid, sha in page_render_pairs],
    }


def compute_cache_identity(
    *,
    project_id: str,
    algorithm_version: str,
    page_render_pairs: Sequence[tuple[str, str]],
) -> str:
    payload = cache_identity_payload(
        project_id=project_id,
        algorithm_version=algorithm_version,
        page_render_pairs=page_render_pairs,
    )
    return sha256_bytes(canonical_json_bytes(payload))


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return round(ordered[mid], 2)
    return round((ordered[mid - 1] + ordered[mid]) / 2.0, 2)


def build_rollup(rows: Sequence[PageMetricsRow]) -> PageMetricsRollup:
    if not rows:
        return PageMetricsRollup(
            page_count=0,
            mean_ink_coverage_pct=None,
            median_ink_coverage_pct=None,
            mean_blankness_pct=None,
            hue_counts={},
        )
    coverages = [r.ink_coverage_pct for r in rows]
    blanks = [r.blankness_pct for r in rows]
    hues = Counter(r.ink_hue for r in rows)
    return PageMetricsRollup(
        page_count=len(rows),
        mean_ink_coverage_pct=round(sum(coverages) / len(coverages), 2),
        median_ink_coverage_pct=_median(coverages),
        mean_blankness_pct=round(sum(blanks) / len(blanks), 2),
        hue_counts=dict(sorted(hues.items())),
    )


class PageMetricsService:
    def __init__(
        self,
        projects: ProjectService,
        *,
        clock: Clock,
    ) -> None:
        self.projects = projects
        self.paths: ProjectPaths = projects.paths
        self.clock = clock
        self.storage = PageMetricsStorage(self.paths)

    def _measurable_pairs(self, project: Project) -> list[tuple[str, str, str, object]]:
        """Return (page_id, render_id, render_sha256, image_path) for measurable pages."""
        out: list[tuple[str, str, str, object]] = []
        for page in project.pages:
            render = project.renders.get(page.active_render_id)
            if render is None:
                continue
            try:
                path = self.paths.resolve_contained(render.image_relpath)
            except ValueError:
                continue
            if not path.is_file():
                continue
            out.append(
                (
                    page.page_id,
                    page.active_render_id,
                    render.rendered_image_sha256,
                    path,
                )
            )
        return out

    def current_cache_identity(self, project: Project | None = None) -> str:
        project = project or self.projects.load(reconcile=False)
        pairs = self._measurable_pairs(project)
        return compute_cache_identity(
            project_id=project.id,
            algorithm_version=ALGORITHM_VERSION,
            page_render_pairs=[(p[0], p[2]) for p in pairs],
        )

    def read_published(self) -> PublishedPageMetrics | None:
        return self.storage.read_published()

    def is_fresh(self, project: Project | None = None) -> bool:
        project = project or self.projects.load(reconcile=False)
        published = self.storage.read_published()
        if published is None:
            return False
        if published.project_id != project.id:
            return False
        if published.algorithm_version != ALGORITHM_VERSION:
            return False
        return published.cache_identity == self.current_cache_identity(project)

    def ensure_fresh(
        self, project: Project | None = None, *, force: bool = False
    ) -> PublishedPageMetrics:
        project = project or self.projects.load(reconcile=False)
        if not force and self.is_fresh(project):
            published = self.storage.read_published()
            assert published is not None
            return published
        return self.recompute(project)

    def recompute(self, project: Project | None = None) -> PublishedPageMetrics:
        project = project or self.projects.load(reconcile=False)
        measurable = self._measurable_pairs(project)
        rows: list[PageMetricsRow] = []
        for page_id, render_id, render_sha, path in measurable:
            metrics = analyse_image_path(path)
            rows.append(
                PageMetricsRow(
                    page_id=page_id,
                    render_id=render_id,
                    render_sha256=render_sha,
                    ink_coverage_pct=metrics.ink_coverage_pct,
                    blankness_pct=metrics.blankness_pct,
                    ink_hue=metrics.ink_hue,
                    ink_hue_degrees=metrics.ink_hue_degrees,
                    paper_tone=metrics.paper_tone,
                    width=metrics.width,
                    height=metrics.height,
                    pixel_count=metrics.pixel_count,
                    ink_pixel_count=metrics.ink_pixel_count,
                )
            )
        identity = compute_cache_identity(
            project_id=project.id,
            algorithm_version=ALGORITHM_VERSION,
            page_render_pairs=[(r.page_id, r.render_sha256) for r in rows],
        )
        outcome = "success" if rows else "insufficient_data"
        computed_at = to_iso(self.clock.now())
        doc = PublishedPageMetrics(
            project_id=project.id,
            algorithm_version=ALGORITHM_VERSION,
            cache_identity=identity,
            outcome=outcome,
            computed_at=computed_at,
            rollup=build_rollup(rows),
            pages=tuple(rows),
        )
        self.storage.write_published(doc)
        return doc
