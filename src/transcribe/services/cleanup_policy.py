"""Versioned OCR cleanup validator policy (ocr_cleanup_validator v1)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

CLEANUP_VALIDATOR_POLICY_ID = "ocr_cleanup_validator"
CLEANUP_VALIDATOR_POLICY_VERSION = "1"

MIN_LENGTH_DENOM = 40
NUM_CTX_FALLBACK = 8192
NUM_PREDICT_MIN = 1024
NUM_PREDICT_MAX = 8192

CleanupMode = Literal["strip_leak", "sanitize_light", "rewrite"]

ValidatorNote = Literal[
    "empty_output",
    "truncated_output",
    "prompt_artefact",
    "faithfulness_artefact",
    "identical_nfkc",
    "abs_ceiling_exceeded",
    "ratio_exceeded",
    "min_retained_failed",
]


@dataclass(frozen=True)
class ModeBudget:
    max_growth_ratio: float | None
    max_growth_abs: int | None
    max_shrink_ratio: float | None
    max_abs_delta: int | None
    mode_ratio: float | None
    min_retained_token_coverage: float  # recall vs source
    min_groundedness: float  # precision vs candidate


# Frozen v1 budgets — do not tune ad hoc at call sites.
MODE_BUDGETS: dict[str, ModeBudget] = {
    "strip_leak": ModeBudget(
        max_growth_ratio=0.05,
        max_growth_abs=80,
        max_shrink_ratio=0.90,
        max_abs_delta=None,
        mode_ratio=None,
        min_retained_token_coverage=0.35,
        min_groundedness=0.90,
    ),
    "sanitize_light": ModeBudget(
        max_growth_ratio=None,
        max_growth_abs=None,
        max_shrink_ratio=None,
        max_abs_delta=400,
        mode_ratio=0.20,
        min_retained_token_coverage=0.70,
        min_groundedness=0.85,
    ),
    "rewrite": ModeBudget(
        max_growth_ratio=None,
        max_growth_abs=None,
        max_shrink_ratio=None,
        max_abs_delta=2000,
        mode_ratio=0.50,
        min_retained_token_coverage=0.40,
        min_groundedness=0.75,
    ),
}

# Instruction / meta text that must not appear as cleaned OCR.
_ARTEFACT_RE = re.compile(
    r"(?im)^(?:\s*[-*•]\s*)?(?:"
    r"do\s+not\s+(?:change|use|add|summarize)|"
    r"use\s+(?:proper|a\s+clear|consistent)\s+(?:punctuation|writing|style)|"
    r"avoid\s+(?:using\s+)?(?:contractions|abbreviations)|"
    r"keep\s+the\s+tone\s+consistent|"
    r"if\s+you\s+need\s+to\s+(?:add|use)\s+(?:a\s+word|additional)|"
    r"write\s+it\s+in\s+square\s+brackets|"
    r"format\s+the\s+output\s+in\s+markdown|"
    r"extract\s+all\s+(?:text|visible)\s+(?:content\s+)?from\s+this"
    r")"
)

_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ÿ]+", re.UNICODE)

# Whole-response fence only (optional language tag).
_WHOLE_FENCE_RE = re.compile(
    r"\A\s*```(?:[a-zA-Z0-9_+-]*)\s*\n([\s\S]*?)\n```\s*\Z",
)


def nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def tokenize(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(nfkc(text))}


def token_coverage(source: str, candidate: str) -> tuple[float, float]:
    """Return (recall vs source, precision vs candidate)."""
    src = tokenize(source)
    cand = tokenize(candidate)
    if not src and not cand:
        return 1.0, 1.0
    inter = len(src & cand)
    recall = inter / len(src) if src else 1.0
    precision = inter / len(cand) if cand else 0.0
    return recall, precision


def length_denom(source_nfkc: str) -> int:
    return max(len(source_nfkc), MIN_LENGTH_DENOM)


def narrow_unwrap_fence(raw: str) -> str:
    """Unwrap only when the entire response is a single fenced block."""
    text = raw if raw is not None else ""
    match = _WHOLE_FENCE_RE.match(text)
    if match:
        return match.group(1)
    return text


def compute_num_predict(source_len: int, *, num_ctx: int | None = None) -> int:
    ctx = num_ctx if num_ctx and num_ctx > 0 else NUM_CTX_FALLBACK
    soft_max = min(NUM_PREDICT_MAX, max(NUM_PREDICT_MIN, ctx // 4))
    target = source_len + 512
    return max(NUM_PREDICT_MIN, min(soft_max, target))


@dataclass(frozen=True)
class ValidationResult:
    note: ValidatorNote | None
    original_length: int
    candidate_length: int
    length_ratio: float | None


def validate_cleanup_candidate(
    *,
    source: str,
    candidate: str,
    mode: str,
    truncated: bool = False,
) -> ValidationResult:
    """First-failure-wins validator. ``identical_nfkc`` is not a rejection."""
    budget = MODE_BUDGETS[mode]
    src = nfkc(source)
    cand = nfkc(candidate)
    orig_len = len(src)
    cand_len = len(cand)
    denom = float(length_denom(src))
    delta = cand_len - orig_len
    ratio = abs(delta) / denom if denom else None

    def _res(note: ValidatorNote | None) -> ValidationResult:
        return ValidationResult(
            note=note,
            original_length=orig_len,
            candidate_length=cand_len,
            length_ratio=ratio,
        )

    if not cand.strip():
        return _res("empty_output")
    if truncated:
        return _res("truncated_output")
    if _ARTEFACT_RE.search(cand):
        if mode == "strip_leak":
            return _res("prompt_artefact")
        return _res("faithfulness_artefact")
    if src == cand:
        return _res("identical_nfkc")

    if mode == "strip_leak":
        if delta > 0:
            if budget.max_growth_abs is not None and delta > budget.max_growth_abs:
                return _res("abs_ceiling_exceeded")
            if (
                budget.max_growth_ratio is not None
                and ratio is not None
                and ratio > budget.max_growth_ratio
            ):
                return _res("ratio_exceeded")
        if delta < 0 and budget.max_shrink_ratio is not None:
            shrink = abs(delta) / denom
            if shrink > budget.max_shrink_ratio:
                return _res("ratio_exceeded")
    else:
        if budget.max_abs_delta is not None and abs(delta) > budget.max_abs_delta:
            return _res("abs_ceiling_exceeded")
        if (
            budget.mode_ratio is not None
            and ratio is not None
            and ratio > budget.mode_ratio
        ):
            return _res("ratio_exceeded")

    recall, precision = token_coverage(src, cand)
    if precision < budget.min_groundedness:
        return _res("min_retained_failed")
    if recall < budget.min_retained_token_coverage:
        return _res("min_retained_failed")

    return _res(None)
