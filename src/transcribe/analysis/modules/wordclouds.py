"""Baseline wordclouds: document-level token frequencies from AnalysisDocument.text."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules._tx_lexical_diversity import tokenize
from transcribe.domain.fingerprint import sha256_bytes

MODULE_ID = "wordclouds"
MODULE_VERSION = "1.2.0"
ALGORITHM_VERSION = "1"
TOKENIZATION_VERSION = "wordclouds_tokens_v1"
PAYLOAD_SCHEMA = "wordclouds_payload_v1"
ENRICHMENT_MODE = "baseline"
MAX_TOKENS = 100
MIN_TOKEN_LENGTH = 2
WEIGHTING_POLICY = "count_over_max_v1"
STEM_LEMMA_POLICY = "none"
STOPWORDS_ID = "wordclouds_stopwords_v1"

_STOPWORDS_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "wordclouds_stopwords_v1.json"
)
_STOPWORDS_CACHE: set[str] | None = None
_STOPWORDS_DIGEST: str | None = None


def _load_stopwords() -> tuple[set[str], str]:
    global _STOPWORDS_CACHE, _STOPWORDS_DIGEST
    if _STOPWORDS_CACHE is not None and _STOPWORDS_DIGEST is not None:
        return _STOPWORDS_CACHE, _STOPWORDS_DIGEST
    payload = json.loads(_STOPWORDS_PATH.read_text(encoding="utf-8"))
    words = [str(w).casefold() for w in payload["words"]]
    digest = hashlib.sha256(
        json.dumps(sorted(words), separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
    _STOPWORDS_CACHE = set(words)
    _STOPWORDS_DIGEST = digest
    return _STOPWORDS_CACHE, _STOPWORDS_DIGEST


def stopwords_digest() -> str:
    return _load_stopwords()[1]


def wordclouds_config() -> dict[str, Any]:
    _, digest = _load_stopwords()
    return {
        "tokenization_version": TOKENIZATION_VERSION,
        "enrichment_mode": ENRICHMENT_MODE,
        "payload_schema": PAYLOAD_SCHEMA,
        "max_tokens": MAX_TOKENS,
        "min_token_length": MIN_TOKEN_LENGTH,
        "stem_lemma_policy": STEM_LEMMA_POLICY,
        "weighting_policy": WEIGHTING_POLICY,
        "stopwords_id": STOPWORDS_ID,
        "stopwords_digest": digest,
    }


def wordclouds_lexicon_or_model() -> dict[str, Any]:
    return {
        "stopwords_id": STOPWORDS_ID,
        "stopwords_digest": stopwords_digest(),
    }


def eligible_tokens(text: str) -> list[str]:
    """Tokenize document text then drop stopwords (wordclouds_tokens_v1)."""
    stopwords, _ = _load_stopwords()
    return [t for t in tokenize(text) if t not in stopwords]


def build_token_payload(text: str) -> dict[str, Any] | None:
    tokens = eligible_tokens(text)
    if not tokens:
        return None
    counts = Counter(tokens)
    max_count = max(counts.values())
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    emitted = []
    for token, count in ranked[:MAX_TOKENS]:
        weight = round(count / max_count, 6)
        emitted.append({"token": token, "count": count, "weight": weight})
    return {
        "schema": PAYLOAD_SCHEMA,
        "tokenization_version": TOKENIZATION_VERSION,
        "enrichment_mode": ENRICHMENT_MODE,
        "algorithm_version": ALGORITHM_VERSION,
        "tokens": emitted,
    }


class WordcloudsModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    semantic_class = "adaptation"
    semantic_delta = (
        "document.text only; speaker paths removed; enrichment_mode=baseline; "
        "shared TOKEN_RE + pinned wordclouds_stopwords_v1"
    )

    def run(self, document: AnalysisDocument) -> dict[str, Any]:
        if not document.text.strip():
            return {
                "outcome": "insufficient_data",
                "payload": {},
                "warnings": [
                    {
                        "code": "empty_document_text",
                        "message": "AnalysisDocument.text is empty",
                    }
                ],
                "partial": False,
            }
        payload = build_token_payload(document.text)
        if payload is None:
            return {
                "outcome": "insufficient_data",
                "payload": {},
                "warnings": [
                    {
                        "code": "zero_eligible_tokens",
                        "message": "No eligible tokens after wordclouds_tokens_v1 filtering",
                    }
                ],
                "partial": False,
            }
        return {"outcome": "success", "payload": payload, "warnings": [], "partial": False}


def provenance_files() -> list[dict[str, str]]:
    # Notebook-native frequency core; TX wordclouds stack is speaker/spaCy/viz heavy.
    return []


def code_digest() -> str:
    data = Path(__file__).read_bytes()
    return sha256_bytes(data)
