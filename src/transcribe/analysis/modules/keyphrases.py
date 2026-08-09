"""Keyphrases — notebook adaptation; requires notebook_eligibility_v1."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules._tx_lexical_diversity import tokenize
from transcribe.analysis.modules.wordclouds import _load_stopwords
from transcribe.config.facade import require_operation_config
from transcribe.config.knobs import module_knob_dict

MODULE_ID = "keyphrases"
MODULE_VERSION = "1.4.0"
PAYLOAD_SCHEMA = "keyphrases_payload_v1"
ALGORITHM_VERSION = "keyphrases_tfidf_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


def keyphrases_config() -> dict[str, Any]:
    cfg = require_operation_config()
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
        **module_knob_dict(cfg, MODULE_ID),
    }


def provenance_files() -> list[dict[str, str]]:
    return []


def _ngrams(tokens: list[str], n: int) -> list[str]:
    if n <= 1:
        return list(tokens)
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


class KeyphrasesModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = "TF-IDF unigram/bigram ranking on eligible notebook units; no TX spaCy path"

    def cache_config(self) -> dict[str, Any]:
        return keyphrases_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = parents, llm_ctx, question_text
        top_n = require_operation_config().analysis.keyphrases.top_n
        if not document.units or not document.text.strip():
            return {
                "outcome": "insufficient_data",
                "payload": {},
                "capability_reason": None,
            }
        stop, _ = _load_stopwords()
        docs_tokens: list[list[str]] = []
        df: Counter[str] = Counter()
        for unit in document.units:
            toks = [t for t in tokenize(unit.text) if t not in stop and len(t) > 2]
            phrases = _ngrams(toks, 1) + _ngrams(toks, 2)
            docs_tokens.append(phrases)
            df.update(set(phrases))
        n_docs = max(1, len(docs_tokens))
        tf: Counter[str] = Counter()
        for phrases in docs_tokens:
            tf.update(phrases)
        scored: list[tuple[float, str]] = []
        for phrase, count in tf.items():
            idf = math.log((n_docs + 1) / (df[phrase] + 1)) + 1.0
            scored.append((count * idf, phrase))
        scored.sort(key=lambda row: (-row[0], row[1]))
        phrases = [
            {"phrase": phrase, "score": round(score, 6)}
            for score, phrase in scored[:top_n]
        ]
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "phrases": phrases,
                "n_phrases": len(phrases),
            },
        }
