"""ImportPlan dataclasses and validation (bulk-import generation)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from transcribe.corpus.import_run import compute_plan_fingerprint
from transcribe.errors import ValidationError

PLAN_SCHEMA_VERSION = 1
OP_CREATE_NOTEBOOK = "create_notebook"
OP_IMPORT_INTO_NOTEBOOK = "import_into_notebook"
IMPORT_OPS = frozenset({OP_CREATE_NOTEBOOK, OP_IMPORT_INTO_NOTEBOOK})
POLICY_SKIP_EXISTING_V1 = "skip_existing_v1"
POLICY_CREATE_DUPLICATE_V1 = "create_duplicate_v1"
IMPORT_POLICY_IDS = frozenset({POLICY_SKIP_EXISTING_V1, POLICY_CREATE_DUPLICATE_V1})


@dataclass
class ImportPlanItem:
    item_id: str
    op: str
    notebook_id: str
    source_sha256: str
    media_type: str
    page_indexes: list[int]
    source_id: str
    page_ids: list[str]
    render_ids: list[str]
    provenance: dict[str, Any] | None = None
    corpus_wide_dedupe: bool = False
    original_filename: str | None = None

    def as_dict(self, *, include_provenance: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "item_id": self.item_id,
            "op": self.op,
            "notebook_id": self.notebook_id,
            "source_sha256": self.source_sha256,
            "media_type": self.media_type,
            "page_indexes": list(self.page_indexes),
            "source_id": self.source_id,
            "page_ids": list(self.page_ids),
            "render_ids": list(self.render_ids),
            "corpus_wide_dedupe": bool(self.corpus_wide_dedupe),
        }
        if self.original_filename is not None:
            payload["original_filename"] = self.original_filename
        if include_provenance and self.provenance is not None:
            payload["provenance"] = dict(self.provenance)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImportPlanItem:
        return cls(
            item_id=str(data.get("item_id") or ""),
            op=str(data.get("op") or ""),
            notebook_id=str(data.get("notebook_id") or ""),
            source_sha256=str(data.get("source_sha256") or ""),
            media_type=str(data.get("media_type") or ""),
            page_indexes=[int(i) for i in data.get("page_indexes") or []],
            source_id=str(data.get("source_id") or ""),
            page_ids=[str(i) for i in data.get("page_ids") or []],
            render_ids=[str(i) for i in data.get("render_ids") or []],
            provenance=(
                dict(data["provenance"])
                if isinstance(data.get("provenance"), dict)
                else None
            ),
            corpus_wide_dedupe=bool(data.get("corpus_wide_dedupe", False)),
            original_filename=(
                str(data["original_filename"])
                if data.get("original_filename") is not None
                else None
            ),
        )


@dataclass
class ImportPlan:
    plan_id: str
    import_policy_id: str
    items: list[ImportPlanItem] = field(default_factory=list)
    schema_version: int = PLAN_SCHEMA_VERSION

    def as_dict(self, *, include_provenance: bool = True) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "import_policy_id": self.import_policy_id,
            "items": [
                item.as_dict(include_provenance=include_provenance)
                for item in self.items
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImportPlan:
        return cls(
            plan_id=str(data.get("plan_id") or ""),
            import_policy_id=str(data.get("import_policy_id") or ""),
            schema_version=int(data.get("schema_version", PLAN_SCHEMA_VERSION)),
            items=[
                ImportPlanItem.from_dict(item) for item in data.get("items") or []
            ],
        )

    def body_for_fingerprint(self) -> dict[str, Any]:
        return plan_body_for_fingerprint(self)

    def fingerprint(self) -> str:
        body = self.body_for_fingerprint()
        return compute_plan_fingerprint(
            schema_version=int(body["schema_version"]),
            plan_id=str(body["plan_id"]),
            import_policy_id=str(body["import_policy_id"]),
            items=list(body["items"]),
        )


def plan_body_for_fingerprint(plan: ImportPlan) -> dict[str, Any]:
    """Return the canonical plan body with provenance excluded."""
    return plan.as_dict(include_provenance=False)


def validate_import_plan(plan: ImportPlan) -> None:
    if plan.schema_version != PLAN_SCHEMA_VERSION:
        raise ValidationError(
            f"unsupported ImportPlan schema_version {plan.schema_version}"
        )
    _require_nonempty(plan.plan_id, "plan_id")
    if plan.import_policy_id not in IMPORT_POLICY_IDS:
        raise ValidationError(f"unknown import_policy_id: {plan.import_policy_id!r}")
    seen_items: set[str] = set()
    for item in plan.items:
        _validate_item(item)
        if item.item_id in seen_items:
            raise ValidationError(f"duplicate item_id in import plan: {item.item_id}")
        seen_items.add(item.item_id)


def _validate_item(item: ImportPlanItem) -> None:
    _require_nonempty(item.item_id, "item_id")
    _require_nonempty(item.notebook_id, f"{item.item_id}.notebook_id")
    _require_nonempty(item.source_sha256, f"{item.item_id}.source_sha256")
    _require_nonempty(item.media_type, f"{item.item_id}.media_type")
    if item.op not in IMPORT_OPS:
        raise ValidationError(f"unknown import op for {item.item_id}: {item.op!r}")
    if not item.page_indexes:
        raise ValidationError(f"{item.item_id}.page_indexes must be non-empty")
    if len(set(item.page_indexes)) != len(item.page_indexes):
        raise ValidationError(f"{item.item_id}.page_indexes contains duplicates")
    expected = list(range(len(item.page_indexes)))
    if item.page_indexes != expected:
        raise ValidationError(
            f"{item.item_id}.page_indexes must be contiguous {expected}"
        )
    _require_nonempty(item.source_id, f"{item.item_id}.source_id")
    if len(item.page_ids) != len(item.page_indexes):
        raise ValidationError(
            f"{item.item_id}.page_ids length must match page_indexes"
        )
    if len(item.render_ids) != len(item.page_indexes):
        raise ValidationError(
            f"{item.item_id}.render_ids length must match page_indexes"
        )
    for idx, page_id in enumerate(item.page_ids):
        _require_nonempty(page_id, f"{item.item_id}.page_ids[{idx}]")
    for idx, render_id in enumerate(item.render_ids):
        _require_nonempty(render_id, f"{item.item_id}.render_ids[{idx}]")


def _require_nonempty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty string")
