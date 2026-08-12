"""Workspace corpus doctor: cross-notebook uniqueness and index integrity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from transcribe.corpus.import_run import (
    ImportRun,
    ImportRunItemOutcome,
    ImportRunStore,
    validate_import_run,
)
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
                "no corpus-index.json; bulk import not used in this workspace yet",
            )
            return report

        page_ids: dict[str, str] = {}
        source_ids: dict[str, str] = {}
        render_ids: dict[str, str] = {}
        # notebook_id → project payload (for ImportRun committed-ID resolution)
        notebooks: dict[str, dict[str, Any]] = {}

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

            notebooks[entry.notebook_id] = payload

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

        self._check_import_runs(report, notebooks)

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

    def _check_import_runs(
        self,
        report: CorpusDoctorReport,
        notebooks: dict[str, dict[str, Any]],
    ) -> None:
        """Corpus invariant #6: committed ImportRun IDs resolve, or skip/fail with reason."""
        runs_dir = self.paths.import_runs_dir
        if not runs_dir.exists():
            return

        store = ImportRunStore(self.paths)
        for path in sorted(runs_dir.glob("*.json")):
            if not path.is_file():
                continue
            run_id = path.stem
            try:
                run = store.load(run_id)
            except CorpusError as exc:
                report.add(
                    "error",
                    "import_run_load_failed",
                    f"{path.name}: {exc}",
                )
                continue

            try:
                validate_import_run(run)
            except ValidationError as exc:
                report.add(
                    "error",
                    "import_run_invalid",
                    f"{run.import_run_id}: {exc}",
                )
                continue

            for item in run.items:
                self._check_import_run_item(report, run, item, notebooks)

    def _check_import_run_item(
        self,
        report: CorpusDoctorReport,
        run: ImportRun,
        item: ImportRunItemOutcome,
        notebooks: dict[str, dict[str, Any]],
    ) -> None:
        prefix = f"import-run {run.import_run_id} item {item.item_id}"
        state = item.state

        if state in ("skipped", "failed"):
            has_reason = bool(
                (state == "skipped" and item.skip_classification)
                or (state == "failed" and (item.error_code or item.error_message))
            )
            if not has_reason:
                report.add(
                    "error",
                    "import_run_outcome_missing_reason",
                    f"{prefix}: {state} without recorded reason",
                )
            return

        if state != "committed":
            return

        resulting = item.resulting_ids or {}
        notebook_id = str(resulting.get("notebook_id") or "").strip()
        if not notebook_id:
            report.add(
                "error",
                "import_run_committed_missing_notebook",
                f"{prefix}: committed item missing resulting notebook_id",
            )
            return

        payload = notebooks.get(notebook_id)
        if payload is None:
            report.add(
                "error",
                "import_run_committed_notebook_missing",
                f"{prefix}: committed notebook_id {notebook_id} not in corpus index",
            )
            return

        source_id = resulting.get("source_id")
        if source_id is not None:
            sid = str(source_id)
            known_sources = {
                str(s.get("source_id") or "") for s in (payload.get("sources") or [])
            }
            if sid not in known_sources:
                report.add(
                    "error",
                    "import_run_committed_source_missing",
                    f"{prefix}: source_id {sid} not in notebook {notebook_id}",
                )

        known_pages = {
            str(p.get("page_id") or "") for p in (payload.get("pages") or [])
        }
        for page_id in resulting.get("page_ids") or []:
            pid = str(page_id)
            if pid not in known_pages:
                report.add(
                    "error",
                    "import_run_committed_page_missing",
                    f"{prefix}: page_id {pid} not in notebook {notebook_id}",
                )

        known_renders = {str(rid) for rid in (payload.get("renders") or {}).keys()}
        for render_id in resulting.get("render_ids") or []:
            rid = str(render_id)
            if rid not in known_renders:
                report.add(
                    "error",
                    "import_run_committed_render_missing",
                    f"{prefix}: render_id {rid} not in notebook {notebook_id}",
                )
