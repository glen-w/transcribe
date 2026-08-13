"""U3 model advice / identity product copy."""

from __future__ import annotations

from transcribe.providers.base import ModelInfo
from transcribe.services.model_advice import advise_model, use_case_label
from transcribe.services.ocr_preference_stats import (
    ModelPreferenceStats,
    preference_hint_for_model,
)
from transcribe.ui.components.model_info import _identity_caption, _role_for_model


def test_ocr_oriented_use_case_is_first_ocr() -> None:
    advice = advise_model("glm-ocr", role="vision")
    assert advice.use_case == "first_ocr"
    assert use_case_label(advice) == "Suggested for first OCR"


def test_general_vlm_use_case_is_quality() -> None:
    advice = advise_model("llava", role="vision")
    assert advice.use_case == "quality"
    assert "quality" in (use_case_label(advice) or "").lower()


def test_text_model_copy_mentions_analyse() -> None:
    advice = advise_model("llama3.2", role="text")
    assert advice.use_case == "text"
    assert any("Analyse" in w or "text model" in w.lower() for w in advice.warnings)


def test_identity_caption_verified_and_unverified() -> None:
    verified = ModelInfo(
        name="m",
        digest="abcdef0123456789",
        size=1_000_000_000,
        family="x",
        parameter_size="7B",
        capabilities=("vision",),
        capability_known=True,
    )
    assert "verified" in _identity_caption(verified).lower()
    unverified = ModelInfo(
        name="m",
        digest=None,
        size=None,
        family=None,
        parameter_size=None,
        capabilities=(),
        capability_known=False,
    )
    assert "unverified" in _identity_caption(unverified).lower()


def test_role_for_model_all_uses_capabilities() -> None:
    vision = ModelInfo(
        name="v",
        digest=None,
        size=None,
        family=None,
        parameter_size=None,
        capabilities=("vision",),
        capability_known=True,
    )
    text = ModelInfo(
        name="t",
        digest=None,
        size=None,
        family=None,
        parameter_size=None,
        capabilities=("completion",),
        capability_known=True,
    )
    assert _role_for_model("v", vision, role="all") == "vision"
    assert _role_for_model("t", text, role="all") == "text"


def test_preference_hint_includes_last_ts() -> None:
    stats = {
        "glm-ocr": ModelPreferenceStats(
            model_name="glm-ocr",
            prefer_count=2,
            pages={"n:p1", "n:p2"},
            last_ts="2026-08-12T10:00:00Z",
        )
    }
    hint = preference_hint_for_model("glm-ocr", stats=stats)
    assert hint is not None
    assert "2026-08-12" in hint
