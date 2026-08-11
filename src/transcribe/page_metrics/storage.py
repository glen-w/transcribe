"""Project-local page metrics publish/read."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from transcribe.page_metrics.models import PublishedPageMetrics
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.schema import SchemaError, require_format


class PageMetricsStorage:
    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    @property
    def root(self) -> Path:
        return self.paths.page_metrics_dir

    @property
    def published_path(self) -> Path:
        return self.root / "published.json"

    def read_published(self) -> PublishedPageMetrics | None:
        path = self.published_path
        if not path.exists():
            return None
        try:
            raw = require_format(read_json(path), "transcribe.page-metrics")
            return PublishedPageMetrics.from_dict(raw)
        except (SchemaError, OSError, ValueError, TypeError, KeyError):
            return None

    def read_published_raw(self) -> dict[str, Any] | None:
        path = self.published_path
        if not path.exists():
            return None
        try:
            return require_format(read_json(path), "transcribe.page-metrics")
        except (SchemaError, OSError, ValueError, TypeError):
            return None

    def write_published(self, doc: PublishedPageMetrics) -> Path:
        path = self.published_path
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, doc.to_dict())
        return path
