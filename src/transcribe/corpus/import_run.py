"""ImportRun persistence helpers (bulk-import generation)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from transcribe.domain.fingerprint import canonical_json_bytes, sha256_bytes
from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import CorpusError, ValidationError
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import mutation_lock
from transcribe.persistence.schema import require_format

TERMINAL_STATUSES = frozenset(
    {
        "complete",
        "partial",
        "failed",
        "cancelled",
        "cancelled_with_commits",
    }
)
ITEM_STATES = frozenset(
    {"pending", "committed", "skipped", "failed", "cancelled_pending"}
)

# Fields included in plan_fingerprint input (paths/provenance excluded).
_PLAN_FINGERPRINT_ITEM_KEYS = (
    "item_id",
    "op",
    "notebook_id",
    "source_sha256",
    "media_type",
    "page_indexes",
    "source_id",
    "page_ids",
    "render_ids",
    "corpus_wide_dedupe",
    "original_filename",
)


def compute_plan_fingerprint(
    *,
    schema_version: int,
    plan_id: str,
    import_policy_id: str,
    items: list[dict[str, Any]],
) -> str:
    """SHA-256 of the canonical ImportPlan body (sorted keys; no external paths)."""
    canon_items: list[dict[str, Any]] = []
    for raw in items:
        item: dict[str, Any] = {}
        for key in _PLAN_FINGERPRINT_ITEM_KEYS:
            if key in raw:
                item[key] = raw[key]
        # Always include identity keys when present under alternate nesting
        if "resulting" in raw and isinstance(raw["resulting"], dict):
            resulting = raw["resulting"]
            for key in ("source_id", "page_ids", "render_ids", "notebook_id"):
                if key in resulting and key not in item:
                    item[key] = resulting[key]
        canon_items.append(item)
    body = {
        "schema_version": int(schema_version),
        "plan_id": plan_id,
        "import_policy_id": import_policy_id,
        "items": canon_items,
    }
    return sha256_bytes(canonical_json_bytes(body))


def plans_are_idempotent_retries(
    *,
    plan_id_a: str,
    fingerprint_a: str,
    policy_a: str,
    item_ids_a: set[str],
    plan_id_b: str,
    fingerprint_b: str,
    policy_b: str,
    item_ids_b: set[str],
) -> bool:
    """Exact equality rules for idempotent ImportRun retry."""
    return (
        plan_id_a == plan_id_b
        and fingerprint_a == fingerprint_b
        and policy_a == policy_b
        and item_ids_a == item_ids_b
    )


@dataclass
class ImportRunItemOutcome:
    item_id: str
    state: str
    resulting_ids: dict[str, Any] = field(default_factory=dict)
    skip_classification: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "item_id": self.item_id,
            "state": self.state,
            "resulting_ids": dict(self.resulting_ids),
        }
        if self.skip_classification is not None:
            payload["skip_classification"] = self.skip_classification
        if self.error_code is not None:
            payload["error_code"] = self.error_code
        if self.error_message is not None:
            payload["error_message"] = self.error_message
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImportRunItemOutcome:
        return cls(
            item_id=str(data["item_id"]),
            state=str(data["state"]),
            resulting_ids=dict(data.get("resulting_ids") or {}),
            skip_classification=data.get("skip_classification"),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
        )


@dataclass
class ImportRun:
    import_run_id: str
    plan_id: str
    plan_fingerprint: str
    import_policy_id: str
    created_at: str
    updated_at: str
    status: str
    plan_schema_version: int = 1
    items: list[ImportRunItemOutcome] = field(default_factory=list)
    format: str = "transcribe.import-run"
    schema_version: int = 1
    # Immutable plan body used for fingerprint (optional inline snapshot)
    plan_body: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "format": self.format,
            "schema_version": self.schema_version,
            "import_run_id": self.import_run_id,
            "plan_id": self.plan_id,
            "plan_fingerprint": self.plan_fingerprint,
            "import_policy_id": self.import_policy_id,
            "import_manifest": {"schema_version": self.plan_schema_version},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "items": [i.as_dict() for i in self.items],
        }
        if self.plan_body is not None:
            payload["plan_body"] = self.plan_body
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImportRun:
        require_format(data, "transcribe.import-run")
        manifest = data.get("import_manifest") or {}
        return cls(
            import_run_id=str(data["import_run_id"]),
            plan_id=str(data["plan_id"]),
            plan_fingerprint=str(data["plan_fingerprint"]),
            import_policy_id=str(data["import_policy_id"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            status=str(data["status"]),
            plan_schema_version=int(manifest.get("schema_version", 1)),
            items=[ImportRunItemOutcome.from_dict(i) for i in data.get("items") or []],
            format=str(data.get("format", "transcribe.import-run")),
            schema_version=int(data.get("schema_version", 1)),
            plan_body=data.get("plan_body"),
        )


def committed_notebook_ids(run: ImportRun) -> list[str]:
    """Unique notebook ids from committed ImportRun items, plan order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in run.items:
        if item.state != "committed":
            continue
        nid = str(item.resulting_ids.get("notebook_id") or "").strip()
        if not nid and run.plan_body:
            for planned in run.plan_body.get("items") or []:
                if str(planned.get("item_id") or "") == item.item_id:
                    nid = str(planned.get("notebook_id") or "").strip()
                    break
        if nid and nid not in seen:
            seen.add(nid)
            out.append(nid)
    return out


def validate_import_run(run: ImportRun) -> None:
    if run.status not in TERMINAL_STATUSES and run.status not in {
        "running",
        "pending",
    }:
        raise ValidationError(f"invalid import-run status: {run.status!r}")
    for item in run.items:
        if item.state not in ITEM_STATES:
            raise ValidationError(f"invalid import-run item state: {item.state!r}")


class ImportRunStore:
    def __init__(self, paths: CorpusPaths) -> None:
        self.paths = paths

    def load(self, import_run_id: str) -> ImportRun:
        path = self.paths.import_run_path(import_run_id)
        if not path.exists():
            raise CorpusError(f"import run not found: {import_run_id}")
        try:
            run = ImportRun.from_dict(read_json(path))
            validate_import_run(run)
            return run
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
            raise CorpusError(f"failed to load import run {import_run_id}: {exc}") from exc

    def save(self, run: ImportRun) -> None:
        validate_import_run(run)
        self.paths.ensure_layout()
        path = self.paths.import_run_path(run.import_run_id)
        with mutation_lock(self.paths.lock_path):
            write_json_atomic(path, run.as_dict())

    def list_runs(self) -> list[ImportRun]:
        if not self.paths.import_runs_dir.is_dir():
            return []
        runs: list[ImportRun] = []
        for path in sorted(self.paths.import_runs_dir.glob("*.json"), reverse=True):
            try:
                runs.append(self.load(path.stem))
            except CorpusError:
                continue
        return runs
