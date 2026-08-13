"""Export panel UI: formats, typography, profiles, multi-notebook selection."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from transcribe.config.defaults import builtin_names_for
from transcribe.config.errors import ConfigError
from transcribe.config.facade import clear_config_cache, get_config, reload_config
from transcribe.config.models import ProfileActivations, deep_merge_dict
from transcribe.config.persistence import (
    load_workspace_settings,
    save_workspace_settings,
)
from transcribe.config.profiles import list_user_profile_names, load_profile_overlay
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.archive import ArchiveService
from transcribe.services.export import EpubDependencyError, ExportService
from transcribe.services.export_options import (
    EXPORT_FORMATS,
    ExportOptions,
    ExportTypography,
)
from transcribe.services.project import ProjectService, open_project_paths


def _path_read(path: Path) -> bytes:
    return path.read_bytes()


def render_export_panel(
    runtime: RuntimePaths,
    paths,
    projects: ProjectService,
    project,
    root: str,
    archive: ArchiveService | None = None,
) -> None:
    view = get_config()
    export_cfg = view.effective.export
    active_profile = view.effective.activations.export

    builtins = list(builtin_names_for("export"))
    users = list_user_profile_names("export")
    profile_names = builtins + [n for n in users if n not in builtins]
    idx = profile_names.index(active_profile) if active_profile in profile_names else 0

    col_a, col_b = st.columns(2)
    with col_a:
        chosen_profile = st.selectbox(
            "Export profile",
            profile_names,
            index=idx,
            key="export_profile_select",
        )
    with col_b:
        if st.button("Activate profile", key="export_profile_activate"):
            try:
                loaded = load_workspace_settings()
                load_profile_overlay("export", chosen_profile)
                acts = ProfileActivations(
                    workflow=loaded.activations.workflow,
                    ocr=loaded.activations.ocr,
                    llm=loaded.activations.llm,
                    export=chosen_profile,
                )
                save_workspace_settings(config=loaded.config, activations=acts)
                clear_config_cache()
                reload_config()
                st.success(f"Activated export/{chosen_profile}")
                st.rerun()
            except ConfigError as exc:
                st.error(f"{exc.code}: {exc}")

    # Seed widget defaults from effective export config once per profile.
    seed_key = f"_export_opts_seeded_{active_profile}"
    if seed_key not in st.session_state:
        st.session_state["export_formats"] = list(export_cfg.formats)
        st.session_state["export_page_breaks"] = export_cfg.page_breaks
        st.session_state["export_include_dates"] = export_cfg.include_dates
        st.session_state["export_include_blank"] = export_cfg.include_blank_pages
        st.session_state["export_title_page"] = export_cfg.title_page
        st.session_state["export_body_font"] = export_cfg.typography.body_font
        st.session_state["export_body_size"] = float(export_cfg.typography.body_size_pt)
        st.session_state["export_line_height"] = float(
            export_cfg.typography.line_height
        )
        st.session_state["export_para_spacing"] = float(
            export_cfg.typography.paragraph_spacing_em
        )
        st.session_state["export_margin"] = float(export_cfg.typography.margin_in)
        st.session_state["export_heading_scale"] = float(
            export_cfg.typography.heading_scale
        )
        st.session_state[seed_key] = True

    st.markdown("#### Formats")
    formats = st.multiselect(
        "Include formats",
        list(EXPORT_FORMATS),
        key="export_formats",
    )

    st.markdown("#### Structure")
    c1, c2, c3 = st.columns(3)
    with c1:
        page_breaks = st.selectbox(
            "Page breaks",
            ["per_page", "continuous"],
            key="export_page_breaks",
        )
    with c2:
        include_dates = st.checkbox(
            "Include dates",
            key="export_include_dates",
        )
        title_page = st.checkbox(
            "Title page",
            key="export_title_page",
        )
    with c3:
        include_blank = st.checkbox(
            "Include blank pages",
            key="export_include_blank",
        )

    st.markdown("#### Typography")
    t1, t2, t3 = st.columns(3)
    with t1:
        body_font = st.selectbox(
            "Body font",
            ["serif", "sans", "mono"],
            key="export_body_font",
        )
        body_size = st.number_input(
            "Body size (pt)",
            min_value=8.0,
            max_value=28.0,
            step=0.5,
            key="export_body_size",
        )
    with t2:
        line_height = st.number_input(
            "Line height",
            min_value=1.0,
            max_value=3.0,
            step=0.05,
            key="export_line_height",
        )
        para_spacing = st.number_input(
            "Paragraph spacing (em)",
            min_value=0.0,
            max_value=3.0,
            step=0.05,
            key="export_para_spacing",
        )
    with t3:
        margin = st.number_input(
            "Margin (inches)",
            min_value=0.25,
            max_value=2.0,
            step=0.05,
            key="export_margin",
        )
        heading_scale = st.number_input(
            "Heading scale",
            min_value=1.0,
            max_value=2.5,
            step=0.05,
            key="export_heading_scale",
        )

    if st.button("Save as workspace export defaults", key="export_save_workspace"):
        try:
            loaded = load_workspace_settings()
            cfg = deep_merge_dict({}, loaded.config)
            cfg["export"] = ExportOptions(
                formats=frozenset(formats) if formats else frozenset(EXPORT_FORMATS),  # type: ignore[arg-type]
                page_breaks=page_breaks,  # type: ignore[arg-type]
                include_dates=include_dates,
                include_blank_pages=include_blank,
                title_page=title_page,
                typography=ExportTypography(
                    body_font=body_font,  # type: ignore[arg-type]
                    body_size_pt=float(body_size),
                    line_height=float(line_height),
                    paragraph_spacing_em=float(para_spacing),
                    margin_in=float(margin),
                    heading_scale=float(heading_scale),
                ),
            ).as_dict()
            acts = loaded.activations
            if acts.export != "default":
                acts = ProfileActivations(
                    workflow=acts.workflow,
                    ocr=acts.ocr,
                    llm=acts.llm,
                    export="default",
                )
            save_workspace_settings(config=cfg, activations=acts)
            clear_config_cache()
            reload_config()
            st.success("Saved export defaults (detached to default profile).")
            st.rerun()
        except ConfigError as exc:
            st.error(f"{exc.code}: {exc}")

    st.markdown("#### Notebooks")
    scope = st.radio(
        "Scope",
        ["This notebook", "Multiple notebooks"],
        horizontal=True,
        key="export_scope",
    )
    selected_roots: list[str] = [root]
    if scope == "Multiple notebooks":
        if archive is None:
            st.warning("Archive service unavailable; exporting the open notebook only.")
        else:
            notebooks = archive.list_notebooks(order="newest")
            labels = {
                str(nb.root.expanduser().resolve()): f"{nb.title or nb.root.name}"
                for nb in notebooks
            }
            options = list(labels.keys())
            default = [root] if root in options else options[:1]
            selected_roots = st.multiselect(
                "Include notebooks (order = anthology order)",
                options,
                default=default,
                format_func=lambda r: labels.get(r, r),
                key="export_multi_roots",
            )
            if not selected_roots:
                st.caption("Select at least one notebook.")

    export_dest = st.text_input(
        "Export directory",
        value=str(runtime.export_dir / Path(root).name),
        key="export_dest",
    )

    if st.button("Export", type="primary", key="export_run"):
        if not formats:
            st.error("Select at least one format.")
            return
        if not selected_roots:
            st.error("Select at least one notebook.")
            return
        opts = ExportOptions(
            formats=frozenset(formats),  # type: ignore[arg-type]
            page_breaks=page_breaks,  # type: ignore[arg-type]
            include_dates=include_dates,
            include_blank_pages=include_blank,
            title_page=title_page,
            typography=ExportTypography(
                body_font=body_font,  # type: ignore[arg-type]
                body_size_pt=float(body_size),
                line_height=float(line_height),
                paragraph_spacing_em=float(para_spacing),
                margin_in=float(margin),
                heading_scale=float(heading_scale),
            ),
        )
        dest = Path(export_dest) if export_dest.strip() else None
        try:
            snapshots = []
            n = len(selected_roots)
            bar = st.progress(0.0, text="Preparing export…")
            status = st.empty()
            for i, nb_root in enumerate(selected_roots):
                label = Path(nb_root).name
                status.caption(f"Reading `{label}`…")
                bar.progress(
                    min(1.0, i / max(n + 1, 1)),
                    text=f"Reading notebook {i + 1}/{n} · {label}",
                )
                nb_paths = open_project_paths(Path(nb_root))
                nb_projects = ProjectService(
                    nb_paths, clock=SystemClock(), ids=UuidGenerator()
                )
                snapshots.append(
                    ExportService.capture_snapshot_at(nb_paths, nb_projects)
                )
            bar.progress(
                min(1.0, n / max(n + 1, 1)),
                text="Writing export files…",
            )
            status.caption("Writing export files…")
            service = ExportService(paths, projects)
            written = service.export_snapshots(snapshots, dest_dir=dest, options=opts)
            bar.progress(1.0, text="Export complete")
            rev = ""
            from transcribe.persistence.atomic import read_json

            manifest = read_json(written["manifest"])
            rev = str(
                manifest.get("bundle_revision")
                or manifest.get("content_revision")
                or ""
            )
            if rev:
                st.success(f"Exported revision `{rev[:16]}…`")
            for kind, path in written.items():
                st.write(f"**{kind}:** `{path}`")
            st.session_state["_export_written"] = {
                k: str(v) for k, v in written.items()
            }
        except EpubDependencyError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Export failed: {exc}")

    written = st.session_state.get("_export_written") or {}
    if written:
        st.markdown("#### Downloads")
        for kind, path_str in written.items():
            if kind == "manifest":
                continue
            path = Path(path_str)
            if not path.is_file():
                continue
            st.download_button(
                f"Download {path.name}",
                data=_path_read(path),
                file_name=path.name,
                key=f"export_dl_{kind}",
            )

    st.divider()
    st.subheader("Fine-tune dataset")
    st.caption(
        "Export page images + preferred/active text for **external** training. "
        "See docs/finetune_export.md — Transcribe does not train models."
    )
    ft_require = st.checkbox("Require preferred attempt", key="ft_require_pref")
    ft_rejected = st.checkbox("Include rejected vision candidates", key="ft_rejected")
    ft_no_edited = st.checkbox("Skip pages with human edits", key="ft_no_edited")
    ft_hardlink = st.checkbox("Hardlink images when possible", key="ft_hardlink")
    if st.button("Export fine-tune package", key="ft_export_btn"):
        from transcribe.services.finetune_export import (
            FinetuneExportOptions,
            FinetuneExportService,
        )

        try:
            out = FinetuneExportService(paths, projects).export(
                options=FinetuneExportOptions(
                    include_edited_pages=not ft_no_edited,
                    require_preferred=ft_require,
                    include_rejected_candidates=ft_rejected,
                    image_mode="hardlink" if ft_hardlink else "copy",
                )
            )
            st.success(f"Wrote `{out}`")
            st.session_state["_finetune_export_dir"] = str(out)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Fine-tune export failed: {exc}")


def render_export_settings_panel() -> None:
    """Settings hub subsection for export defaults."""
    st.subheader("Export defaults")
    st.caption(
        "Workspace defaults and export profiles (readable / compact / large_print). "
        "The Workflow → Export panel applies these and can override per run."
    )
    view = get_config()
    cfg = view.effective.export
    st.json(cfg.as_dict())
    st.caption(f"Active export profile: `{view.effective.activations.export}`")
