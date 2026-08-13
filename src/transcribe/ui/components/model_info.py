"""Collapsed model metadata + caveats next to Streamlit model pickers."""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from transcribe.providers.base import ModelInfo
from transcribe.services.model_advice import advise_model, is_general_vlm_name, use_case_label
from transcribe.services.ocr_preference_stats import preference_hint_for_model


def _format_size(size: int | None) -> str:
    if not size or size < 0:
        return "—"
    if size >= 1_000_000_000:
        return f"{size / 1_000_000_000:.1f} GB"
    if size >= 1_000_000:
        return f"{size / 1_000_000:.0f} MB"
    return f"{size} B"


def _identity_caption(info: ModelInfo | None) -> str:
    if info is None:
        return "Identity: unknown (model not in current discovery)."
    digest = (info.digest or "").strip()
    if digest:
        short = digest if len(digest) <= 16 else f"{digest[:12]}…"
        return (
            f"Identity: verified ({short}). Matching fingerprints can skip re-OCR."
        )
    return (
        "Identity: unverified (no digest from Ollama). "
        "Fingerprints may not skip re-OCR reliably until identity is verified."
    )


def _role_for_model(name: str, info: ModelInfo | None, *, role: str) -> str:
    if role in {"vision", "text"}:
        return role
    if info is not None and info.capabilities:
        caps = {c.lower() for c in info.capabilities}
        if "vision" in caps or "image" in caps:
            return "vision"
        if "embedding" in caps:
            return "text"
        if "completion" in caps or "chat" in caps:
            return "text"
    # Name heuristics when discovery lacks capability tags.
    lower = (name or "").lower()
    if any(tok in lower for tok in ("llava", "vision", "ocr", "moondream", "minicpm-v")):
        return "vision"
    return "text"


def render_model_information(
    models: Sequence[ModelInfo],
    *,
    selected: str | Sequence[str],
    role: str = "vision",
    key: str = "model_info",
) -> None:
    """Expander describing the currently selected model(s)."""
    del key
    names = [selected] if isinstance(selected, str) else [n for n in selected if n]
    names = [n for n in names if str(n).strip()]
    if not names:
        return
    by_name = {m.name: m for m in models}
    with st.expander("Model information", expanded=False):
        for index, name in enumerate(names):
            if index:
                st.divider()
            info = by_name.get(name)
            model_role = _role_for_model(name, info, role=role)
            advice = advise_model(name, role=model_role)
            st.markdown(f"**{name}** · {advice.title}")
            case = use_case_label(advice)
            if case:
                st.caption(case)
            st.caption(_identity_caption(info))
            if info is not None:
                caps = ", ".join(info.capabilities) if info.capabilities else "unknown"
                bits = [
                    f"family `{info.family or '—'}`",
                    f"params `{info.parameter_size or '—'}`",
                    f"size {_format_size(info.size)}",
                    f"capabilities `{caps}`",
                ]
                st.caption(" · ".join(bits))
            else:
                st.caption("Not listed in the current Ollama discovery refresh.")
            hint = preference_hint_for_model(name)
            if hint:
                st.caption(hint)
            for warning in advice.warnings:
                st.caption(warning)
            if advice.kind == "general_vlm":
                st.warning(
                    "This is a general vision-language model, not an OCR model. "
                    "It can hang on dense scans; prefer an OCR-oriented model, "
                    "especially as the first compare model."
                )


def warn_if_first_compare_model_is_general_vlm(model_names: Sequence[str]) -> None:
    if not model_names:
        return
    first = str(model_names[0] or "")
    if is_general_vlm_name(first):
        st.warning(
            f"`{first}` is a general vision-language model. Compare runs models "
            "in order — put an OCR-oriented model first so later models can skip "
            "pages that already match."
        )
