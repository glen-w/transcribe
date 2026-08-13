from __future__ import annotations

from transcribe.domain.fingerprint import compute_input_fingerprint


def test_fingerprint_is_order_independent_for_options():
    a, pa = compute_input_fingerprint(
        provider="ollama",
        model_name="m",
        model_digest="d",
        model_identity_verified=True,
        input_sha256="aa",
        prompt_sha256="bb",
        preprocess_profile="none",
        preprocess_version=1,
        generation_options={"temperature": 0.0, "x": 1},
    )
    b, pb = compute_input_fingerprint(
        provider="ollama",
        model_name="m",
        model_digest="d",
        model_identity_verified=True,
        input_sha256="aa",
        prompt_sha256="bb",
        preprocess_profile="none",
        preprocess_version=1,
        generation_options={"x": 1, "temperature": 0.0},
    )
    assert a == b
    assert pa == pb


def test_fingerprint_changes_with_digest():
    a, _ = compute_input_fingerprint(
        provider="ollama",
        model_name="m",
        model_digest="d1",
        model_identity_verified=True,
        input_sha256="aa",
        prompt_sha256="bb",
        preprocess_profile="none",
        preprocess_version=1,
        generation_options={"temperature": 0.0},
    )
    b, _ = compute_input_fingerprint(
        provider="ollama",
        model_name="m",
        model_digest="d2",
        model_identity_verified=True,
        input_sha256="aa",
        prompt_sha256="bb",
        preprocess_profile="none",
        preprocess_version=1,
        generation_options={"temperature": 0.0},
    )
    assert a != b


def test_fingerprint_golden_stable():
    digest, payload = compute_input_fingerprint(
        provider="ollama",
        model_name="fake-vision",
        model_digest="digest-aaa",
        model_identity_verified=True,
        input_sha256="0" * 64,
        prompt_sha256="1" * 64,
        preprocess_profile="none",
        preprocess_version=1,
        generation_options={"temperature": 0.0},
    )
    assert payload["model_name"] == "fake-vision"
    assert len(digest) == 64


def test_fingerprint_omits_default_num_predict():
    from transcribe.domain.models import DEFAULT_VISION_NUM_PREDICT

    a, pa = compute_input_fingerprint(
        provider="ollama",
        model_name="m",
        model_digest="d",
        model_identity_verified=True,
        input_sha256="aa",
        prompt_sha256="bb",
        preprocess_profile="none",
        preprocess_version=1,
        generation_options={"temperature": 0.0},
    )
    b, pb = compute_input_fingerprint(
        provider="ollama",
        model_name="m",
        model_digest="d",
        model_identity_verified=True,
        input_sha256="aa",
        prompt_sha256="bb",
        preprocess_profile="none",
        preprocess_version=1,
        generation_options={
            "temperature": 0.0,
            "num_predict": DEFAULT_VISION_NUM_PREDICT,
        },
    )
    assert a == b
    assert "num_predict" not in pa["generation_options"]
    assert "num_predict" not in pb["generation_options"]


def test_fingerprint_changes_with_custom_num_predict():
    a, _ = compute_input_fingerprint(
        provider="ollama",
        model_name="m",
        model_digest="d",
        model_identity_verified=True,
        input_sha256="aa",
        prompt_sha256="bb",
        preprocess_profile="none",
        preprocess_version=1,
        generation_options={"temperature": 0.0, "num_predict": 512},
    )
    b, pb = compute_input_fingerprint(
        provider="ollama",
        model_name="m",
        model_digest="d",
        model_identity_verified=True,
        input_sha256="aa",
        prompt_sha256="bb",
        preprocess_profile="none",
        preprocess_version=1,
        generation_options={"temperature": 0.0, "num_predict": 4096},
    )
    assert a != b
    assert pb["generation_options"].get("num_predict") is None
