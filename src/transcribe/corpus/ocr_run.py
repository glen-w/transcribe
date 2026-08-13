"""OcrBatchRun persistence — sequential multi-notebook OCR (lighter than ImportRun)."""

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
class OcrBatchItem:
    notebook_id: str
    title: str = ""
    managed_relpath: str = ""
    state: str = "pending"
    pages_total: int = 0
    pages_completed: int = 0
    pages_failed: int = 0
    pages_skipped: int = 0
    error_message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "notebook_id": self.notebook_id,
            "title": self.title,
            "managed_relpath": self.managed_relpath,
            "state": self.state,
            "pages_total": self.pages_total,
            "pages_completed": self.pages_completed,
            "pages_failed": self.pages_failed,
            "pages_skipped": self.pages_skipped,
        }
        if self.error_message is not None:
            payload["error_message"] = self.error_message
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OcrBatchItem:
        return cls(
            notebook_id=str(data["notebook_id"]),
            title=str(data.get("title") or ""),
            managed_relpath=str(data.get("managed_relpath") or ""),
            state=str(data.get("state") or "pending"),
            pages_total=int(data.get("pages_total") or 0),
            pages_completed=int(data.get("pages_completed") or 0),
            pages_failed=int(data.get("pages_failed") or 0),
            pages_skipped=int(data.get("pages_skipped") or 0),
            error_message=data.get("error_message"),
        )


@dataclass
class OcrBatchRun:
    ocr_run_id: str
    created_at: str
    updated_at: str
    status: str
    force: bool = False
    settings: dict[str, Any] = field(default_factory=dict)
    settings_fingerprint: str = ""
    import_run_id: str | None = None
    items: list[OcrBatchItem] = field(default_factory=list)
    format: str = "transcribe.ocr-batch-run"
    schema_version: int = 1

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "format": self.format,
            "schema_version": self.schema_version,
            "ocr_run_id": self.ocr_run_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "force": self.force,
            "settings": dict(self.settings),
            "settings_fingerprint": self.settings_fingerprint,
            "items": [i.as_dict() for i in self.items],
        }
        if self.import_run_id is not None:
            payload["import_run_id"] = self.import_run_id
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OcrBatchRun:
        require_format(data, "transcribe.ocr-batch-run")
        return cls(
            ocr_run_id=str(data["ocr_run_id"]),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            status=str(data.get("status") or "pending"),
            force=bool(data.get("force", False)),
            settings=dict(data.get("settings") or {}),
            settings_fingerprint=str(data.get("settings_fingerprint") or ""),
            import_run_id=data.get("import_run_id"),
            items=[OcrBatchItem.from_dict(i) for i in data.get("items") or []],
            format=str(data.get("format", "transcribe.ocr-batch-run")),
            schema_version=int(data.get("schema_version", 1)),
        )


def validate_ocr_batch_run(run: OcrBatchRun) -> None:
    if run.status not in TERMINAL_STATUSES and run.status not in LIVE_STATUSES:
        raise ValidationError(f"invalid ocr-batch-run status: {run.status!r}")
    if not run.ocr_run_id.strip():
        raise ValidationError("ocr_run_id must be non-empty")
    seen: set[str] = set()
    for item in run.items:
        if item.state not in ITEM_STATES:
            raise ValidationError(f"invalid ocr-batch-run item state: {item.state!r}")
        nid = item.notebook_id.strip()
        if not nid:
            raise ValidationError("ocr-batch-run item notebook_id must be non-empty")
        if nid in seen:
            raise ValidationError(f"duplicate notebook_id in ocr-batch-run: {nid}")
        seen.add(nid)


def finalize_ocr_batch_status(run: OcrBatchRun) -> str:
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


class OcrBatchRunStore:
    def __init__(self, paths: CorpusPaths) -> None:
        self.paths = paths

    def load(self, ocr_run_id: str) -> OcrBatchRun:
        path = self.paths.ocr_run_path(ocr_run_id)
        if not path.exists():
            raise CorpusError(f"ocr batch run not found: {ocr_run_id}")
        try:
            run = OcrBatchRun.from_dict(read_json(path))
            validate_ocr_batch_run(run)
            return run
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
            raise CorpusError(f"failed to load ocr batch run {ocr_run_id}: {exc}") from exc

    def save(self, run: OcrBatchRun) -> None:
        validate_ocr_batch_run(run)
        self.paths.ensure_layout()
        path = self.paths.ocr_run_path(run.ocr_run_id)
        with mutation_lock(self.paths.lock_path):
            write_json_atomic(path, run.as_dict())

    def list_runs(self) -> list[OcrBatchRun]:
        if not self.paths.ocr_runs_dir.is_dir():
            return []
        runs: list[OcrBatchRun] = []
        for path in sorted(self.paths.ocr_runs_dir.glob("*.json"), reverse=True):
            try:
                runs.append(self.load(path.stem))
            except CorpusError:
                continue
        return runs
