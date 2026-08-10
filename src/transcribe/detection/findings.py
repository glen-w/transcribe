"""DetectionFinding model helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class DetectionFinding:
    finding_id: str
    detector_id: str
    detector_version: str
    notebook_id: str
    start_page_id: str
    end_page_id: str
    finding_type: str
    confidence: float
    evidence: dict[str, Any]
    prompt_provenance: dict[str, str]
    model_provenance: dict[str, Any]
    input_fingerprint: str
    created_at: str
    updated_at: str
    review_status: str = "unreviewed"
    detector_data: dict[str, Any] = field(default_factory=dict)
    start_boundary: dict[str, Any] | None = None
    end_boundary: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "finding_id": self.finding_id,
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "notebook_id": self.notebook_id,
            "start_page_id": self.start_page_id,
            "end_page_id": self.end_page_id,
            "finding_type": self.finding_type,
            "confidence": round(self.confidence, 6),
            "evidence": self.evidence,
            "prompt_provenance": self.prompt_provenance,
            "model_provenance": self.model_provenance,
            "input_fingerprint": self.input_fingerprint,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "review_status": self.review_status,
        }
        if self.detector_data:
            out["detector_data"] = self.detector_data
        if self.start_boundary is not None:
            out["start_boundary"] = self.start_boundary
        if self.end_boundary is not None:
            out["end_boundary"] = self.end_boundary
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DetectionFinding:
        return cls(
            finding_id=str(data["finding_id"]),
            detector_id=str(data["detector_id"]),
            detector_version=str(data["detector_version"]),
            notebook_id=str(data["notebook_id"]),
            start_page_id=str(data["start_page_id"]),
            end_page_id=str(data["end_page_id"]),
            finding_type=str(data["finding_type"]),
            confidence=float(data["confidence"]),
            evidence=dict(data.get("evidence") or {}),
            prompt_provenance=dict(data.get("prompt_provenance") or {}),
            model_provenance=dict(data.get("model_provenance") or {}),
            input_fingerprint=str(data["input_fingerprint"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            review_status=str(data.get("review_status") or "unreviewed"),
            detector_data=dict(data.get("detector_data") or {}),
            start_boundary=data.get("start_boundary"),
            end_boundary=data.get("end_boundary"),
        )


def findings_to_dicts(findings: list[DetectionFinding]) -> list[dict[str, Any]]:
    return [f.as_dict() for f in findings]
