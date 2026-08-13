"""Page metrics domain shapes (in-memory + dict wire form)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PageMetricsRow:
    page_id: str
    render_id: str
    render_sha256: str
    ink_coverage_pct: float
    blankness_pct: float
    ink_hue: str
    ink_hue_degrees: float | None
    paper_tone: str
    width: int
    height: int
    pixel_count: int
    ink_pixel_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "render_id": self.render_id,
            "render_sha256": self.render_sha256,
            "ink_coverage_pct": self.ink_coverage_pct,
            "blankness_pct": self.blankness_pct,
            "ink_hue": self.ink_hue,
            "ink_hue_degrees": self.ink_hue_degrees,
            "paper_tone": self.paper_tone,
            "width": self.width,
            "height": self.height,
            "pixel_count": self.pixel_count,
            "ink_pixel_count": self.ink_pixel_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageMetricsRow:
        return cls(
            page_id=str(data["page_id"]),
            render_id=str(data["render_id"]),
            render_sha256=str(data["render_sha256"]),
            ink_coverage_pct=float(data["ink_coverage_pct"]),
            blankness_pct=float(data["blankness_pct"]),
            ink_hue=str(data["ink_hue"]),
            ink_hue_degrees=(
                None if data.get("ink_hue_degrees") is None else float(data["ink_hue_degrees"])
            ),
            paper_tone=str(data["paper_tone"]),
            width=int(data["width"]),
            height=int(data["height"]),
            pixel_count=int(data["pixel_count"]),
            ink_pixel_count=int(data["ink_pixel_count"]),
        )


@dataclass(frozen=True)
class PageMetricsRollup:
    page_count: int
    mean_ink_coverage_pct: float | None
    median_ink_coverage_pct: float | None
    mean_blankness_pct: float | None
    hue_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_count": self.page_count,
            "mean_ink_coverage_pct": self.mean_ink_coverage_pct,
            "median_ink_coverage_pct": self.median_ink_coverage_pct,
            "mean_blankness_pct": self.mean_blankness_pct,
            "hue_counts": dict(self.hue_counts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageMetricsRollup:
        raw_hues = data.get("hue_counts") or {}
        return cls(
            page_count=int(data.get("page_count") or 0),
            mean_ink_coverage_pct=(
                None
                if data.get("mean_ink_coverage_pct") is None
                else float(data["mean_ink_coverage_pct"])
            ),
            median_ink_coverage_pct=(
                None
                if data.get("median_ink_coverage_pct") is None
                else float(data["median_ink_coverage_pct"])
            ),
            mean_blankness_pct=(
                None
                if data.get("mean_blankness_pct") is None
                else float(data["mean_blankness_pct"])
            ),
            hue_counts={str(k): int(v) for k, v in dict(raw_hues).items()},
        )


@dataclass(frozen=True)
class PublishedPageMetrics:
    project_id: str
    algorithm_version: str
    cache_identity: str
    outcome: str
    computed_at: str
    rollup: PageMetricsRollup
    pages: tuple[PageMetricsRow, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "transcribe.page-metrics",
            "schema_version": 1,
            "project_id": self.project_id,
            "algorithm_version": self.algorithm_version,
            "cache_identity": self.cache_identity,
            "outcome": self.outcome,
            "computed_at": self.computed_at,
            "rollup": self.rollup.to_dict(),
            "pages": [p.to_dict() for p in self.pages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PublishedPageMetrics:
        rows = tuple(PageMetricsRow.from_dict(r) for r in (data.get("pages") or []))
        return cls(
            project_id=str(data["project_id"]),
            algorithm_version=str(data["algorithm_version"]),
            cache_identity=str(data["cache_identity"]),
            outcome=str(data["outcome"]),
            computed_at=str(data["computed_at"]),
            rollup=PageMetricsRollup.from_dict(data.get("rollup") or {}),
            pages=rows,
        )

    def row_for_page(self, page_id: str) -> PageMetricsRow | None:
        for row in self.pages:
            if row.page_id == page_id:
                return row
        return None
