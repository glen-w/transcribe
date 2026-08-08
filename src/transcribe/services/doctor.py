"""Project integrity doctor: cheap structural checks and optional deep hashing."""

from __future__ import annotations

from dataclasses import dataclass, field

from transcribe.domain.validation import (
    collect_unexplained_files,
    validate_page_result,
    validate_project,
)
from transcribe.errors import ProjectError, ValidationError
from transcribe.paths import ProjectPaths
from transcribe.services.project import ProjectService


@dataclass
class DoctorFinding:
    severity: str  # error | warning
    code: str
    message: str


@dataclass
class DoctorReport:
    ok: bool
    findings: list[DoctorFinding] = field(default_factory=list)

    def add(self, severity: str, code: str, message: str) -> None:
        self.findings.append(DoctorFinding(severity, code, message))
        if severity == "error":
            self.ok = False


class DoctorService:
    def __init__(self, paths: ProjectPaths, projects: ProjectService) -> None:
        self.paths = paths
        self.projects = projects

    def run(self, *, deep: bool = False) -> DoctorReport:
        report = DoctorReport(ok=True)
        try:
            project = self.projects.load(reconcile=False)
        except (ProjectError, ValidationError, OSError, ValueError) as exc:
            report.add("error", "load_failed", str(exc))
            return report

        try:
            validate_project(project, paths=self.paths, deep=deep)
        except ValidationError as exc:
            report.add("error", "project_invalid", str(exc))

        if self.paths.ingest_journal.exists():
            report.add(
                "warning",
                "ingest_journal_present",
                "incomplete ingest journal present; open/cleanup will recover or roll back",
            )

        for page in project.pages:
            path = self.paths.result_path(page.page_id)
            if not path.exists():
                continue
            try:
                result = self.projects.load_page_result(page.page_id)
                if result is None:
                    continue
                validate_page_result(result, expected_page_id=page.page_id)
                if path.stem != page.page_id:
                    report.add(
                        "error",
                        "result_filename_mismatch",
                        f"result file {path.name} does not match page_id {page.page_id}",
                    )
            except (ValidationError, ProjectError, OSError, ValueError, KeyError) as exc:
                report.add(
                    "error",
                    "page_result_invalid",
                    f"{page.page_id}: {exc}",
                )

        # Orphan result files not referenced by any page
        page_ids = {p.page_id for p in project.pages}
        if self.paths.results_dir.exists():
            for path in self.paths.results_dir.glob("*.json"):
                if path.stem not in page_ids:
                    report.add(
                        "warning",
                        "orphan_result",
                        f"result file not referenced by project pages: {path.name}",
                    )

        for rel in collect_unexplained_files(self.paths, project):
            report.add(
                "warning",
                "unexplained_file",
                f"durable file not explained by manifest: {rel}",
            )

        return report
