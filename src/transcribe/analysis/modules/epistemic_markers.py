"""Epistemic markers — TX lexicon path adapted to notebook units (no speakers)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from transcribe.analysis.document import AnalysisDocument, content_fingerprint
from transcribe.analysis.modules._lexicon_markers import (
    ALGORITHM_VERSION,
    TOKENIZER_VERSION,
    count_tokens,
    derive_epistemic_shares,
    iter_phrases,
    load_categorized_lexicon,
    match_phrases_in_text,
    stats_for_scope,
)
from transcribe.domain.fingerprint import sha256_bytes

MODULE_ID = "epistemic_markers"
MODULE_VERSION = "1.3.0"
PAYLOAD_SCHEMA = "epistemic_markers_payload_v1"
LEXICON_FILENAME = "epistemic_markers_en.json"
LEXICON_ID = "epistemic_markers_en_v1"
MIN_TOKENS_FOR_RATES = 20
CATEGORIES = (
    "epistemic_hedge",
    "approximator",
    "modal_uncertainty",
    "certainty_booster",
)

_LEXICON_PATH = Path(__file__).resolve().parents[1] / "data" / LEXICON_FILENAME
_LEXICON_CACHE: dict | None = None
_LEXICON_DIGEST: str | None = None

TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


def _load_lexicon():
    global _LEXICON_CACHE, _LEXICON_DIGEST
    if _LEXICON_CACHE is not None and _LEXICON_DIGEST is not None:
        return _LEXICON_CACHE, _LEXICON_DIGEST
    raw = _LEXICON_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    _LEXICON_CACHE = load_categorized_lexicon(_LEXICON_PATH)
    _LEXICON_DIGEST = digest
    return _LEXICON_CACHE, _LEXICON_DIGEST


def lexicon_digest() -> str:
    return _load_lexicon()[1]


def epistemic_config() -> dict[str, Any]:
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
        "tokenizer_version": TOKENIZER_VERSION,
        "lexicon_id": LEXICON_ID,
        "lexicon_digest": lexicon_digest(),
        "min_tokens_for_rates": MIN_TOKENS_FOR_RATES,
        "categories": list(CATEGORIES),
    }


def epistemic_lexicon_or_model() -> dict[str, Any]:
    return {"lexicon_id": LEXICON_ID, "lexicon_digest": lexicon_digest()}


class EpistemicMarkersModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    semantic_class = "adaptation"
    semantic_delta = (
        "speaker stats removed; unit/page rollups; TX lexicon_markers_v1 matching; "
        "pinned epistemic_markers_en.json"
    )
    ported_from_commit = TX_COMMIT

    def cache_config(self) -> dict[str, Any]:
        return epistemic_config()

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

        lexicon, digest = _load_lexicon()
        phrases = iter_phrases(lexicon, CATEGORIES)
        doc_fp = content_fingerprint(document)
        hits: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        category_counts = {c: 0 for c in CATEGORIES}
        total_tokens = 0
        units_out: list[dict[str, Any]] = []

        for unit in sorted(document.units, key=lambda u: u.order):
            unit_hits = match_phrases_in_text(
                unit.text,
                phrases,
                unit_id=unit.unit_id,
                unit_order=unit.order,
                module=MODULE_ID,
            )
            tokens = count_tokens(unit.text)
            total_tokens += tokens
            unit_counts = {c: 0 for c in CATEGORIES}
            for hit in unit_hits:
                unit_counts[hit.category] = unit_counts.get(hit.category, 0) + 1
                category_counts[hit.category] += 1
                hit_dict = hit.as_dict()
                hits.append(hit_dict)
                evidence.append(
                    {
                        "unit_id": unit.unit_id,
                        "char_start": hit.start,
                        "char_end": hit.end,
                        "quote": hit.surface,
                        "content_fingerprint": doc_fp,
                        "source_ref": dict(unit.source_ref),
                        "category": hit.category,
                    }
                )
            unit_stats = stats_for_scope(
                unit_counts, tokens, CATEGORIES, MIN_TOKENS_FOR_RATES
            )
            units_out.append(
                {
                    "unit_id": unit.unit_id,
                    "order": unit.order,
                    "date": unit.date,
                    **unit_stats,
                }
            )

        global_stats = stats_for_scope(
            category_counts, total_tokens, CATEGORIES, MIN_TOKENS_FOR_RATES
        )
        shares = derive_epistemic_shares(global_stats)
        global_stats = {**global_stats, **shares}

        payload = {
            "schema": PAYLOAD_SCHEMA,
            "algorithm_version": ALGORITHM_VERSION,
            "tokenizer_version": TOKENIZER_VERSION,
            "lexicon_id": LEXICON_ID,
            "lexicon_digest": digest,
            "global_stats": global_stats,
            "units": units_out,
            "hits": hits,
        }
        return {
            "outcome": "success",
            "payload": payload,
            "warnings": [],
            "partial": False,
            "evidence": evidence,
        }


def provenance_files() -> list[dict[str, str]]:
    return [
        {
            "path": "src/transcriptx/preprocessing/lexicons/epistemic_markers_en.json",
            "sha256": lexicon_digest(),
        },
        {
            "path": "src/transcriptx/core/analysis/lexicon_markers/__init__.py",
            "sha256": "85879f6d34591c90403b0f25ccadc5581ce76d84c70bd378a41e5e86cfa67a9d",
        },
    ]


def code_digest() -> str:
    return sha256_bytes(Path(__file__).read_bytes())
