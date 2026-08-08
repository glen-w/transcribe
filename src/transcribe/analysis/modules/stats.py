"""Notebook-native stats (adaptation of TX stats; speaker rollups removed)."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules._tx_lexical_diversity import tokenize
from transcribe.domain.fingerprint import sha256_bytes

MODULE_ID = "stats"
MODULE_VERSION = "1.1.0"
ALGORITHM_VERSION = "1"


class StatsModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    semantic_class = "adaptation"
    semantic_delta = "speaker rollups removed; unit/page distributions only"

    def run(self, document: AnalysisDocument) -> dict[str, Any]:
        if not document.units:
            return {
                "outcome": "insufficient_input",
                "payload": {},
                "warnings": [],
                "partial": False,
            }
        unit_rows = []
        total_chars = 0
        total_tokens = 0
        for unit in document.units:
            tokens = tokenize(unit.text)
            chars = len(unit.text)
            total_chars += chars
            total_tokens += len(tokens)
            unit_rows.append(
                {
                    "unit_id": unit.unit_id,
                    "order": unit.order,
                    "char_count": chars,
                    "token_count": len(tokens),
                    "line_count": unit.text.count("\n") + (1 if unit.text else 0),
                }
            )
        payload = {
            "algorithm_version": ALGORITHM_VERSION,
            "unit_count": len(document.units),
            "total_char_count": total_chars,
            "total_token_count": total_tokens,
            "document_char_count": len(document.text),
            "units": unit_rows,
        }
        return {"outcome": "success", "payload": payload, "warnings": [], "partial": False}


def provenance_files() -> list[dict[str, str]]:
    # Native adaptation — no TX file copy for stats core.
    return []


def code_digest() -> str:
    from pathlib import Path

    data = Path(__file__).read_bytes()
    return sha256_bytes(data)
