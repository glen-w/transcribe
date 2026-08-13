from __future__ import annotations

from pathlib import Path

from transcribe.persistence.atomic import (
    read_json,
    write_bytes_atomic,
    write_json_atomic,
)


def test_atomic_json_roundtrip(tmp_path: Path):
    path = tmp_path / "x.json"
    write_json_atomic(path, {"a": 1, "b": [True, None]})
    assert read_json(path) == {"a": 1, "b": [True, None]}
    mode = path.stat().st_mode & 0o777
    # best-effort 0600; may be masked by umask but should not be world-writable
    assert mode & 0o002 == 0


def test_atomic_bytes(tmp_path: Path):
    path = tmp_path / "bin" / "a.png"
    write_bytes_atomic(path, b"\x89PNG")
    assert path.read_bytes() == b"\x89PNG"


def test_strict_json_rejects_nan(tmp_path: Path):
    path = tmp_path / "bad.json"
    try:
        write_json_atomic(path, {"x": float("nan")})
        raised = False
    except ValueError:
        raised = True
    assert raised
