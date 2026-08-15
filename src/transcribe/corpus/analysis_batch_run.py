"""AnalysisBatchRun persistence — sequential multi-notebook Analyse."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import CorpusError, ValidationError
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import mutation_lock
from transcribe.persistence.schema import require_format

TERMINAL_STATUSES = frozenset({"completed", "partial", "failed", "cancelled"})
ITEM_STATES = frozenset(
    {"pending", "running", "completed", "skipped", "failed", "cancelled"}
)
LIVE_STATUSES = frozenset({"pending", "running"})


@dataclass
class AnalysisBatchItem:
    notebook_id: str
    title: str = ""
    managed_relpath: str = ""
    state: str = "pending"
    modules_total: int = 0
    modules_completed: int = 0
    modules_failed: int = 0
    modules_skipped: int = 0
    error_message: str | None = None
    inner_run_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "notebook_id": self.notebook_id,
            "title": self.title,
            "managed_relpath": self.managed_relpath,
            "state": self.state,
            "modules_total": self.modules_total,
            "modules_completed": self.modules_completed,
            "modules_failed": self.modules_failed,
            "modules_skipped": self.modules_skipped,
        }
        if self.error_message is not None:
            payload["error_message"] = self.error_message
        if self.inner_run_id is not None:
            payload["inner_run_id"] = self.inner_run_id
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalysisBatchItem:
        inner = data.get("inner_run_id")
        return cls(
            notebook_id=str(data["notebook_id"]),
            title=str(data.get("title") or ""),
            managed_relpath=str(data.get("managed_relpath") or ""),
            state=str(data.get("state") or "pending"),
            modules_total=int(data.get("modules_total") or 0),
            modules_completed=int(data.get("modules_completed") or 0),
            modules_failed=int(data.get("modules_failed") or 0),
            modules_skipped=int(data.get("modules_skipped") or 0),
            error_message=data.get("error_message"),
            inner_run_id=str(inner) if inner else None,
        )


@dataclass
class AnalysisBatchRun:
    analysis_batch_id: str
    created_at: str
    updated_at: str
    status: str
    module_ids: list[str] = field(default_factory=list)
    question_text: str | None = None
    effective_config: dict[str, Any] = field(default_factory=dict)
    config_fingerprint: str = ""
    text_model: dict[str, Any] | None = None
    plan_template_hash: str = ""
    preset_label: str | None = None
    preset_key: str | None = None
    preset_content_version: int | None = None
    preset_policy_fingerprint: str | None = None
    import_run_id: str | None = None
    items: list[AnalysisBatchItem] = field(default_factory=list)
    format: str = "transcribe.analysis-batch-run"
    schema_version: int = 1
    detector_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "format": self.format,
            "schema_version": self.schema_version,
            "analysis_batch_id": self.analysis_batch_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "module_ids": list(self.module_ids),
            "detector_ids": list(self.detector_ids),
            "effective_config": dict(self.effective_config),
            "config_fingerprint": self.config_fingerprint,
            "plan_template_hash": self.plan_template_hash,
            "items": [i.as_dict() for i in self.items],
        }
        if self.question_text is not None:
            payload["question_text"] = self.question_text
        if self.text_model is not None:
            payload["text_model"] = dict(self.text_model)
        if self.preset_label is not None:
            payload["preset_label"] = self.preset_label
        if self.preset_key is not None:
            payload["preset_key"] = self.preset_key
        if self.preset_content_version is not None:
            payload["preset_content_version"] = self.preset_content_version
        if self.preset_policy_fingerprint is not None:
            payload["preset_policy_fingerprint"] = self.preset_policy_fingerprint
        if self.import_run_id is not None:
            payload["import_run_id"] = self.import_run_id
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalysisBatchRun:
        require_format(data, "transcribe.analysis-batch-run")
        version_raw = data.get("preset_content_version")
        content_version: int | None
        if version_raw is None:
            content_version = None
        else:
            try:
                content_version = int(version_raw)
            except (TypeError, ValueError):
                content_version = None
        text_raw = data.get("text_model")
        return cls(
            analysis_batch_id=str(data["analysis_batch_id"]),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            status=str(data.get("status") or "pending"),
            module_ids=[str(m) for m in (data.get("module_ids") or [])],
            question_text=(
                str(data["question_text"])
                if data.get("question_text") is not None
                else None
            ),
            effective_config=dict(data.get("effective_config") or {}),
            config_fingerprint=str(data.get("config_fingerprint") or ""),
            text_model=dict(text_raw) if isinstance(text_raw, dict) else None,
            plan_template_hash=str(data.get("plan_template_hash") or ""),
            preset_label=(
                str(data["preset_label"]) if data.get("preset_label") is not None else None
            ),
            preset_key=(
                str(data["preset_key"]) if data.get("preset_key") is not None else None
            ),
            preset_content_version=content_version,
            preset_policy_fingerprint=(
                str(data["preset_policy_fingerprint"])
                if data.get("preset_policy_fingerprint") is not None
                else None
            ),
            import_run_id=data.get("import_run_id"),
            items=[AnalysisBatchItem.from_dict(i) for i in data.get("items") or []],
            format=str(data.get("format", "transcribe.analysis-batch-run")),
            schema_version=int(data.get("schema_version", 1)),
            detector_ids=[str(d) for d in (data.get("detector_ids") or [])],
        )


def validate_analysis_batch_run(run: AnalysisBatchRun) -> None:
    if run.status not in TERMINAL_STATUSES and run.status not in LIVE_STATUSES:
        raise ValidationError(f"invalid analysis-batch-run status: {run.status!r}")
    if not run.analysis_batch_id.strip():
        raise ValidationError("analysis_batch_id must be non-empty")
    if not run.module_ids and not run.detector_ids:
        raise ValidationError(
            "analysis-batch-run requires at least one module_id or detector_id"
        )
    seen: set[str] = set()
    for item in run.items:
        if item.state not in ITEM_STATES:
            raise ValidationError(
                f"invalid analysis-batch-run item state: {item.state!r}"
            )
        nid = item.notebook_id.strip()
        if not nid:
            raise ValidationError(
                "analysis-batch-run item notebook_id must be non-empty"
            )
        if nid in seen:
            raise ValidationError(
                f"duplicate notebook_id in analysis-batch-run: {nid}"
            )
        seen.add(nid)


def finalize_analysis_batch_status(run: AnalysisBatchRun) -> str:
    """Derive terminal status from item states after a stop or finish."""
    states = {i.state for i in run.items}
    if "running" in states or "pending" in states:
        if "cancelled" in states:
            return "cancelled" if not (states & {"completed", "skipped"}) else "partial"
        return "running"
    if states <= {"completed", "skipped"}:
        return "completed"
    if states <= {"failed"}:
        return "failed"
    if "cancelled" in states and not (states & {"completed", "skipped", "failed"}):
        return "cancelled"
    if "cancelled" in states or "failed" in states:
        return "partial"
    return "completed"


class AnalysisBatchRunStore:
    def __init__(self, paths: CorpusPaths) -> None:
        self.paths = paths

    def load(self, analysis_batch_id: str) -> AnalysisBatchRun:
        path = self.paths.analysis_batch_run_path(analysis_batch_id)
        if not path.exists():
            raise CorpusError(f"analysis batch run not found: {analysis_batch_id}")
        try:
            run = AnalysisBatchRun.from_dict(read_json(path))
            validate_analysis_batch_run(run)
            return run
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
            raise CorpusError(
                f"failed to load analysis batch run {analysis_batch_id}: {exc}"
            ) from exc

    def save(self, run: AnalysisBatchRun) -> None:
        validate_analysis_batch_run(run)
        self.paths.ensure_layout()
        path = self.paths.analysis_batch_run_path(run.analysis_batch_id)
        with mutation_lock(self.paths.lock_path):
            write_json_atomic(path, run.as_dict())

    def list_runs(self) -> list[AnalysisBatchRun]:
        if not self.paths.analysis_batch_runs_dir.is_dir():
            return []
        runs: list[AnalysisBatchRun] = []
        for path in sorted(
            self.paths.analysis_batch_runs_dir.glob("*.json"), reverse=True
        ):
            try:
                runs.append(self.load(path.stem))
            except CorpusError:
                continue
        return runs
