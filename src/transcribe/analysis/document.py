"""AnalysisDocument validation and content fingerprint (contract schema v1)."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any

from transcribe.domain.fingerprint import canonical_json_bytes
from transcribe.persistence.schema import require_format

SPLIT_PAGE = "page"
SPLIT_PARAGRAPH_V1 = "paragraph_v1"
GRANULARITY_PAGE_V1 = "page_v1"
GRANULARITY_PARAGRAPH_V1 = "paragraph_v1"
CONTENT_FINGERPRINT_VERSION = 1
SUPPORTED_SPLIT_PROFILES = frozenset({SPLIT_PAGE, SPLIT_PARAGRAPH_V1})

_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


class AnalysisDocumentError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class AnalysisUnit:
    unit_id: str
    text: str
    order: float
    source_ref: dict[str, Any]
    date: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "text": self.text,
            "order": self.order,
            "date": self.date,
            "source_ref": dict(self.source_ref),
        }


@dataclass
class AnalysisDocument:
    document_id: str
    text: str
    units: list[AnalysisUnit] = field(default_factory=list)
    granularity_version: str = GRANULARITY_PAGE_V1
    split_profile: str = SPLIT_PAGE
    format: str = "transcribe.analysis-document"
    schema_version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "text": self.text,
            "granularity_version": self.granularity_version,
            "split_profile": self.split_profile,
            "units": [u.as_dict() for u in self.units],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalysisDocument:
        require_format(data, "transcribe.analysis-document")
        units = [
            AnalysisUnit(
                unit_id=str(u["unit_id"]),
                text=str(u["text"]),
                order=float(u["order"]),
                source_ref=dict(u["source_ref"]),
                date=u.get("date"),
            )
            for u in data.get("units") or []
        ]
        return cls(
            document_id=str(data["document_id"]),
            text=str(data["text"]),
            units=units,
            granularity_version=str(data.get("granularity_version", GRANULARITY_PAGE_V1)),
            split_profile=str(data.get("split_profile", SPLIT_PAGE)),
            format=str(data.get("format", "transcribe.analysis-document")),
            schema_version=int(data.get("schema_version", 1)),
        )


def _reject_surrogates(label: str, value: str) -> None:
    if _SURROGATE_RE.search(value):
        raise AnalysisDocumentError(
            "invalid_text", f"{label} contains unpaired surrogates"
        )


def concatenate_document_text(units: list[AnalysisUnit]) -> str:
    ordered = sorted(units, key=lambda u: (u.order, u.unit_id))
    return "\n".join(u.text for u in ordered)


def validate_analysis_document(doc: AnalysisDocument) -> AnalysisDocument:
    if doc.split_profile not in SUPPORTED_SPLIT_PROFILES:
        raise AnalysisDocumentError(
            "unsupported_split_profile",
            f"unsupported split_profile: {doc.split_profile!r}",
        )
    if not isinstance(doc.text, str):
        raise AnalysisDocumentError("invalid_text", "text must be a string")
    _reject_surrogates("text", doc.text)

    if not doc.units:
        raise AnalysisDocumentError("empty_document_text", "document has no units")
    if doc.text == "":
        raise AnalysisDocumentError("empty_document_text", "text is empty")

    seen: set[str] = set()
    for unit in doc.units:
        if not unit.unit_id:
            raise AnalysisDocumentError("missing_unit_id", "unit lacks unit_id")
        if unit.unit_id in seen:
            raise AnalysisDocumentError(
                "duplicate_unit_id", f"duplicate unit_id: {unit.unit_id}"
            )
        seen.add(unit.unit_id)
        if not isinstance(unit.text, str) or unit.text == "":
            raise AnalysisDocumentError("empty_unit_text", "unit text is empty")
        _reject_surrogates(f"unit {unit.unit_id}", unit.text)
        if not math.isfinite(unit.order) or unit.order < 0:
            raise AnalysisDocumentError("invalid_order", f"invalid order: {unit.order}")
        if unit.date is not None:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", unit.date):
                raise AnalysisDocumentError(
                    "invalid_date", f"invalid date: {unit.date!r}"
                )
        _validate_source_ref(unit.source_ref, unit_text=unit.text)

    sorted_units = sorted(doc.units, key=lambda u: (u.order, u.unit_id))
    if [u.unit_id for u in doc.units] != [u.unit_id for u in sorted_units]:
        raise AnalysisDocumentError(
            "units_not_sorted", "units not strictly sorted by (order, unit_id)"
        )

    expected = concatenate_document_text(doc.units)
    if doc.text != expected:
        raise AnalysisDocumentError("text_mismatch", "text ≠ concatenation rule")

    return doc


def _validate_source_ref(
    ref: dict[str, Any], *, unit_text: str | None = None
) -> None:
    kind = ref.get("kind")
    if kind == "page":
        if set(ref.keys()) - {"kind", "page_id"}:
            raise AnalysisDocumentError("invalid_source_ref", "extra keys in source_ref")
        if not isinstance(ref.get("page_id"), str) or not ref["page_id"]:
            raise AnalysisDocumentError("invalid_source_ref", "page_id required")
        return
    if kind == "page_span":
        required = {"kind", "page_id", "char_start", "char_end"}
        if set(ref.keys()) != required:
            raise AnalysisDocumentError("invalid_source_ref", "page_span shape invalid")
        if not isinstance(ref["page_id"], str) or not ref["page_id"]:
            raise AnalysisDocumentError("invalid_source_ref", "page_id required")
        start, end = ref["char_start"], ref["char_end"]
        if not isinstance(start, int) or not isinstance(end, int):
            raise AnalysisDocumentError("invalid_source_ref", "offsets must be int")
        if start < 0 or end < start:
            raise AnalysisDocumentError("invalid_source_ref", "invalid span offsets")
        # Without page text, require span length to match unit substring text.
        if unit_text is not None and (end - start) != len(unit_text):
            raise AnalysisDocumentError(
                "invalid_source_ref",
                "page_span length must equal unit text length",
            )
        return
    raise AnalysisDocumentError("invalid_source_ref", f"unknown kind: {kind!r}")


def content_fingerprint(doc: AnalysisDocument) -> str:
    validate_analysis_document(doc)
    payload: dict[str, Any] = {
        "content_fingerprint_version": CONTENT_FINGERPRINT_VERSION,
        "document_id": doc.document_id,
        "granularity_version": doc.granularity_version,
        "split_profile": doc.split_profile,
        "text": doc.text,
        "units": [
            {
                "date": unit.date,
                "order": unit.order,
                "source_ref": unit.source_ref,
                "text": unit.text,
                "unit_id": unit.unit_id,
            }
            for unit in doc.units
        ],
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def is_whitespace_only(text: str) -> bool:
    return len(text.strip()) == 0
