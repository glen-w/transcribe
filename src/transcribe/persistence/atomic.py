"""Crash-safe staged bytes/JSON persistence."""

from __future__ import annotations

import json
import math
import os
import stat
import tempfile
from pathlib import Path
from typing import Any


def _reject_non_strict_json(obj: Any, *, path: str = "$") -> None:
    if obj is None or isinstance(obj, (str, bool, int)):
        return
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError(f"non-finite float at {path}")
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(key, str):
                raise TypeError(
                    f"JSON object keys must be strings at {path}; got {type(key).__name__}"
                )
            _reject_non_strict_json(value, path=f"{path}.{key}")
        return
    if isinstance(obj, (list, tuple)):
        for idx, value in enumerate(obj):
            _reject_non_strict_json(value, path=f"{path}[{idx}]")
        return
    raise TypeError(f"unsupported JSON type at {path}: {type(obj).__name__}")


def strict_json_dumps(payload: Any, *, indent: int | None = 2) -> str:
    _reject_non_strict_json(payload)
    if indent is None:
        text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=indent, allow_nan=False)
    return text + "\n"


def _fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Sibling temp → flush → fsync → replace → best-effort directory fsync."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        try:
            os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp), str(path))
        _fsync_dir(path.parent)
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass


def write_json_atomic(path: Path, payload: Any, *, indent: int | None = 2) -> None:
    text = strict_json_dumps(payload, indent=indent)
    write_bytes_atomic(path, text.encode("utf-8"))


def read_json(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)
