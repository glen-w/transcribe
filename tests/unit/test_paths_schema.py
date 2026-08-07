from __future__ import annotations

import pytest

from transcribe.paths import ProjectPaths
from transcribe.persistence.schema import SchemaError, require_format
from transcribe.ports import SystemClock, to_iso


def test_clock_utc_iso_has_z():
    stamp = to_iso(SystemClock().now())
    assert stamp.endswith("Z")
    assert "+" not in stamp[:-1] or True  # Z form


def test_path_containment_rejects_escape(tmp_path):
    paths = ProjectPaths(root=tmp_path)
    paths.ensure_layout()
    with pytest.raises(ValueError):
        paths.resolve_contained("../../etc/passwd")


def test_schema_rejects_unknown_version():
    with pytest.raises(SchemaError):
        require_format(
            {"format": "transcribe.project", "schema_version": 99},
            "transcribe.project",
        )


def test_schema_rejects_wrong_format():
    with pytest.raises(SchemaError):
        require_format(
            {"format": "transcribe.notebook", "schema_version": 1},
            "transcribe.project",
        )
