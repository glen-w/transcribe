"""Unit tests for OCR cleanup validator policy v1."""

from __future__ import annotations

from transcribe.domain.fingerprint import compute_input_fingerprint
from transcribe.services.cleanup_policy import (
    CLEANUP_VALIDATOR_POLICY_ID,
    CLEANUP_VALIDATOR_POLICY_VERSION,
    compute_num_predict,
    narrow_unwrap_fence,
    nfkc,
    validate_cleanup_candidate,
)


def test_narrow_fence_unwrap_whole_response_only():
    body = "hello page"
    assert narrow_unwrap_fence(f"```\n{body}\n```") == body
    assert narrow_unwrap_fence(f"```md\n{body}\n```") == body
    mixed = f"```\n{body}\n```\ntrailing"
    assert narrow_unwrap_fence(mixed) == mixed


def test_identical_nfkc_is_unchanged_note():
    src = "Café notes"
    cand = nfkc("Café notes")
    v = validate_cleanup_candidate(source=src, candidate=cand, mode="strip_leak")
    assert v.note == "identical_nfkc"


def test_empty_candidate_rejected_first():
    v = validate_cleanup_candidate(
        source="real notebook text here",
        candidate="   ",
        mode="sanitize_light",
        truncated=True,
    )
    assert v.note == "empty_output"


def test_truncated_before_artefact():
    v = validate_cleanup_candidate(
        source="real notebook text about weather",
        candidate="- Do not change the order of words\nweather",
        mode="strip_leak",
        truncated=True,
    )
    assert v.note == "truncated_output"


def test_prompt_artefact_strip_leak():
    src = "Une beauté pénétrante\net si tu crois"
    cand = "- Use proper punctuation\n- Avoid contractions\n\n" + src
    v = validate_cleanup_candidate(source=src, candidate=cand, mode="strip_leak")
    assert v.note == "prompt_artefact"


def test_strip_leak_min_retained_blocks_page_deletion():
    # Shrink within max_shrink_ratio but recall below strip_leak threshold.
    src = " ".join([f"word{i}" for i in range(20)])
    cand = " ".join([f"word{i}" for i in range(5)])
    v = validate_cleanup_candidate(source=src, candidate=cand, mode="strip_leak")
    assert v.note == "min_retained_failed"


def test_strip_leak_rejects_ungrounded_candidate():
    src = "alpha beta gamma delta epsilon zeta eta th"
    cand = "alpha beta quantum invented nonsense zz zz"
    assert len(src) == len(cand)
    v = validate_cleanup_candidate(source=src, candidate=cand, mode="strip_leak")
    assert v.note == "min_retained_failed"


def test_sanitize_light_ratio_exceeded():
    src = "a" * 100
    cand = "a" * 100 + "b" * 50
    v = validate_cleanup_candidate(source=src, candidate=cand, mode="sanitize_light")
    assert v.note in {"ratio_exceeded", "abs_ceiling_exceeded", "min_retained_failed"}


def test_applied_path_passes_strip_leak_preamble_strip():
    page = "Gush!\n260524 1954\nStill stuck between future and past"
    leaked = (
        "- Do not change the order of words in sentences\n"
        "- Use proper punctuation and grammar\n"
        "---\n"
        f"{page}"
    )
    # Candidate is clean page only — should pass.
    v = validate_cleanup_candidate(source=leaked, candidate=page, mode="strip_leak")
    assert v.note is None


def test_num_predict_bounds():
    assert compute_num_predict(10) >= 1024
    assert compute_num_predict(50_000) <= 8192


def test_fingerprint_includes_cleanup_when_enabled():
    base = dict(
        provider="ollama",
        model_name="vision",
        model_digest="d1",
        model_identity_verified=True,
        input_sha256="aa",
        prompt_sha256="bb",
        preprocess_profile="none",
        preprocess_version=1,
        generation_options={"temperature": 0.0},
    )
    a, pa = compute_input_fingerprint(**base)
    b, pb = compute_input_fingerprint(
        **base,
        cleanup={
            "enabled": True,
            "mode": "strip_leak",
            "model_name": "llama",
            "model_digest": "cd",
            "model_identity_verified": True,
            "prompt_id": "cleanup_strip_leak",
            "prompt_version": "1",
            "prompt_sha256": "cc",
            "cleanup_validator_policy_id": CLEANUP_VALIDATOR_POLICY_ID,
            "cleanup_validator_policy_version": CLEANUP_VALIDATOR_POLICY_VERSION,
        },
    )
    assert a != b
    assert "cleanup" not in pa
    assert pb["cleanup"]["mode"] == "strip_leak"


def test_fingerprint_unchanged_when_cleanup_omitted():
    kwargs = dict(
        provider="ollama",
        model_name="vision",
        model_digest="d1",
        model_identity_verified=True,
        input_sha256="aa",
        prompt_sha256="bb",
        preprocess_profile="none",
        preprocess_version=1,
        generation_options={"temperature": 0.0},
    )
    a, _ = compute_input_fingerprint(**kwargs)
    b, _ = compute_input_fingerprint(**kwargs, cleanup=None)
    assert a == b
