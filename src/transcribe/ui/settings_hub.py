"""Settings → Profiles / Models / Configuration panels (workspace knobs)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from transcribe.config.apply_ocr import preview_apply_ocr, apply_ocr_patch
from transcribe.config.defaults import builtin_names_for
from transcribe.config.errors import ConfigError
from transcribe.config.facade import clear_config_cache, get_config, reload_config
from transcribe.config.gui_support import COMMON_SETTINGS_SCHEMA
from transcribe.config.models import PROFILE_TARGETS, ProfileActivations, deep_merge_dict
from transcribe.config.persistence import load_workspace_settings, save_workspace_settings
from transcribe.config.profiles import (
    list_user_profile_names,
    save_user_profile,
    validate_profile_name,
)
from transcribe.config.reset import (
    reset_profile_activation,
    reset_whole_workspace,
)
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import build_runtime_paths
from transcribe.services.project import ProjectService, open_project_paths
from pathlib import Path


def render_configuration_panel() -> None:
    st.subheader("Configuration")
    view = get_config()
    if view.readonly_recovery:
        st.error(
            f"Workspace settings unreadable ({view.recovery_code}). "
            "Use Reset workspace below."
        )

    runtime = build_runtime_paths()
    st.markdown("#### Folders")
    st.caption("Set via environment / Docker mounts; not editable here.")
    st.caption(f"Notebooks: `{runtime.projects_dir}`")
    st.caption(f"Inbox: `{runtime.inbox_dir}`")
    st.caption(f"Exports: `{runtime.export_dir}`")

    st.divider()
    st.markdown("#### Import")
    st.caption("Used when importing PDFs and images (Workflow → Import).")
    dpi = st.number_input(
        "PDF render DPI",
        min_value=72,
        max_value=600,
        value=int(view.effective.ingest.render_dpi),
        key="settings_ingest_render_dpi",
    )
    declutter = st.checkbox(
        "Visual declutter (remove scanner borders on import)",
        value=bool(view.effective.ingest.visual_declutter_enabled),
        key="settings_ingest_visual_declutter",
        help="On by default. Affects new imports only; existing notebooks are not rewritten.",
    )
    if st.button("Save import defaults", type="primary", key="settings_ingest_save"):
        try:
            loaded = load_workspace_settings()
            cfg = deep_merge_dict({}, loaded.config)
            ingest_cfg = cfg.setdefault("ingest", {})
            ingest_cfg["render_dpi"] = int(dpi)
            ingest_cfg["visual_declutter_enabled"] = bool(declutter)
            save_workspace_settings(config=cfg, activations=loaded.activations)
            clear_config_cache()
            reload_config()
            st.success("Saved.")
            st.rerun()
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")

    st.divider()
    st.caption("Curated knobs (effective values). Edit via Analysis / Models / Profiles.")
    for field in COMMON_SETTINGS_SCHEMA:
        parts = field.key.split(".")
        cur: Any = view.effective
        try:
            if parts[0] == "ocr":
                cur = getattr(view.effective.ocr, parts[1])
            elif parts[0] == "llm":
                cur = getattr(view.effective.llm, parts[1])
            elif parts[0] == "ingest":
                cur = getattr(view.effective.ingest, parts[1])
            elif parts[0] == "analysis":
                sub = getattr(view.effective.analysis, parts[1])
                cur = getattr(sub, parts[2]) if len(parts) > 2 else sub
            else:
                cur = None
        except Exception:  # noqa: BLE001
            cur = None
        src = view.provenance.get(field.key, "?")
        st.text(f"{field.group} · {field.label}: {cur}  ({src})")

    with st.expander("Provenance (diagnostics)"):
        st.json(view.provenance)

    if st.button("Reset whole workspace settings", key="settings_reset_workspace"):
        try:
            reset_whole_workspace()
            clear_config_cache()
            st.success("Workspace settings archived and reset to defaults.")
            st.rerun()
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")


def render_models_panel() -> None:
    st.subheader("Models & LLM budgets")
    view = get_config()
    ocr = view.effective.ocr
    llm = view.effective.llm
    st.caption(
        "Workspace OCR URL seeds new notebooks only. Open-notebook URL is independent "
        "until you Apply or save on Workflow → Transcribe."
    )
    base_url = st.text_input("Workspace Ollama base URL", value=ocr.base_url or "")
    text_pref = st.text_input(
        "Preferred text model (workspace hint)",
        value=llm.text_model_preference or "",
    )
    num_predict = st.number_input(
        "num_predict", min_value=64, max_value=8192, value=int(llm.num_predict)
    )
    max_unit = st.number_input(
        "max_unit_tokens", min_value=100, max_value=8000, value=int(llm.max_unit_tokens)
    )
    max_prompt = st.number_input(
        "max_prompt_tokens",
        min_value=500,
        max_value=32000,
        value=int(llm.max_prompt_tokens),
    )
    if st.button("Save model defaults", type="primary", key="settings_models_save"):
        try:
            loaded = load_workspace_settings()
            cfg = deep_merge_dict({}, loaded.config)
            cfg.setdefault("ocr", {})["base_url"] = base_url.strip()
            cfg.setdefault("llm", {}).update(
                {
                    "text_model_preference": text_pref.strip(),
                    "num_predict": int(num_predict),
                    "max_unit_tokens": int(max_unit),
                    "max_prompt_tokens": int(max_prompt),
                }
            )
            acts = loaded.activations
            if acts.llm != "default" or acts.ocr != "default":
                acts = ProfileActivations(
                    workflow=acts.workflow,
                    ocr="default",
                    llm="default",
                    export=acts.export,
                )
            save_workspace_settings(config=cfg, activations=acts)
            clear_config_cache()
            reload_config()
            st.success("Saved.")
            st.rerun()
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")

    st.divider()
    st.markdown("#### Apply OCR defaults to open notebook")
    root = st.session_state.get("root")
    if not root:
        st.caption("Select a notebook to apply.")
        return
    try:
        paths = open_project_paths(Path(root))
        projects = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
        project = projects.load(reconcile=False)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not load notebook: {exc}")
        return
    plan = preview_apply_ocr(project.settings, view.effective.ocr)
    changed = plan.changed
    if not changed:
        st.caption("No differences between workspace OCR defaults and notebook settings.")
        return
    st.json({k: {"from": a, "to": b} for k, (a, b) in changed.items()})
    if st.button("Apply allowlisted OCR fields to open notebook", key="settings_apply_ocr"):
        try:
            new_settings = apply_ocr_patch(project.settings, plan)
            projects.save_settings(project, new_settings)
            clear_config_cache()
            st.success("Applied OCR patch to project.json.")
            st.rerun()
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")


def render_profiles_panel() -> None:
    st.subheader("Profiles")
    st.caption(
        "Activation pointer + resolve-time overlay. Editing profile-supplied values "
        "in other tabs detaches to default and writes workspace overrides."
    )
    target = st.selectbox("Target", list(PROFILE_TARGETS), key="settings_profile_target")
    builtins = list(builtin_names_for(target))  # type: ignore[arg-type]
    users = list_user_profile_names(target)  # type: ignore[arg-type]
    names = builtins + [n for n in users if n not in builtins]
    view = get_config()
    current = getattr(view.effective.activations, target)
    idx = names.index(current) if current in names else 0
    chosen = st.selectbox("Active profile", names, index=idx, key="settings_profile_active")
    if st.button("Activate", key="settings_profile_activate"):
        try:
            loaded = load_workspace_settings()
            acts = ProfileActivations(
                workflow=chosen if target == "workflow" else loaded.activations.workflow,
                ocr=chosen if target == "ocr" else loaded.activations.ocr,
                llm=chosen if target == "llm" else loaded.activations.llm,
                export=chosen if target == "export" else loaded.activations.export,
            )
            # Ensure profile resolves
            from transcribe.config.profiles import load_profile_overlay

            load_profile_overlay(target, chosen)  # type: ignore[arg-type]
            save_workspace_settings(config=loaded.config, activations=acts)
            clear_config_cache()
            st.success(f"Activated {target}/{chosen}")
            st.rerun()
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")

    if st.button("Reset activation to default", key="settings_profile_reset_act"):
        try:
            reset_profile_activation(target)
            clear_config_cache()
            st.success("Activation reset to default.")
            st.rerun()
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")

    st.divider()
    new_name = st.text_input("Save As name", key="settings_profile_save_as_name")
    if st.button("Save As (current effective subtree)", key="settings_profile_save_as"):
        try:
            name = validate_profile_name(new_name, for_save_as=True)
            eff = get_config().effective
            if target == "workflow":
                config = {"analysis": {"ui_presets": eff.analysis.ui_presets.as_dict()}}
            elif target == "ocr":
                config = {"ocr": eff.ocr.as_dict()}
            elif target == "export":
                config = {"export": eff.export.as_dict()}
            else:
                config = {"llm": eff.llm.as_dict()}
            save_user_profile(target, name, config, overwrite=False)  # type: ignore[arg-type]
            st.success(f"Saved user profile {target}/{name}")
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")
