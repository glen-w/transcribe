"""Settings → Analysis presets panel (TX-shaped policy knobs)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from transcribe.analysis.module_catalog import (
    format_module_label,
    is_heavy_module,
    list_catalog_modules,
)
from transcribe.analysis.presets import bump_preset_content_versions
from transcribe.config.errors import ConfigError
from transcribe.config.facade import clear_config_cache, get_config, reload_config
from transcribe.config.models import (
    ProfileActivations,
    UiPresetsConfig,
    deep_merge_dict,
)
from transcribe.config.persistence import (
    load_workspace_settings,
    save_workspace_settings,
)
from transcribe.ui import icons as ic
from transcribe.ui.components.info_tooltip import widget_help  # noqa: F401
from transcribe.config.reset import reset_subtree

_PRESET_KEYS = ("quick", "balanced", "thorough")
_PRESET_TITLES = {"quick": "Quick", "balanced": "Balanced", "thorough": "Thorough"}
_PRESET_TAB_KEY = "settings_ui_presets_selected"


def _catalogue() -> list[str]:
    return [info.module_id for info in list_catalog_modules()]


def _llm_ids(catalogue: list[str]) -> list[str]:
    out: list[str] = []
    for mid in catalogue:
        info = next((i for i in list_catalog_modules() if i.module_id == mid), None)
        if info is not None and info.requires_llm:
            out.append(mid)
    return out


def _heavy_ids(catalogue: list[str]) -> list[str]:
    out: list[str] = []
    for info in list_catalog_modules():
        if info.module_id in catalogue and is_heavy_module(info):
            out.append(info.module_id)
    return out


def _seed_draft() -> dict[str, dict[str, Any]]:
    view = get_config()
    return view.effective.analysis.ui_presets.as_dict()


def _render_preset_editor(
    preset_key: str,
    draft: dict[str, Any],
    *,
    catalogue: list[str],
    llm_options: list[str],
    heavy_options: list[str],
    detector_options: list[str],
    gen: int,
) -> None:
    title = _PRESET_TITLES[preset_key]
    st.markdown(f"#### {title}")
    prefix = f"settings_ui_presets_{gen}_{preset_key}"

    draft["allow_llm"] = st.checkbox(
        "Allow LLM modules",
        value=bool(draft.get("allow_llm")),
        key=f"{prefix}_allow_llm",
    )
    if draft["allow_llm"]:
        draft["llm_module_ids"] = st.multiselect(
            "LLM allowlist (empty = all LLM modules)",
            options=llm_options,
            default=[m for m in (draft.get("llm_module_ids") or []) if m in llm_options],
            format_func=format_module_label,
            key=f"{prefix}_llm_ids",
        )
    else:
        draft["llm_module_ids"] = list(draft.get("llm_module_ids") or [])

    draft["allow_heavy"] = st.checkbox(
        "Allow heavy modules",
        value=bool(draft.get("allow_heavy")),
        key=f"{prefix}_allow_heavy",
        help=widget_help("Heavy = registry cost_tier or category marked heavy."),
    )
    if draft["allow_heavy"]:
        draft["heavy_module_ids"] = st.multiselect(
            "Heavy allowlist (empty = all heavy modules)",
            options=heavy_options,
            default=[m for m in (draft.get("heavy_module_ids") or []) if m in heavy_options],
            format_func=format_module_label,
            key=f"{prefix}_heavy_ids",
        )
    else:
        draft["heavy_module_ids"] = list(draft.get("heavy_module_ids") or [])

    draft["include_excluded_from_default"] = st.checkbox(
        "Include exclude-from-default modules",
        value=bool(draft.get("include_excluded_from_default")),
        key=f"{prefix}_excl",
    )

    draft["allow_detection"] = st.checkbox(
        "Include Detect suite",
        value=bool(draft.get("allow_detection")),
        key=f"{prefix}_allow_detection",
        help=widget_help(
            "When enabled, Analyse runs selected detectors after modules "
            "(publishes under detection/)."
        ),
    )
    if draft["allow_detection"]:
        from transcribe.ui.module_ui_groups import format_detector_label

        draft["detector_ids"] = st.multiselect(
            "Detector allowlist (empty = all detectors)",
            options=detector_options,
            default=[
                d for d in (draft.get("detector_ids") or []) if d in detector_options
            ],
            format_func=format_detector_label,
            key=f"{prefix}_detector_ids",
        )
    else:
        draft["detector_ids"] = list(draft.get("detector_ids") or [])

    use_override = st.checkbox(
        "Override with explicit module list",
        value=draft.get("module_ids") is not None,
        key=f"{prefix}_use_override",
        help=widget_help("When enabled, policy filters are ignored and only this list runs."),
    )
    if use_override:
        current = list(draft.get("module_ids") or [])
        draft["module_ids"] = st.multiselect(
            "Module override",
            options=catalogue,
            default=[m for m in current if m in catalogue],
            format_func=format_module_label,
            key=f"{prefix}_override",
        )
    else:
        draft["module_ids"] = None


@st.fragment
def render_analysis_presets_panel() -> None:
    """Edit Quick / Balanced / Thorough policies; save to workspace settings."""
    st.subheader("Analysis presets")
    st.caption(
        "Defines what Quick, Balanced, and Thorough include when you launch analysis. "
        "Workflow → Analyse still chooses which preset to use. "
        "Custom on that page remains a one-off module and detector picker."
    )

    catalogue = _catalogue()
    llm_options = _llm_ids(catalogue)
    heavy_options = _heavy_ids(catalogue)
    from transcribe.analysis.presets import suitable_detector_ids

    detector_options = list(suitable_detector_ids())

    if "settings_ui_presets_draft" not in st.session_state:
        st.session_state["settings_ui_presets_draft"] = _seed_draft()
    if "settings_ui_presets_gen" not in st.session_state:
        st.session_state["settings_ui_presets_gen"] = 0

    draft_root: dict[str, dict[str, Any]] = st.session_state["settings_ui_presets_draft"]
    gen = int(st.session_state["settings_ui_presets_gen"])

    view = get_config()
    if view.readonly_recovery:
        st.error(
            f"Workspace settings unreadable ({view.recovery_code}): "
            f"{view.recovery_message}. Saves disabled until Reset workspace."
        )

    # Detach notice when workflow profile is active
    if view.effective.activations.workflow != "default":
        st.info(
            f"Active workflow profile: `{view.effective.activations.workflow}`. "
            "Saving preset edits will detach to `default` and write workspace overrides."
        )

    titles = [_PRESET_TITLES[k] for k in _PRESET_KEYS]
    title_to_key = {title: key for key, title in _PRESET_TITLES.items()}
    selected_title = st.session_state.get(_PRESET_TAB_KEY)
    if selected_title not in titles:
        st.session_state[_PRESET_TAB_KEY] = titles[0]
    label = st.segmented_control(
        "Preset",
        options=titles,
        key=_PRESET_TAB_KEY,
        label_visibility="collapsed",
    )
    if label not in title_to_key:
        label = titles[0]
        st.session_state[_PRESET_TAB_KEY] = label
    key = title_to_key[label]
    _render_preset_editor(
        key,
        draft_root[key],
        catalogue=catalogue,
        llm_options=llm_options,
        heavy_options=heavy_options,
        detector_options=detector_options,
        gen=gen,
    )

    col_save, col_reset = st.columns(2)
    with col_save:
        save = st.button(
            "Save presets",
            type="primary",
            key="settings_ui_presets_save",
            disabled=view.readonly_recovery,
            icon=ic.SAVE,
        )
    with col_reset:
        reset = st.button("Reset presets subtree", key="settings_ui_presets_reset", icon=ic.RESET)

    if reset:
        try:
            reset_subtree("analysis.ui_presets")
            clear_config_cache()
            st.session_state["settings_ui_presets_draft"] = _seed_draft()
            st.session_state["settings_ui_presets_gen"] = gen + 1
            st.success("Reset analysis.ui_presets workspace keys.")
            st.rerun()
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")

    if save:
        try:
            loaded = load_workspace_settings()
            previous = get_config().effective.analysis.ui_presets.as_dict()
            bumped = bump_preset_content_versions(
                previous,
                {key: dict(draft_root[key]) for key in _PRESET_KEYS},
            )
            cfg = deep_merge_dict({}, loaded.config)
            cfg.setdefault("analysis", {})["ui_presets"] = bumped
            # Validate via model round-trip
            UiPresetsConfig.from_dict(cfg["analysis"]["ui_presets"])
            acts = loaded.activations
            # Detach workflow profile on edit (activation-pointer ownership)
            if acts.workflow != "default":
                acts = ProfileActivations(
                    workflow="default",
                    ocr=acts.ocr,
                    llm=acts.llm,
                    export=acts.export,
                )
            save_workspace_settings(config=cfg, activations=acts)
            clear_config_cache()
            reload_config()
            st.session_state["settings_ui_presets_draft"] = _seed_draft()
            st.session_state["settings_ui_presets_gen"] = gen + 1
            st.success("Saved analysis presets to workspace settings.")
            st.rerun()
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Invalid preset settings: {exc}")


@st.fragment
def render_ask_rag_panel() -> None:
    """Workspace Ask / RAG knobs (Paperful ``[rag]`` defaults)."""
    from transcribe.analysis.rag.index import lancedb_available
    from transcribe.config.models import ASK_MODES, RagConfig

    st.subheader("Ask / RAG")
    st.caption(
        "Optional retrieve-then-generate Ask. Off by default. "
        "Needs `pip install -e '.[rag]'` (Compose images already include it) and "
        "`ollama pull nomic-embed-text`. Grounded Ask stays available either way."
    )
    if not lancedb_available():
        st.warning("LanceDB is not installed in this environment — RAG Ask will report unavailable extra.")

    view = get_config()
    rag = view.effective.analysis.rag
    if view.readonly_recovery:
        st.error("Workspace settings unreadable. Saves disabled until Reset workspace.")

    enabled = st.checkbox(
        "Enable RAG Ask",
        value=rag.enabled,
        key="settings_rag_enabled",
        help=widget_help("Build a local vector index of this notebook and retrieve passages before answering."),
    )
    auto_ingest = st.checkbox(
        "Auto-rebuild index when notebook text changes",
        value=rag.auto_ingest,
        key="settings_rag_auto_ingest",
        disabled=not enabled,
    )
    mode_idx = ASK_MODES.index(rag.ask_mode) if rag.ask_mode in ASK_MODES else 0
    ask_mode = st.selectbox(
        "Default Ask mode",
        options=list(ASK_MODES),
        index=mode_idx,
        key="settings_rag_ask_mode",
        help=widget_help("Grounded = current full-notebook Ask. RAG = retrieve then generate. Both = run both."),
    )
    embed_model = st.text_input(
        "Embedding model",
        value=rag.embed_model,
        key="settings_rag_embed_model",
        disabled=not enabled,
    )
    with st.expander("Advanced RAG", expanded=False):
        top_k = st.number_input("top_k", min_value=1, value=int(rag.top_k), key="settings_rag_top_k")
        chunk_chars = st.number_input(
            "chunk_chars", min_value=200, value=int(rag.chunk_chars), key="settings_rag_chunk_chars"
        )
        chunk_overlap = st.number_input(
            "chunk_overlap", min_value=0, value=int(rag.chunk_overlap), key="settings_rag_chunk_overlap"
        )
        max_context = st.number_input(
            "max_context_chars",
            min_value=1000,
            value=int(rag.max_context_chars),
            key="settings_rag_max_context",
        )
        hybrid = st.checkbox("Hybrid vector + full-text", value=rag.hybrid, key="settings_rag_hybrid")
        batch = st.number_input(
            "embed_batch_size", min_value=1, value=int(rag.embed_batch_size), key="settings_rag_batch"
        )
        embed_base = st.text_input(
            "embed_base_url (empty = Ollama URL)",
            value=rag.embed_base_url,
            key="settings_rag_embed_base",
        )
        rag_model = st.text_input(
            "RAG chat model override (empty = Ask text model)",
            value=rag.model,
            key="settings_rag_chat_model",
        )

    col_save, col_reset = st.columns(2)
    with col_save:
        save = st.button(
            "Save Ask / RAG",
            type="primary",
            key="settings_rag_save",
            disabled=view.readonly_recovery,
            icon=ic.SAVE,
        )
    with col_reset:
        reset = st.button("Reset Ask / RAG", key="settings_rag_reset", icon=ic.RESET)

    if reset:
        try:
            reset_subtree("analysis.rag")
            clear_config_cache()
            st.success("Reset analysis.rag workspace keys.")
            st.rerun()
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")

    if save:
        try:
            loaded = load_workspace_settings()
            cfg = deep_merge_dict({}, loaded.config)
            parsed = RagConfig.from_dict(
                {
                    "enabled": enabled,
                    "auto_ingest": auto_ingest,
                    "ask_mode": ask_mode,
                    "embed_model": embed_model,
                    "top_k": int(top_k),
                    "chunk_chars": int(chunk_chars),
                    "chunk_overlap": int(chunk_overlap),
                    "max_context_chars": int(max_context),
                    "hybrid": hybrid,
                    "embed_batch_size": int(batch),
                    "embed_base_url": embed_base,
                    "model": rag_model,
                }
            )
            cfg.setdefault("analysis", {})["rag"] = parsed.as_dict()
            save_workspace_settings(config=cfg, activations=loaded.activations)
            clear_config_cache()
            reload_config()
            st.success("Saved Ask / RAG settings.")
            st.rerun()
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Invalid RAG settings: {exc}")
