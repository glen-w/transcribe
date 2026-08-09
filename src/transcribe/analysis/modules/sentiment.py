"""Sentiment — notebook adaptation; chronology via unit order/date (no speakers)."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules._tx_lexical_diversity import tokenize
from transcribe.domain.fingerprint import sha256_bytes

MODULE_ID = "sentiment"
MODULE_VERSION = "1.3.0"
PAYLOAD_SCHEMA = "sentiment_payload_v1"
ALGORITHM_VERSION = "sentiment_lexicon_v1"
LEXICON_ID = "sentiment_lexicon_v1"
BUCKET_THRESHOLD = 0.05

_LEXICON_PATH = Path(__file__).resolve().parents[1] / "data" / "sentiment_lexicon_v1.json"
_POS: dict[str, float] | None = None
_NEG: dict[str, float] | None = None
_DIGEST: str | None = None

TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


def _load_lexicon() -> tuple[dict[str, float], dict[str, float], str]:
    global _POS, _NEG, _DIGEST
    if _POS is not None and _NEG is not None and _DIGEST is not None:
        return _POS, _NEG, _DIGEST
    raw_bytes = _LEXICON_PATH.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    data = json.loads(raw_bytes.decode("utf-8"))
    pos = {str(k).casefold(): float(v) for k, v in (data.get("positive") or {}).items()}
    neg = {str(k).casefold(): float(v) for k, v in (data.get("negative") or {}).items()}
    _POS, _NEG, _DIGEST = pos, neg, digest
    return pos, neg, digest


def lexicon_digest() -> str:
    return _load_lexicon()[2]


def sentiment_config() -> dict[str, Any]:
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
        "lexicon_id": LEXICON_ID,
        "lexicon_digest": lexicon_digest(),
        "bucket_threshold": BUCKET_THRESHOLD,
    }


def sentiment_lexicon_or_model() -> dict[str, Any]:
    return {"lexicon_id": LEXICON_ID, "lexicon_digest": lexicon_digest()}


def score_sentiment(text: str) -> dict[str, float]:
    """Deterministic polarity scores shaped like VADER compound/pos/neu/neg."""
    pos_lex, neg_lex, _ = _load_lexicon()
    tokens = tokenize(text)
    if not tokens:
        return {"compound": 0.0, "pos": 0.0, "neu": 1.0, "neg": 0.0}
    pos_score = 0.0
    neg_score = 0.0
    for tok in tokens:
        if tok in pos_lex:
            pos_score += pos_lex[tok]
        if tok in neg_lex:
            neg_score += neg_lex[tok]
    # VADER-like normalization constant keeps compounds in (-1, 1).
    raw = pos_score - neg_score
    compound = raw / math.sqrt(raw * raw + 15.0) if raw != 0 else 0.0
    total = pos_score + neg_score
    if total <= 0:
        return {"compound": 0.0, "pos": 0.0, "neu": 1.0, "neg": 0.0}
    pos = pos_score / (total + 1.0)
    neg = neg_score / (total + 1.0)
    neu = max(0.0, 1.0 - pos - neg)
    return {
        "compound": float(compound),
        "pos": float(pos),
        "neu": float(neu),
        "neg": float(neg),
    }


def _bucket(compound: float) -> str:
    if compound >= BUCKET_THRESHOLD:
        return "positive"
    if compound <= -BUCKET_THRESHOLD:
        return "negative"
    return "neutral"


class SentimentModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    semantic_class = "adaptation"
    semantic_delta = (
        "speaker rollups removed; chronology via unit order/date; "
        "pinned sentiment_lexicon_v1 (offline VADER-shaped scores)"
    )
    ported_from_commit = TX_COMMIT

    def cache_config(self) -> dict[str, Any]:
        return sentiment_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = parents, llm_ctx, question_text
        if not document.units or not document.text.strip():
            return {
                "outcome": "insufficient_data",
                "payload": {},
                "warnings": [
                    {
                        "code": "empty_document",
                        "message": "No units / empty document text",
                    }
                ],
                "partial": False,
            }

        units_out: list[dict[str, Any]] = []
        compounds: list[float] = []
        pos_vals: list[float] = []
        neu_vals: list[float] = []
        neg_vals: list[float] = []
        distribution = {"positive": 0, "neutral": 0, "negative": 0}

        for unit in sorted(document.units, key=lambda u: u.order):
            scores = score_sentiment(unit.text)
            compounds.append(scores["compound"])
            pos_vals.append(scores["pos"])
            neu_vals.append(scores["neu"])
            neg_vals.append(scores["neg"])
            label = _bucket(scores["compound"])
            distribution[label] += 1
            units_out.append(
                {
                    "unit_id": unit.unit_id,
                    "order": unit.order,
                    "date": unit.date,
                    "compound": scores["compound"],
                    "pos": scores["pos"],
                    "neu": scores["neu"],
                    "neg": scores["neg"],
                    "label": label,
                }
            )

        n = len(units_out)
        payload = {
            "schema": PAYLOAD_SCHEMA,
            "algorithm_version": ALGORITHM_VERSION,
            "lexicon_id": LEXICON_ID,
            "lexicon_digest": lexicon_digest(),
            "global_stats": {
                "count": n,
                "compound_mean": sum(compounds) / n,
                "pos_mean": sum(pos_vals) / n,
                "neu_mean": sum(neu_vals) / n,
                "neg_mean": sum(neg_vals) / n,
                "sentiment_distribution": distribution,
            },
            "units": units_out,
        }
        return {"outcome": "success", "payload": payload, "warnings": [], "partial": False}


def provenance_files() -> list[dict[str, str]]:
    return [
        {
            "path": "src/transcriptx/core/analysis/sentiment/__init__.py",
            "sha256": "94070e07c0ac03844a370ab044a47849312b8e2c9c3b145cf8f48a3ab036272c",
        }
    ]


def code_digest() -> str:
    return sha256_bytes(Path(__file__).read_bytes())
