"""Append-only ingest ledger beside the notebook RAG index."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

STATUS_OK = "ok"
_STATUS_REMOVED = "removed"
NOTEBOOK_KEY = "notebook"


@dataclass
class LedgerRow:
    key: str
    status: str = STATUS_OK
    chunks: int = 0
    content_fingerprint: str = ""
    params: str = ""
    error: str = ""
    ts: float = 0.0


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self._rows: dict[str, LedgerRow] = {}
        if not path.is_file():
            return
        known = set(LedgerRow.__dataclass_fields__)
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if not isinstance(data, dict) or not data.get("key"):
                continue
            row = LedgerRow(**{k: v for k, v in data.items() if k in known})
            if row.status == _STATUS_REMOVED:
                self._rows.pop(row.key, None)
            else:
                self._rows[row.key] = row

    def get(self, key: str) -> LedgerRow | None:
        return self._rows.get(key)

    def write(self, row: LedgerRow) -> None:
        row.ts = time.time()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
        self._rows[row.key] = row


def needs_rebuild(
    row: LedgerRow | None,
    *,
    content_fingerprint: str,
    params: str,
    force: bool = False,
) -> bool:
    if force or row is None:
        return True
    if row.status != STATUS_OK or row.error:
        return True
    if row.params != params:
        return True
    if row.content_fingerprint != content_fingerprint:
        return True
    return False
