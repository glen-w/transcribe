"""Highlights — quote-forward spans; requires notebook_eligibility_v1."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules._tx_lexical_diversity import tokenize
from transcribe.analysis.modules.wordclouds import _load_stopwords
from transcribe.config.facade import require_operation_config
from transcribe.config.knobs import module_knob_dict

MODULE_ID = "highlights"
MODULE_VERSION = "1e.1.0"
PAYLOAD_SCHEMA = "highlights_payload_v1"
ALGORITHM_VERSION = "highlights_salience_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


def highlights_config() -> dict[str, Any]:
    from transcribe.analysis.modules.wordclouds import STOPWORDS_ID, stopwords_digest

    cfg = require_operation_config()
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
        **module_knob_dict(cfg, MODULE_ID),
        "stopwords_id": STOPWORDS_ID,
        "stopwords_digest": stopwords_digest(),
    }


def highlights_lexicon_or_model() -> dict[str, Any]:
    from transcribe.analysis.modules.wordclouds import STOPWORDS_ID, stopwords_digest

    return {
        "stopwords_id": STOPWORDS_ID,
        "stopwords_digest": stopwords_digest(),
    }


def provenance_files() -> list[dict[str, str]]:
    return []


def _score_unit(text: str, stop: set[str], position: int, n_units: int) -> float:
    toks = [t for t in tokenize(text) if t not in stop and len(t) > 2]
    uniq = len(set(toks))
    length_bonus = min(len(text) / 200.0, 1.5)
    pos_bonus = 1.0 - (position / max(n_units, 1)) * 0.25
    return uniq * 1.5 + length_bonus + pos_bonus


class HighlightsModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = "Notebook salience quotes over eligible paragraph/page units; no TX momentum"

    def cache_config(self) -> dict[str, Any]:
        return highlights_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = parents, llm_ctx, question_text
        top_n = require_operation_config().analysis.highlights.top_n
        if not document.units:
            return {"outcome": "insufficient_data", "payload": {}}
        stop, _ = _load_stopwords()
        n = len(document.units)
        ranked: list[tuple[float, Any]] = []
        for i, unit in enumerate(document.units):
            score = _score_unit(unit.text, stop, i, n)
            ranked.append((score, unit))
        ranked.sort(key=lambda row: (-row[0], row[1].unit_id))
        quotes = []
        evidence = []
        for score, unit in ranked[:top_n]:
            quote_id = f"q:{unit.unit_id}"
            quotes.append(
                {
                    "quote_id": quote_id,
                    "unit_id": unit.unit_id,
                    "text": unit.text.strip()[:500],
                    "score": round(score, 6),
                    "order": unit.order,
                    "date": unit.date,
                }
            )
            evidence.append(
                {
                    "unit_id": unit.unit_id,
                    "source_ref": dict(unit.source_ref),
                    "quote_id": quote_id,
                }
            )
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "quotes": quotes,
                "n_quotes": len(quotes),
            },
            "evidence": evidence,
        }
