"""Semantic similarity — bag-of-words cosine across units (no multi-speaker gate)."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules._tx_lexical_diversity import tokenize
from transcribe.analysis.modules.wordclouds import _load_stopwords

MODULE_ID = "semantic_similarity"
MODULE_VERSION = "1c.0"
PAYLOAD_SCHEMA = "semantic_similarity_payload_v1"
ALGORITHM_VERSION = "bow_cosine_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"
MOTIF_THRESHOLD = 0.55
MAX_MOTIFS = 25


def semantic_similarity_config() -> dict[str, Any]:
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
        "motif_threshold": MOTIF_THRESHOLD,
        "max_motifs": MAX_MOTIFS,
    }


def provenance_files() -> list[dict[str, str]]:
    return []


def _unit_tokens(text: str, stop: set[str]) -> list[str]:
    return [t for t in tokenize(text) if t not in stop and len(t) > 2]


def build_unit_vectors(
    units: list[Any],
) -> tuple[list[str], list[dict[str, float]], list[list[str]]]:
    """Return (unit_ids, sparse tf-idf vectors as dicts, token lists)."""
    stop, _ = _load_stopwords()
    unit_ids: list[str] = []
    token_lists: list[list[str]] = []
    df: Counter[str] = Counter()
    for unit in sorted(units, key=lambda u: u.order):
        toks = _unit_tokens(unit.text, stop)
        unit_ids.append(unit.unit_id)
        token_lists.append(toks)
        df.update(set(toks))
    n_docs = max(1, len(token_lists))
    vectors: list[dict[str, float]] = []
    for toks in token_lists:
        tf = Counter(toks)
        vec: dict[str, float] = {}
        for term, count in tf.items():
            idf = math.log((n_docs + 1) / (df[term] + 1)) + 1.0
            vec[term] = float(count) * idf
        vectors.append(vec)
    return unit_ids, vectors, token_lists


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    # Prefer iterating the smaller dict.
    if len(a) > len(b):
        a, b = b, a
    dot = 0.0
    for k, va in a.items():
        vb = b.get(k)
        if vb is not None:
            dot += va * vb
    if dot == 0.0:
        return 0.0
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return float(dot / (na * nb))


def pairwise_matrix(vectors: list[dict[str, float]]) -> list[list[float]]:
    n = len(vectors)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        matrix[i][i] = 1.0
        for j in range(i + 1, n):
            sim = round(cosine(vectors[i], vectors[j]), 6)
            matrix[i][j] = sim
            matrix[j][i] = sim
    return matrix


class SemanticSimilarityModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = (
        "BoW TF-IDF cosine across notebook units; multi-speaker gate dropped"
    )

    def cache_config(self) -> dict[str, Any]:
        return semantic_similarity_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = llm_ctx, question_text
        _ = parents
        if len(document.units) < 2:
            return {
                "outcome": "insufficient_data",
                "payload": {},
                "warnings": [
                    {
                        "code": "need_two_units",
                        "message": "semantic_similarity requires ≥2 units",
                    }
                ],
            }

        unit_ids, vectors, _ = build_unit_vectors(document.units)
        matrix = pairwise_matrix(vectors)
        motifs: list[dict[str, Any]] = []
        for i in range(len(unit_ids)):
            for j in range(i + 1, len(unit_ids)):
                sim = matrix[i][j]
                if sim >= MOTIF_THRESHOLD:
                    motifs.append(
                        {
                            "unit_id_a": unit_ids[i],
                            "unit_id_b": unit_ids[j],
                            "similarity": sim,
                        }
                    )
        motifs.sort(key=lambda row: (-row["similarity"], row["unit_id_a"], row["unit_id_b"]))
        motifs = motifs[:MAX_MOTIFS]
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "algorithm_version": ALGORITHM_VERSION,
                "unit_ids": unit_ids,
                "matrix": matrix,
                "motifs": motifs,
                "motif_threshold": MOTIF_THRESHOLD,
                "n_units": len(unit_ids),
            },
        }
