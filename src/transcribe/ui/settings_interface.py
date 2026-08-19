"""Settings Interface tab: draft-backed action menu customisation.

Widget interactions run in ``@st.fragment`` so checkbox / mode toggles do not
trigger a full-app rerun. Save, Restore, and Reload still call ``st.rerun()``.

Draft→widget hydrate runs only before keyed widgets instantiate (first load or
a deferred pending-sync flag).
"""

from __future__ import annotations

import streamlit as st

from transcribe.ui import icons as ic
from transcribe.ui.action_menus.catalog import (
    ACTIONS,
    SECTION_ALLOWLISTS,
    section_default_actions,
)
from transcribe.ui.action_menus.ids import (
    SECTION_LABELS,
    SECTION_ORDER,
    ActionId,
)
from transcribe.ui.action_menus.prefs import (
    DRAFT_SESSION_KEY,
    draft_is_dirty,
    get_or_hydrate_draft,
    interface_menus_path,
    reload_draft_from_disk,
    restore_built_in_defaults,
    save_interface_prefs,
    validate_draft_for_save,
)
from transcribe.ui.components.info_tooltip import widget_help

_MODE_LABELS = {
    "use_standard": "Use standard menu",
    "section_default": "Use built-in section default",
    "manual": "Choose actions manually",
}
_MODE_OPTIONS = list(_MODE_LABELS.keys())
_PENDING_WIDGET_SYNC_KEY = "iface_pending_widget_sync"


def _sync_widgets_from_draft() -> None:
    draft = st.session_state[DRAFT_SESSION_KEY]
    prefs = draft.prefs
    st.session_state["iface_show_info_tooltips"] = bool(prefs.show_info_tooltips)
    st.session_state["iface_std_mode"] = (
        "Built-in" if prefs.standard_menu_mode == "built_in" else "Custom"
    )
    for action in ACTIONS:
        st.session_state[f"iface_std_{action.id.value}"] = action.id in prefs.standard_menu
    for sid in SECTION_ORDER:
        sec = prefs.sections[sid]
        st.session_state[f"iface_show_{sid.value}"] = sec.show_menu
        st.session_state[f"iface_mode_{sid.value}"] = sec.mode
        allow = SECTION_ALLOWLISTS[sid]
        for action_id in allow:
            st.session_state[f"iface_sel_{sid.value}_{action_id.value}"] = action_id in sec.selected


def _request_widget_sync() -> None:
    st.session_state[_PENDING_WIDGET_SYNC_KEY] = True


def _pull_widgets_into_draft() -> None:
    draft = st.session_state[DRAFT_SESSION_KEY]
    prefs = draft.prefs
    prefs.show_info_tooltips = bool(st.session_state.get("iface_show_info_tooltips", True))
    std_mode = st.session_state.get("iface_std_mode", "Built-in")
    prefs.standard_menu_mode = "built_in" if std_mode == "Built-in" else "custom"
    selected_std: list[ActionId] = []
    for action in ACTIONS:
        if st.session_state.get(f"iface_std_{action.id.value}", False):
            selected_std.append(action.id)
    prefs.standard_menu = selected_std

    for sid in SECTION_ORDER:
        sec = prefs.sections[sid]
        sec.show_menu = bool(st.session_state.get(f"iface_show_{sid.value}", True))
        mode = st.session_state.get(f"iface_mode_{sid.value}", "section_default")
        if mode not in _MODE_OPTIONS:
            mode = "section_default"
        sec.mode = mode  # type: ignore[assignment]
        selected: list[ActionId] = []
        for action_id in SECTION_ALLOWLISTS[sid]:
            if st.session_state.get(f"iface_sel_{sid.value}_{action_id.value}", False):
                selected.append(action_id)
        sec.selected = selected


@st.fragment
def render_interface_panel() -> None:
    """Render Interface menus settings (ordinary widgets + draft session state)."""
    first = DRAFT_SESSION_KEY not in st.session_state
    draft = get_or_hydrate_draft(st.session_state, path=interface_menus_path())
    pending_sync = bool(st.session_state.pop(_PENDING_WIDGET_SYNC_KEY, False))
    if first or pending_sync:
        _sync_widgets_from_draft()

    st.subheader("Action menus")
    st.caption(
        "Customise the icon-link strips on Archive notebook cards and Library "
        "notebook rows, plus Import / Transcribe / Analyse next-step strips. "
        "Changes apply after Save. "
        f"Stored at `{interface_menus_path()}`."
    )

    if draft.recovery:
        st.warning(
            draft.recovery_message
            or "Interface menus file needs recovery. Normal Save is disabled."
        )

    if draft_is_dirty(draft):
        st.caption("Unsaved changes")

    st.markdown("##### Instructional tips")
    st.caption("Show or hide instructional ⓘ tips on widgets and page-viewer notes.")
    st.checkbox(
        "Show info tooltips",
        key="iface_show_info_tooltips",
        disabled=draft.recovery,
    )

    st.markdown("##### Standard menu")
    st.radio(
        "Standard menu source",
        options=["Built-in", "Custom"],
        key="iface_std_mode",
        horizontal=True,
        help=widget_help("Built-in is Open · Transcribe · Analyse · Export."),
        disabled=draft.recovery,
    )
    if st.session_state.get("iface_std_mode") == "Custom":
        for action in ACTIONS:
            st.checkbox(
                action.label,
                key=f"iface_std_{action.id.value}",
                help=widget_help(action.help),
                disabled=draft.recovery,
            )

    st.markdown("##### Per-section menus")
    for sid in SECTION_ORDER:
        with st.expander(SECTION_LABELS[sid], expanded=False):
            show = st.checkbox(
                "Show menu",
                key=f"iface_show_{sid.value}",
                help=widget_help(
                    "When off, this section renders no action links. "
                    "Mode and selections are kept."
                ),
                disabled=draft.recovery,
            )
            default_preview = " · ".join(
                a.value for a in section_default_actions(sid, subject_type="notebook")
            )
            st.caption(f"Built-in section default: {default_preview}")

            st.radio(
                "Menu mode",
                options=_MODE_OPTIONS,
                format_func=lambda m: _MODE_LABELS[m],
                key=f"iface_mode_{sid.value}",
                disabled=draft.recovery or not show,
            )
            mode = st.session_state.get(f"iface_mode_{sid.value}")
            if mode == "manual" and show and not draft.recovery:
                for action_id in SECTION_ALLOWLISTS[sid]:
                    action = next(a for a in ACTIONS if a.id == action_id)
                    st.checkbox(
                        action.label,
                        key=f"iface_sel_{sid.value}_{action_id.value}",
                        help=widget_help(action.help),
                    )
            elif not show:
                st.caption(
                    "Menu hidden. Mode and checkbox selections are retained for when you turn Show menu back on."
                )
            else:
                st.caption(
                    "Runtime context may temporarily hide unavailable actions "
                    "(for example Open on an empty notebook) without turning the menu off."
                )

    c1, c2, c3 = st.columns(3)
    with c1:
        save_clicked = st.button(
            "Save",
            key="iface_save",
            type="primary",
            disabled=draft.recovery,
            icon=ic.SAVE,
        )
    with c2:
        restore_clicked = st.button(
            "Restore built-in defaults",
            key="iface_restore",
            help=widget_help(
                "Persist built-in defaults to disk (same conflict protection as Save)."
            ),
            icon=ic.RESTORE,
        )
    with c3:
        reload_clicked = st.button("Reload saved settings", key="iface_reload", icon=ic.REFRESH)

    if save_clicked and not draft.recovery:
        _pull_widgets_into_draft()
        err = validate_draft_for_save(draft.prefs)
        if err:
            st.error(err)
        else:
            result = save_interface_prefs(draft)
            if result.ok:
                _request_widget_sync()
                st.success("Interface menus saved.")
                st.rerun()
            elif result.conflict:
                st.error(result.error)
            else:
                st.error(result.error or "Save failed.")

    if restore_clicked:
        # Persist built-ins with CAS (including recovery replace).
        result = restore_built_in_defaults(draft)
        if result.ok:
            _request_widget_sync()
            st.success("Restored built-in interface menus (saved).")
            st.rerun()
        elif result.conflict:
            st.error(result.error)
        else:
            st.error(result.error or "Restore failed.")

    if reload_clicked:
        reload_draft_from_disk(st.session_state, path=interface_menus_path())
        _request_widget_sync()
        st.info("Reloaded saved interface menus.")
        st.rerun()


# Chrome order: Configuration + Analysis first (TX), then Transcribe-native
# Detection/Tags/Prompts, Interface before Models (TX), Profiles as a tab (not a
# System page), Export last.
SETTINGS_TABS: tuple[str, ...] = (
    "Configuration",
    "Analysis",
    "Detection",
    "Tags",
    "Prompts",
    "Interface",
    "Models",
    "Profiles",
    "Export",
)


def render_settings_page() -> None:
    """Top-level Settings hub (TX-shaped tabs, Transcribe-scoped)."""
    from transcribe.ui.export_panel import render_export_settings_panel
    from transcribe.ui.settings_analysis import render_analysis_presets_panel
    from transcribe.ui.settings_detection import render_detection_settings_panel
    from transcribe.ui.settings_hub import (
        render_configuration_panel,
        render_models_panel,
        render_profiles_panel,
    )
    from transcribe.ui.settings_prompts import render_prompts_panel
    from transcribe.ui.settings_tags import render_tags_settings_panel

    tabs = st.tabs(list(SETTINGS_TABS))
    for tab, label in zip(tabs, SETTINGS_TABS):
        with tab:
            if label == "Configuration":
                render_configuration_panel()
            elif label == "Analysis":
                render_analysis_presets_panel()
            elif label == "Detection":
                render_detection_settings_panel()
            elif label == "Tags":
                render_tags_settings_panel()
            elif label == "Prompts":
                render_prompts_panel()
            elif label == "Interface":
                st.markdown("### Interface")
                render_interface_panel()
            elif label == "Models":
                render_models_panel()
            elif label == "Profiles":
                render_profiles_panel()
            else:
                render_export_settings_panel()
