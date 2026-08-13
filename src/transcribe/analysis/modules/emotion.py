"""Emotion — offline lexicon path; chronology via unit order/date."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules._tx_lexical_diversity import tokenize
from transcribe.domain.fingerprint import sha256_bytes

MODULE_ID = "emotion"
MODULE_VERSION = "1d.0"
PAYLOAD_SCHEMA = "emotion_payload_v1"
ALGORITHM_VERSION = "emotion_lexicon_v1"
LEXICON_ID = "emotion_lexicon_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"

_LEXICON_PATH = Path(__file__).resolve().parents[1] / "data" / "emotion_lexicon_v1.json"
_WORDS: dict[str, dict[str, float]] | None = None
_LABELS: list[str] | None = None
_DIGEST: str | None = None


def _load_lexicon() -> tuple[dict[str, dict[str, float]], list[str], str]:
    global _WORDS, _LABELS, _DIGEST
    if _WORDS is not None and _LABELS is not None and _DIGEST is not None:
        return _WORDS, _LABELS, _DIGEST
    raw = _LEXICON_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw.decode("utf-8"))
    labels = [str(x) for x in (data.get("labels") or [])]
    words = {
        str(k).casefold(): {str(lk): float(lv) for lk, lv in (v or {}).items()}
        for k, v in (data.get("words") or {}).items()
    }
    _WORDS, _LABELS, _DIGEST = words, labels, digest
    return words, labels, digest


def lexicon_digest() -> str:
    return _load_lexicon()[2]


def emotion_config() -> dict[str, Any]:
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
        "lexicon_id": LEXICON_ID,
        "lexicon_digest": lexicon_digest(),
    }


def emotion_lexicon_or_model() -> dict[str, Any]:
    return {"lexicon_id": LEXICON_ID, "lexicon_digest": lexicon_digest()}


def score_emotion(text: str) -> dict[str, Any]:
    words, labels, _ = _load_lexicon()
    scores = {lab: 0.0 for lab in labels}
    tokens = tokenize(text)
    hits = 0
    for tok in tokens:
        entry = words.get(tok)
        if not entry:
            continue
        hits += 1
        for lab, weight in entry.items():
            if lab in scores:
                scores[lab] += weight
    total = sum(scores.values())
    if total > 0:
        dist = {lab: round(v / total, 6) for lab, v in scores.items()}
    else:
        dist = {lab: 0.0 for lab in labels}
    top = max(dist, key=dist.get) if labels and total > 0 else None
    intensity = round(min(1.0, total / max(1.0, 8.0)), 6)
    return {
        "scores": {k: round(v, 6) for k, v in scores.items()},
        "distribution": dist,
        "top_label": top,
        "intensity": intensity,
        "hit_count": hits,
    }


def provenance_files() -> list[dict[str, str]]:
    return []


def code_digest() -> str:
    return sha256_bytes(Path(__file__).read_bytes())


class EmotionModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = (
        "speaker assumptions removed; page-unit chronology; "
        "pinned emotion_lexicon_v1 offline path"
    )

    def cache_config(self) -> dict[str, Any]:
        return emotion_config()

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
            }

        _, labels, digest = _load_lexicon()
        units_out: list[dict[str, Any]] = []
        label_totals = {lab: 0.0 for lab in labels}
        intensities: list[float] = []
        for unit in sorted(document.units, key=lambda u: u.order):
            scored = score_emotion(unit.text)
            intensities.append(scored["intensity"])
            for lab, val in scored["scores"].items():
                label_totals[lab] = label_totals.get(lab, 0.0) + val
            units_out.append(
                {
                    "unit_id": unit.unit_id,
                    "order": unit.order,
                    "date": unit.date,
                    **scored,
                }
            )
        n = len(units_out)
        payload = {
            "schema": PAYLOAD_SCHEMA,
            "algorithm_version": ALGORITHM_VERSION,
            "lexicon_id": LEXICON_ID,
            "lexicon_digest": digest,
            "labels": labels,
            "global_stats": {
                "count": n,
                "intensity_mean": sum(intensities) / n if n else 0.0,
                "label_totals": {k: round(v, 6) for k, v in label_totals.items()},
            },
            "units": units_out,
        }
        return {
            "outcome": "success",
            "payload": payload,
            "warnings": [],
            "partial": False,
        }
