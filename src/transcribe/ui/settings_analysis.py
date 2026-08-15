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
from transcribe.ui.components.info_tooltip import widget_help
from transcribe.config.reset import reset_subtree

_PRESET_KEYS = ("quick", "balanced", "thorough")
_PRESET_TITLES = {"quick": "Quick", "balanced": "Balanced", "thorough": "Thorough"}


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


def render_analysis_presets_panel() -> None:
    """Edit Quick / Balanced / Thorough policies; save to workspace settings."""
    st.subheader("Analysis presets")
    st.caption(
        "Defines what Quick, Balanced, and Thorough include when you launch analysis. "
        "Workflow → Analyse still chooses which preset to use. "
        "Custom on that page remains a one-off module picker."
    )

    catalogue = _catalogue()
    llm_options = _llm_ids(catalogue)
    heavy_options = _heavy_ids(catalogue)

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

    tabs = st.tabs([_PRESET_TITLES[k] for k in _PRESET_KEYS])
    for tab, key in zip(tabs, _PRESET_KEYS):
        with tab:
            _render_preset_editor(
                key,
                draft_root[key],
                catalogue=catalogue,
                llm_options=llm_options,
                heavy_options=heavy_options,
                gen=gen,
            )

    col_save, col_reset = st.columns(2)
    with col_save:
        save = st.button(
            "Save presets",
            type="primary",
            key="settings_ui_presets_save",
            disabled=view.readonly_recovery,
        )
    with col_reset:
        reset = st.button("Reset presets subtree", key="settings_ui_presets_reset")

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
