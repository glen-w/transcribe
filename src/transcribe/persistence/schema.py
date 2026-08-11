"""Persisted format/schema recognition."""

from __future__ import annotations

from typing import Any

SUPPORTED: dict[str, int] = {
    "transcribe.project": 1,
    "transcribe.page-result": 1,
    "transcribe.notebook": 1,
    "transcribe.export-manifest": 1,
    "transcribe.export-bundle": 1,
    "transcribe.analysis-document": 1,
    "transcribe.analysis-result": 1,
    "transcribe.detection-result": 1,
    "transcribe.page-metrics": 1,
    # Bulk-import generation (prospective until activation gate)
    "transcribe.corpus-index": 1,
    "transcribe.import-run": 1,
    "transcribe.ingest-journal": 1,
}


class SchemaError(ValueError):
    pass


def require_format(payload: Any, expected_format: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SchemaError(f"expected object for {expected_format}")
    fmt = payload.get("format")
    version = payload.get("schema_version")
    if fmt != expected_format:
        raise SchemaError(f"expected format {expected_format!r}, got {fmt!r}")
    expected_version = SUPPORTED.get(expected_format)
    if expected_version is None:
        raise SchemaError(f"unsupported format: {expected_format!r}")
    if not isinstance(version, int):
        raise SchemaError(f"schema_version must be int for {expected_format}")
    if version != expected_version:
        raise SchemaError(
            f"unsupported schema_version {version} for {expected_format}; "
            f"this build supports {expected_version}"
        )
    return payload
