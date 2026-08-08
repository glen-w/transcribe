"""Lexical diversity — TX util core + notebook-level wrap."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules._tx_lexical_diversity import (
    MIN_MTLD_TOKENS,
    build_metadata,
    compute_lexical_diversity_metrics,
)
from transcribe.domain.fingerprint import sha256_bytes

MODULE_ID = "lexical_diversity"
MODULE_VERSION = "1.1.0"
TX_PATH = "src/transcriptx/core/utils/lexical_diversity.py"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


class LexicalDiversityModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    semantic_class = "adaptation"
    semantic_delta = "speaker timelines removed; document + per-unit metrics"

    def run(self, document: AnalysisDocument) -> dict[str, Any]:
        doc_metrics = compute_lexical_diversity_metrics(document.text)
        token_count = int(doc_metrics["token_count"])
        if token_count < 1:
            return {
                "outcome": "insufficient_data",
                "payload": {"document": doc_metrics, "metadata": build_metadata()},
                "warnings": [],
                "partial": False,
            }
        warnings: list[dict[str, str]] = []
        partial = False
        payload_doc = dict(doc_metrics)
        if token_count < MIN_MTLD_TOKENS:
            payload_doc.pop("mtld", None)
            partial = True
            warnings.append(
                {
                    "code": "below_mtld_threshold",
                    "message": f"MTLD omitted when token_count < {MIN_MTLD_TOKENS}",
                }
            )
        per_unit = []
        for unit in document.units:
            m = compute_lexical_diversity_metrics(unit.text)
            if int(m["token_count"]) < MIN_MTLD_TOKENS:
                m = dict(m)
                m.pop("mtld", None)
            per_unit.append({"unit_id": unit.unit_id, "order": unit.order, **m})
        return {
            "outcome": "success",
            "payload": {
                "document": payload_doc,
                "units": per_unit,
                "metadata": build_metadata(),
            },
            "warnings": warnings,
            "partial": partial,
        }


def provenance_files() -> list[dict[str, str]]:
    path = Path(__file__).with_name("_tx_lexical_diversity.py")
    return [{"path": TX_PATH, "sha256": sha256_bytes(path.read_bytes())}]


def code_digest() -> str:
    return sha256_bytes(Path(__file__).read_bytes())
