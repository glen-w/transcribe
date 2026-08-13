"""Offline unit coverage for analysis result envelope helpers."""

from __future__ import annotations

import pytest

from transcribe.analysis.envelope import (
    build_envelope,
    derive_capability,
    filter_live_evidence,
    round_floats,
)


def test_derive_capability_matrix():
    assert derive_capability(outcome="success") == "success"
    assert derive_capability(outcome="success", partial=True) == "partial"
    assert derive_capability(outcome="insufficient_data") == "insufficient_data"
    assert (
        derive_capability(outcome="insufficient_data", reason="invalid_document") == "invalid_input"
    )
    assert derive_capability(outcome="unavailable_dependency") == "unavailable_dependency"
    assert (
        derive_capability(outcome="skipped_not_applicable", reason="unavailable_extra")
        == "unavailable_extra"
    )
    assert (
        derive_capability(outcome="skipped_not_applicable", reason="unavailable_model")
        == "unavailable_model"
    )
    assert derive_capability(outcome="skipped_not_applicable") == "skipped_not_applicable"
    assert derive_capability(outcome="failed") == "failed"


def test_filter_live_evidence_ignores_non_dicts():
    live = filter_live_evidence(
        [
            {"content_fingerprint": "ok", "quote": "a"},
            "not-a-dict",
            {"content_fingerprint": "other", "quote": "b"},
            None,
        ],
        current_content_fingerprint="ok",
    )
    assert live == [{"content_fingerprint": "ok", "quote": "a"}]


def test_round_floats_nested_and_nonfinite():
    out = round_floats({"a": 1.23456789, "b": [float("nan"), 2.0], "c": "x"}, ndigits=3)
    assert out["a"] == 1.235
    assert out["b"][1] == 2.0
    assert out["c"] == "x"
    assert isinstance(out["b"][0], float) and out["b"][0] != out["b"][0]  # NaN


def test_build_envelope_rejects_invalid_states():
    base = dict(
        project_id="p",
        module_id="stats",
        module_version="1.0.0",
        cache_identity="c" * 64,
        content_fingerprint="d" * 64,
        payload={},
        provenance={},
        config_fingerprint="e" * 64,
    )
    with pytest.raises(ValueError, match="attempt_state"):
        build_envelope(**base, attempt_state="nope", outcome="success")
    with pytest.raises(ValueError, match="outcome"):
        build_envelope(**base, attempt_state="succeeded", outcome="nope")


def test_build_envelope_maps_unavailable_extra_capability():
    env = build_envelope(
        project_id="p",
        module_id="ner",
        module_version="1.3.0",
        cache_identity="c" * 64,
        content_fingerprint="d" * 64,
        attempt_state="succeeded",
        outcome="skipped_not_applicable",
        payload={"error": {"code": "unavailable_extra"}},
        provenance={},
        config_fingerprint="e" * 64,
        capability_reason="unavailable_extra",
        published=True,
    )
    assert env["capability"] == "unavailable_extra"
    assert env["format"] == "transcribe.analysis-result"
    assert env["published"] is True
