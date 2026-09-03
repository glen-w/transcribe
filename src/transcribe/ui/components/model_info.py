"""Collapsed model metadata + chooser tables next to Streamlit model pickers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import streamlit as st

from transcribe.providers.base import ModelInfo
from transcribe.services.model_advice import (
    ModelAdvice,
    advise_model,
    chooser_caption,
    is_general_vlm_name,
    use_case_label,
)
from transcribe.services.ocr_preference_stats import (
    effective_model_preference_hint_mode,
    preference_hint_for_model,
    resolve_model_preference_hint_mode,
)

_KIND_LABELS = {
    "thinking_risk": "Thinking",
    "ocr_oriented": "OCR-oriented",
    "recommended_vlm": "Recommended VLM",
    "general_vlm": "General VLM",
    "text": "Text",
    "unknown": "Unknown",
}


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
        return f"Identity: verified ({short}). Matching fingerprints can skip re-OCR."
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
        if "embedding" in caps or "embed" in caps:
            return "text"
        if "completion" in caps or "chat" in caps:
            return "text"
    lower = (name or "").lower()
    if any(tok in lower for tok in ("llava", "vision", "ocr", "moondream", "minicpm-v")):
        return "vision"
    return "text"


def _is_embedding_model(info: ModelInfo) -> bool:
    if info.capability_known:
        caps = {c.lower() for c in info.capabilities}
        if caps.intersection({"embedding", "embed"}):
            return True
    lower = (info.name or "").lower()
    family = (info.family or "").lower()
    return any(token in lower for token in ("embed", "embedding")) or family in {
        "clip",
        "bert",
    } or "embed" in family


def _kind_label(advice: ModelAdvice, info: ModelInfo) -> str:
    if _is_embedding_model(info):
        return "Embedding"
    return _KIND_LABELS.get(advice.kind, advice.title)


def _capability_label(info: ModelInfo) -> str:
    if not info.capability_known:
        return "unknown"
    if not info.capabilities:
        return "none"
    return ", ".join(info.capabilities)


def _notes_for_model(
    info: ModelInfo,
    *,
    role: str,
    preference_hints: Mapping[str, str] | None = None,
    preference_share_mode: str | None = None,
) -> str:
    hints = preference_hints or {}
    model_role = _role_for_model(info.name, info, role=role)
    advice = advise_model(info.name, role=model_role)
    parts: list[str] = []
    case = use_case_label(advice)
    if case:
        parts.append(case)
    mode = (
        resolve_model_preference_hint_mode(preference_share_mode)
        if preference_share_mode is not None
        else effective_model_preference_hint_mode()
    )
    hint = hints.get(info.name) or preference_hint_for_model(
        info.name,
        share_mode=mode,
    )
    if hint:
        parts.append(hint)
    if advice.warnings:
        parts.append(advice.warnings[0])
    return " · ".join(parts) if parts else "—"


def installed_models_table(
    models: Sequence[ModelInfo],
    *,
    role: str = "all",
    preference_hints: Mapping[str, str] | None = None,
    preference_share_mode: str | None = None,
) -> dict[str, list[str]]:
    """Column-oriented table data for every installed Ollama tag."""
    hints = preference_hints or {}
    mode = (
        resolve_model_preference_hint_mode(preference_share_mode)
        if preference_share_mode is not None
        else effective_model_preference_hint_mode()
    )
    rows_model: list[str] = []
    rows_caps: list[str] = []
    rows_kind: list[str] = []
    rows_params: list[str] = []
    rows_family: list[str] = []
    rows_size: list[str] = []
    rows_best: list[str] = []
    rows_notes: list[str] = []
    for info in models:
        model_role = _role_for_model(info.name, info, role=role)
        advice = advise_model(info.name, role=model_role)
        rows_model.append(info.name)
        rows_caps.append(_capability_label(info))
        rows_kind.append(_kind_label(advice, info))
        rows_params.append(info.parameter_size or "—")
        rows_family.append(info.family or "—")
        rows_size.append(_format_size(info.size))
        rows_best.append(use_case_label(advice) or "—")
        rows_notes.append(
            _notes_for_model(
                info,
                role=role,
                preference_hints=hints,
                preference_share_mode=mode,
            )
        )
    return {
        "Model": rows_model,
        "Capabilities": rows_caps,
        "Kind": rows_kind,
        "Parameters": rows_params,
        "Family": rows_family,
        "Size": rows_size,
        "Best for": rows_best,
        "Notes": rows_notes,
    }


def render_installed_models_table(
    models: Sequence[ModelInfo],
    *,
    role: str = "all",
    key: str = "installed_models_table",
    preference_share_mode: str | None = None,
) -> None:
    """Render the shared installed-models guidance table."""
    if not models:
        st.info(
            "No installed models to describe. Pull one with Ollama, then refresh models."
        )
        return
    st.dataframe(
        installed_models_table(
            models,
            role=role,
            preference_share_mode=preference_share_mode,
        ),
        hide_index=True,
        width="stretch",
        key=key,
    )
    st.caption(
        "Capabilities, family, parameters, and size come from the local Ollama API. "
        "Kind and notes are advisory — they do not block a selection."
    )


def _selected_model_alerts(names: Sequence[str], models: Sequence[ModelInfo], *, role: str) -> None:
    by_name = {m.name: m for m in models}
    for name in names:
        if not str(name).strip():
            continue
        info = by_name.get(name)
        model_role = _role_for_model(name, info, role=role)
        advice = advise_model(name, role=model_role)
        if advice.kind == "general_vlm":
            st.warning(
                f"`{name}` is a general vision-language model, not an OCR model. "
                "It can hang on dense scans; prefer an OCR-oriented model, "
                "especially as the first compare model."
            )
        elif advice.kind == "thinking_risk":
            st.error(
                f"`{name}` is a thinking model. It often returns empty OCR text "
                "(failed / empty_output) when num_predict is consumed internally. "
                "Switch to glm-ocr, deepseek-ocr, granite3.2-vision, or qwen2.5vl."
            )


def render_model_information(
    models: Sequence[ModelInfo],
    *,
    selected: str | Sequence[str],
    role: str = "vision",
    key: str = "model_info",
    preference_share_mode: str | None = None,
) -> None:
    """Expander with the full installed-model table plus alerts for pickers."""
    names = [selected] if isinstance(selected, str) else [n for n in selected if n]
    names = [n for n in names if str(n).strip()]
    with st.expander("Model information", expanded=False):
        st.caption(chooser_caption(role))
        render_installed_models_table(
            models,
            role=role,
            key=f"{key}_table",
            preference_share_mode=preference_share_mode,
        )
        if names:
            _selected_model_alerts(names, models, role=role)


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
