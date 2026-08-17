"""Settings → Profiles / Models / Configuration panels (workspace knobs)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from transcribe.config.apply_ocr import apply_ocr_patch, preview_apply_ocr
from transcribe.config.defaults import builtin_names_for
from transcribe.config.errors import ConfigError
from transcribe.config.facade import clear_config_cache, get_config, reload_config
from transcribe.config.gui_support import COMMON_SETTINGS_SCHEMA
from transcribe.config.models import (
    PROFILE_TARGETS,
    ProfileActivations,
    deep_merge_dict,
)
from transcribe.config.persistence import (
    load_workspace_settings,
    save_workspace_settings,
)
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
from transcribe.ui.components.info_tooltip import widget_help


@st.fragment
def render_configuration_panel() -> None:
    st.subheader("Configuration")
    view = get_config()
    if view.readonly_recovery:
        st.error(
            f"Workspace settings unreadable ({view.recovery_code}). " "Use Reset workspace below."
        )

    runtime = build_runtime_paths()
    st.markdown("#### Folders")
    st.caption("Set via environment / Docker mounts; not editable here.")
    st.caption(f"Notebooks: `{runtime.projects_dir}`")
    st.caption(f"Inbox: `{runtime.inbox_dir}`")
    st.caption(f"Exports: `{runtime.export_dir}`")

    st.divider()
    st.markdown("#### Backup")
    st.caption(
        "Full-workspace ZIP (notebooks + corpus + config). "
        "Writes under Exports → `backups/`. Restore **replaces** the current workspace. "
        "Large archives: prefer CLI (`transcribe backup create` / `transcribe restore`). "
        "Guide: docs/backup_and_restore.md."
    )
    include_inbox = st.checkbox(
        "Include inbox",
        value=False,
        key="workspace_backup_include_inbox",
        help="Also pack TRANSCRIBE_INBOX_DIR (scan dumps).",
    )
    include_exports = st.checkbox(
        "Include exports",
        value=False,
        key="workspace_backup_include_exports",
        help="Also pack TRANSCRIBE_EXPORT_DIR (skips the zip being written).",
    )
    if st.button("Create backup", key="workspace_backup_create"):
        from transcribe.errors import BackupError
        from transcribe.services.workspace_backup import (
            BackupOptions,
            WorkspaceBackupService,
            default_backup_dest,
        )

        try:
            dest = default_backup_dest(runtime)
            result = WorkspaceBackupService().create_backup(
                runtime,
                dest,
                BackupOptions(
                    include_inbox=include_inbox,
                    include_exports=include_exports,
                ),
            )
            size = result.archive_path.stat().st_size if result.archive_path.is_file() else 0
            st.success(
                f"Wrote `{result.archive_path}` "
                f"({result.notebook_count} notebooks, {result.file_count} files, {size} bytes on disk)."
            )
        except BackupError as exc:
            st.error(str(exc))

    st.markdown("##### Restore")
    st.caption(
        "Provide a path to a workspace backup ZIP on this machine. "
        "Verify or dry-run first. A real restore writes a safety ZIP, then **replaces** "
        "notebooks, corpus, and config. After restore, check System → Diagnostics."
    )
    restore_path = st.text_input(
        "Backup archive path",
        value="",
        key="workspace_backup_restore_path",
        placeholder=str(runtime.export_dir / "backups" / "transcribe-workspace-….zip"),
    )
    verify_col, dry_col = st.columns(2)
    with verify_col:
        if st.button("Verify archive", key="workspace_backup_verify"):
            from transcribe.errors import BackupError
            from transcribe.services.workspace_backup import WorkspaceBackupService

            if not restore_path.strip():
                st.error("Enter the path to a backup ZIP.")
            else:
                try:
                    result = WorkspaceBackupService().verify_backup(Path(restore_path.strip()))
                    counts = result.manifest.get("counts") or {}
                    st.success(
                        "Archive verified "
                        f"(notebooks={counts.get('notebooks')}, files={counts.get('files')})."
                    )
                    for message in result.messages:
                        st.caption(message)
                except BackupError as exc:
                    st.error(str(exc))
    with dry_col:
        if st.button("Dry-run restore", key="workspace_backup_dry_run"):
            from transcribe.errors import BackupError
            from transcribe.services.workspace_backup import WorkspaceBackupService

            if not restore_path.strip():
                st.error("Enter the path to a backup ZIP.")
            else:
                try:
                    result = WorkspaceBackupService().restore_backup(
                        runtime,
                        Path(restore_path.strip()),
                        safety=False,
                        dry_run=True,
                    )
                    st.info("Dry-run complete — no changes written.")
                    for message in result.messages:
                        st.caption(message)
                except BackupError as exc:
                    st.error(str(exc))
    restore_confirm = st.checkbox(
        "I understand this replaces notebooks, corpus, and config",
        value=False,
        key="workspace_backup_restore_confirm",
    )
    if st.button("Restore from backup", key="workspace_backup_restore"):
        from transcribe.errors import BackupError
        from transcribe.services.workspace_backup import WorkspaceBackupService

        if not restore_confirm:
            st.error("Confirm the replace checkbox before restoring.")
        elif not restore_path.strip():
            st.error("Enter the path to a backup ZIP.")
        else:
            try:
                result = WorkspaceBackupService().restore_backup(
                    runtime,
                    Path(restore_path.strip()),
                    safety=True,
                    dry_run=False,
                )
                for message in result.messages:
                    st.caption(message)
                if result.safety_archive is not None:
                    st.info(f"Safety backup: `{result.safety_archive}`")
                if result.ok:
                    st.success("Restore finished. Open System → Diagnostics to review doctor output.")
                    clear_config_cache()
                    reload_config()
                else:
                    st.error("Restore finished with corpus-doctor errors — see messages above.")
            except BackupError as exc:
                st.error(str(exc))

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
        "Visual declutter (remove scanner borders / white gutters on import)",
        value=bool(view.effective.ingest.visual_declutter_enabled),
        key="settings_ingest_visual_declutter",
        help=widget_help(
            "On by default for new imports. Use Re-apply below to crop scanner "
            "beds, stark white gutters, and residual corner wedges on an existing "
            "notebook."
        ),
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

    st.markdown("#### Re-apply visual declutter")
    st.caption(
        "Re-crop scanner beds on an existing notebook’s page images. "
        "Uses the checkbox above as the on/off switch. Does not re-run OCR."
    )
    project_roots = sorted(
        p for p in Path(runtime.projects_dir).expanduser().glob("*") if p.is_dir()
    )
    labels = [p.name for p in project_roots]
    if not labels:
        st.info("No notebooks found under the projects folder.")
    else:
        choice = st.selectbox(
            "Notebook",
            options=labels,
            key="settings_declutter_reapply_notebook",
        )
        if st.button(
            "Re-apply visual declutter",
            key="settings_declutter_reapply_run",
            type="secondary",
        ):
            root = Path(runtime.projects_dir) / choice
            try:
                paths = open_project_paths(root)
                svc = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
                bar = st.progress(0.0, text="Starting declutter…")
                status = st.empty()

                def on_progress(done: int, total: int, message: str) -> None:
                    frac = min(1.0, done / max(1, total))
                    bar.progress(
                        frac,
                        text=f"Decluttering {done}/{total}" + (f" · {message}" if message else ""),
                    )
                    if message:
                        status.caption(message)

                stats = svc.reapply_visual_declutter(
                    enabled=bool(declutter), on_progress=on_progress
                )
                st.success(
                    f"Done on **{choice}**: cropped {stats.pages_cropped}, "
                    f"noop {stats.pages_noop}, unchanged {stats.pages_unchanged}, "
                    f"errors {stats.pages_error} "
                    f"(of {stats.pages_total} pages)."
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"{type(exc).__name__}: {exc}")

    st.divider()
    st.markdown("#### Archive")
    st.caption("Archive notebook strip paging.")
    archive_initial = st.number_input(
        "Notebooks shown initially",
        min_value=0,
        value=int(view.effective.ui.archive_notebooks_initial),
        key="settings_archive_notebooks_initial",
        help=widget_help("How many notebook cards load before “Show more”. 0 shows all notebooks."),
    )
    if st.button("Save archive defaults", type="primary", key="settings_archive_save"):
        try:
            loaded = load_workspace_settings()
            cfg = deep_merge_dict({}, loaded.config)
            ui_cfg = cfg.setdefault("ui", {})
            ui_cfg["archive_notebooks_initial"] = int(archive_initial)
            save_workspace_settings(config=cfg, activations=loaded.activations)
            clear_config_cache()
            reload_config()
            st.session_state.pop("archive_strip_n", None)
            st.success("Saved.")
            st.rerun()
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")

    st.divider()
    st.markdown("#### Overview")
    st.caption("View → Overview cards. Status strip is always shown.")
    from transcribe.config.models import OVERVIEW_CARD_IDS

    _CARD_LABELS = {
        "page_metrics": "Page ink & blankness",
        "stats": "Counts",
        "lexical_diversity": "Lexical diversity",
        "understandability": "Understandability",
        "wordclouds": "Word themes",
        "ner": "People & entities",
        "sentiment": "Sentiment",
        "epistemic_markers": "Hedging & certainty",
    }
    current_cards = set(view.effective.ui.overview_cards)
    chosen: list[str] = []
    for cid in OVERVIEW_CARD_IDS:
        on = st.checkbox(
            _CARD_LABELS.get(cid, cid.replace("_", " ").title()),
            value=cid in current_cards,
            key=f"settings_overview_card_{cid}",
        )
        if on:
            chosen.append(cid)
    if st.button("Save overview cards", type="primary", key="settings_overview_cards_save"):
        try:
            loaded = load_workspace_settings()
            cfg = deep_merge_dict({}, loaded.config)
            ui_cfg = cfg.setdefault("ui", {})
            ui_cfg["overview_cards"] = list(chosen)
            save_workspace_settings(config=cfg, activations=loaded.activations)
            clear_config_cache()
            reload_config()
            st.success("Saved.")
            st.rerun()
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")

    st.divider()
    st.caption(
        "Curated knobs (effective values). Edit under Analysis (presets), "
        "Models (OCR/LLM seeds), or Profiles (named overlays). Analysis module "
        "thresholds here are display-only."
    )
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
            elif parts[0] == "ui":
                cur = getattr(view.effective.ui, parts[1])
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


_PREPROCESS_PROFILES = ("none", "gentle_contrast")


@st.fragment
def render_models_panel() -> None:
    st.subheader("Models & LLM budgets")
    view = get_config()
    ocr = view.effective.ocr
    llm = view.effective.llm
    from transcribe.ui.home import ollama_health_line

    st.caption(ollama_health_line())
    st.caption(
        "Workspace OCR URL and preprocess seed new notebooks only. "
        "Open-notebook URL is independent until you Apply or save on "
        "Workflow → Transcribe. Live model pickers stay on Transcribe / Analyse."
    )
    base_url = st.text_input("Workspace Ollama base URL", value=ocr.base_url or "")
    current_preprocess = (
        ocr.preprocess_profile if ocr.preprocess_profile in _PREPROCESS_PROFILES else "none"
    )
    preprocess = st.selectbox(
        "Preprocess profile (new notebooks)",
        list(_PREPROCESS_PROFILES),
        index=list(_PREPROCESS_PROFILES).index(current_preprocess),
        key="settings_ocr_preprocess_profile",
        help=widget_help(
            "Image preprocess for new notebooks (`none` or `gentle_contrast`). "
            "Does not rewrite an open notebook until Apply OCR below or a "
            "Transcribe save."
        ),
    )
    text_pref = st.text_input(
        "Preferred text model (workspace default)",
        value=llm.text_model_preference or "",
        help=(
            "Used for Analyse / Detect when a notebook has no text model set, "
            "and as the default pick on Batch Analyse. Also seeds new notebooks."
        ),
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
            ocr_cfg = cfg.setdefault("ocr", {})
            ocr_cfg["base_url"] = base_url.strip()
            ocr_cfg["preprocess_profile"] = str(preprocess)
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


@st.fragment
def render_profiles_panel() -> None:
    st.subheader("Profiles")
    st.caption(
        "Activation pointer + resolve-time overlay (not copied into workspace). "
        "Editing a profile-supplied value in other tabs detaches that target to "
        "`default` and writes workspace overrides. Builtins are immutable."
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
                workflow=(chosen if target == "workflow" else loaded.activations.workflow),
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
