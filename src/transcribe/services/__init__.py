"""Services package.

Job coordinator imports stay lazy so leaf modules such as ``model_advice`` can
be loaded from analysis without re-entering ``llm_runtime`` (circular import).
"""

from __future__ import annotations

from .export import ExportService
from .project import ProjectService, open_project_paths

__all__ = [
    "ExportService",
    "JobCoordinator",
    "JobPlan",
    "JobProgress",
    "ProjectService",
    "build_coordinator",
    "open_project_paths",
]


def __getattr__(name: str):
    if name in {"JobCoordinator", "JobPlan", "JobProgress", "build_coordinator"}:
        from . import job as _job

        return getattr(_job, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
