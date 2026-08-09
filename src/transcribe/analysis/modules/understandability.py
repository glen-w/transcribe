"""Understandability — notebook adaptation without nltk/textstat deps."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules._tx_lexical_diversity import tokenize
from transcribe.domain.fingerprint import sha256_bytes

MODULE_ID = "understandability"
MODULE_VERSION = "1.1.0"
ALGORITHM_VERSION = "1"

_SENTENCE_RE = re.compile(r"[^.?!]+[.?!]+|[^.?!]+$", re.UNICODE)


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_RE.findall(text)]
    return [p for p in parts if p]


def _syllable_count(word: str) -> int:
    w = word.casefold()
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for ch in w:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if w.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def compute_readability(text: str) -> dict[str, Any]:
    sentences = split_sentences(text)
    words = tokenize(text)
    n_sent = len(sentences)
    n_words = len(words)
    if n_sent < 1 or n_words < 3:
        return {
            "word_count": n_words,
            "sentence_count": n_sent,
            "insufficient": True,
        }
    n_syll = sum(_syllable_count(w) for w in words)
    asl = n_words / n_sent
    asw = n_syll / n_words
    # Flesch Reading Ease
    fre = 206.835 - 1.015 * asl - 84.6 * asw
    # Automated Readability Index (chars via original tokens' lengths)
    chars = sum(len(w) for w in words)
    ari = 4.71 * (chars / n_words) + 0.5 * asl - 21.43
    # Gunning fog approximation (complex = 3+ syllables)
    complex_words = sum(1 for w in words if _syllable_count(w) >= 3)
    fog = 0.4 * (asl + 100.0 * (complex_words / n_words))
    lexical_density = len(set(words)) / n_words
    metrics = {
        "flesch_reading_ease": float(fre),
        "gunning_fog_index": float(fog),
        "automated_readability_index": float(ari),
        "avg_sentence_length": float(asl),
        "lexical_density": float(lexical_density),
        "word_count": n_words,
        "sentence_count": n_sent,
        "algorithm_version": ALGORITHM_VERSION,
    }
    for key, value in list(metrics.items()):
        if isinstance(value, float) and not math.isfinite(value):
            return {"non_finite": True, "field": key, **metrics}
    return metrics


class UnderstandabilityModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    semantic_class = "adaptation"
    semantic_delta = (
        "speaker grouping removed; pure-Python readability (no nltk/textstat)"
    )

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = parents, llm_ctx, question_text
        metrics = compute_readability(document.text)
        if metrics.get("insufficient"):
            return {
                "outcome": "insufficient_data",
                "payload": {
                    "document": {
                        "word_count": metrics["word_count"],
                        "sentence_count": metrics["sentence_count"],
                    }
                },
                "warnings": [],
                "partial": False,
            }
        if metrics.get("non_finite"):
            return {
                "outcome": "failed",
                "payload": {"document": metrics},
                "warnings": [
                    {
                        "code": "non_finite_metric",
                        "message": f"non-finite value in {metrics.get('field')}",
                    }
                ],
                "partial": False,
            }
        per_unit = []
        for unit in document.units:
            m = compute_readability(unit.text)
            if m.get("insufficient") or m.get("non_finite"):
                continue
            per_unit.append({"unit_id": unit.unit_id, "order": unit.order, **m})
        return {
            "outcome": "success",
            "payload": {"document": metrics, "units": per_unit},
            "warnings": [],
            "partial": False,
        }


def provenance_files() -> list[dict[str, str]]:
    return []


def code_digest() -> str:
    return sha256_bytes(Path(__file__).read_bytes())
