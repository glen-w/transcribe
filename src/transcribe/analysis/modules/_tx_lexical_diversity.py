"""Lexical diversity metrics: TTR, MTLD, hapax rate."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

LEXICAL_DIVERSITY_SCHEMA_ID = "transcriptx.lexical_diversity.v1"
LEXICAL_DIVERSITY_ALGORITHM_VERSION = "1"
TOKENIZER_VERSION = "1"
MTLD_FACTOR_THRESHOLD = 0.72
MIN_MTLD_TOKENS = 50
TIME_BUCKET_SECONDS = 60

TOKEN_RE = re.compile(r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*", re.UNICODE)


def tokenize(text: str) -> List[str]:
    """Return case-folded lexical tokens from text."""
    if not text:
        return []
    tokens = [match.group(0) for match in TOKEN_RE.finditer(text.casefold())]
    return [token for token in tokens if len(token) >= 2]


def _mtld_pass(tokens: List[str], *, threshold: float = MTLD_FACTOR_THRESHOLD) -> float:
    if not tokens:
        return 0.0
    factors: List[float] = []
    types: set[str] = set()
    count = 0
    for token in tokens:
        count += 1
        types.add(token)
        ttr = len(types) / count
        if ttr <= threshold:
            factors.append(float(count))
            types = set()
            count = 0
    if count > 0:
        ttr = len(types) / count
        if ttr >= 1.0:
            partial = float(count)
        else:
            partial = count / (1.0 - ttr)
        factors.append(float(partial))
    if not factors:
        return 0.0
    return sum(factors) / len(factors)


def compute_mtld(tokens: List[str]) -> Optional[float]:
    if len(tokens) < MIN_MTLD_TOKENS:
        return None
    forward = _mtld_pass(tokens)
    reverse = _mtld_pass(list(reversed(tokens)))
    value = (forward + reverse) / 2.0
    if not math.isfinite(value):
        return None
    return float(value)


def compute_lexical_diversity_metrics(text: str) -> Dict[str, Any]:
    """Compute token/type/TTR/MTLD/hapax metrics for one text block."""
    tokens = tokenize(text)
    token_count = len(tokens)
    if token_count == 0:
        return {
            "token_count": 0,
            "type_count": 0,
            "hapax_count": 0,
            "ttr": None,
            "mtld": None,
            "hapax_rate": None,
        }
    freq: Dict[str, int] = {}
    for token in tokens:
        freq[token] = freq.get(token, 0) + 1
    type_count = len(freq)
    hapax_count = sum(1 for count in freq.values() if count == 1)
    ttr = type_count / token_count
    hapax_rate = hapax_count / type_count if type_count else None
    mtld = compute_mtld(tokens)
    return {
        "token_count": token_count,
        "type_count": type_count,
        "hapax_count": hapax_count,
        "ttr": float(ttr),
        "mtld": mtld,
        "hapax_rate": float(hapax_rate) if hapax_rate is not None else None,
    }


def build_metadata() -> Dict[str, Any]:
    return {
        "schema_id": LEXICAL_DIVERSITY_SCHEMA_ID,
        "algorithm_version": LEXICAL_DIVERSITY_ALGORITHM_VERSION,
        "tokenizer_version": TOKENIZER_VERSION,
        "mtld_factor_threshold": MTLD_FACTOR_THRESHOLD,
        "min_mtld_tokens": MIN_MTLD_TOKENS,
        "bucket_seconds": TIME_BUCKET_SECONDS,
    }
