"""Workspace corpus doctor: cross-notebook uniqueness and index integrity."""

from __future__ import annotations

from dataclasses import dataclass, field

from transcribe.corpus.index import CorpusIndexStore, validate_entry_matches_project
from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import CorpusError, ProjectError, ValidationError
from transcribe.persistence.atomic import read_json
from transcribe.persistence.schema import require_format
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.services.doctor import DoctorFinding, DoctorReport, DoctorService
from transcribe.services.project import ProjectService, open_project_paths


@dataclass
class CorpusDoctorReport:
    ok: bool
    findings: list[DoctorFinding] = field(default_factory=list)
    notebook_reports: dict[str, DoctorReport] = field(default_factory=dict)

    def add(self, severity: str, code: str, message: str) -> None:
        self.findings.append(DoctorFinding(severity, code, message))
        if severity == "error":
            self.ok = False


class CorpusDoctorService:
    """Corpus-wide checks. Absent corpus index → informational skip (not activated)."""

    def __init__(self, paths: CorpusPaths) -> None:
        self.paths = paths
        self.store = CorpusIndexStore(paths, clock=SystemClock())

    def run(self, *, deep: bool = False, per_notebook: bool = True) -> CorpusDoctorReport:
        report = CorpusDoctorReport(ok=True)
        try:
            index = self.store.load()
        except CorpusError as exc:
            report.add("error", "corpus_index_load_failed", str(exc))
            return report

        if index is None:
            report.add(
                "warning",
                "corpus_index_absent",
                "no corpus-index.json; bulk-import generation not activated",
            )
            return report

        page_ids: dict[str, str] = {}
        source_ids: dict[str, str] = {}
        render_ids: dict[str, str] = {}

        for entry in index.entries:
            try:
                root = self.paths.resolve_managed(entry.managed_relpath)
            except ValueError as exc:
                report.add("error", "locator_escape", str(exc))
                continue
            manifest = root / "project.json"
            if not manifest.is_file():
                report.add(
                    "error",
                    "missing_project",
                    f"notebook {entry.notebook_id}: missing project.json at {entry.managed_relpath}",
                )
                continue
            try:
                payload = require_format(read_json(manifest), "transcribe.project")
                validate_entry_matches_project(
                    notebook_id=entry.notebook_id, project_id=str(payload["id"])
                )
            except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
                report.add(
                    "error",
                    "notebook_id_mismatch_or_invalid",
                    f"{entry.notebook_id}: {exc}",
                )
                continue

            if per_notebook:
                try:
                    project_paths = open_project_paths(root)
                    projects = ProjectService(
                        project_paths, clock=SystemClock(), ids=UuidGenerator()
                    )
                    nb_report = DoctorService(project_paths, projects).run(deep=deep)
                    report.notebook_reports[entry.notebook_id] = nb_report
                    if not nb_report.ok:
                        report.ok = False
                        for finding in nb_report.findings:
                            if finding.severity == "error":
                                report.add(
                                    "error",
                                    f"notebook:{finding.code}",
                                    f"{entry.notebook_id}: {finding.message}",
                                )
                except (ProjectError, OSError, ValueError) as exc:
                    report.add(
                        "error",
                        "notebook_doctor_failed",
                        f"{entry.notebook_id}: {exc}",
                    )

            # Collect IDs for global uniqueness
            try:
                for page in payload.get("pages") or []:
                    pid = str(page.get("page_id") or "")
                    if not pid:
                        continue
                    if pid in page_ids:
                        report.add(
                            "error",
                            "duplicate_page_id",
                            f"page_id {pid} in {entry.notebook_id} and {page_ids[pid]}",
                        )
                    else:
                        page_ids[pid] = entry.notebook_id
                for source in payload.get("sources") or []:
                    sid = str(source.get("source_id") or "")
                    if not sid:
                        continue
                    if sid in source_ids:
                        report.add(
                            "error",
                            "duplicate_source_id",
                            f"source_id {sid} in {entry.notebook_id} and {source_ids[sid]}",
                        )
                    else:
                        source_ids[sid] = entry.notebook_id
                for rid in (payload.get("renders") or {}).keys():
                    rid_s = str(rid)
                    if rid_s in render_ids:
                        report.add(
                            "error",
                            "duplicate_render_id",
                            f"render_id {rid_s} in {entry.notebook_id} and {render_ids[rid_s]}",
                        )
                    else:
                        render_ids[rid_s] = entry.notebook_id
            except (TypeError, AttributeError) as exc:
                report.add(
                    "error",
                    "id_scan_failed",
                    f"{entry.notebook_id}: {exc}",
                )

        # Quarantined corpus artifacts (documented warning — recovery may leave
        # audit trails; does not fail doctor.ok after a successful rebuild).
        if self.paths.quarantine_dir.exists():
            for path in sorted(self.paths.quarantine_dir.iterdir()):
                if path.is_file():
                    report.add(
                        "warning",
                        "corpus_quarantine_present",
                        f"quarantined artifact retained for review: {path.name}",
                    )

        return report
