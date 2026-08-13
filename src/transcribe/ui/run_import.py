"""Import page — This notebook | Batch (TranscriptX Target pattern)."""

from __future__ import annotations

import streamlit as st

from transcribe.config.facade import get_config
from transcribe.errors import TranscribeError
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.archive import bump_archive_generation
from transcribe.ui.import_inbox import render_import_inbox
from transcribe.ui.targets import (
    IMPORT_TARGET_KEY,
    PENDING_IMPORT_TARGET_KEY,
    TARGET_BATCH,
    TARGET_OPTIONS,
    TARGET_THIS,
    apply_pending_target,
    normalize_target,
)


def render_run_import(
    runtime: RuntimePaths,
    *,
    root: str | None,
    projects,
    ingest,
    project,
) -> None:
    apply_pending_target(
        st.session_state,
        pending_key=PENDING_IMPORT_TARGET_KEY,
        target_key=IMPORT_TARGET_KEY,
    )
    normalize_target(st.session_state, IMPORT_TARGET_KEY)
    target = st.segmented_control(
        "Target",
        options=list(TARGET_OPTIONS),
        key=IMPORT_TARGET_KEY,
        help=(
            "This notebook: add JPEG/PNG/PDF files to the selected notebook. "
            "Batch: import a folder or parent of folders into the corpus."
        ),
    )
    if target is None:
        target = st.session_state.get(IMPORT_TARGET_KEY) or TARGET_THIS

    if target == TARGET_BATCH:
        render_import_inbox(runtime)
        return

    if project is None or projects is None or ingest is None:
        st.info(
            "Select a notebook above, or create one under Workflow → New notebook."
        )
        return

    flash = st.session_state.pop("import_flash", None)
    if flash:
        st.success(flash)
    for err in st.session_state.pop("import_errors", []) or []:
        st.error(err)

    uploaded = st.file_uploader(
        "JPEG / PNG / PDF",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True,
    )
    dpi = int(get_config().effective.ingest.render_dpi)
    declutter = bool(get_config().effective.ingest.visual_declutter_enabled)
    st.caption(
        f"PDF render DPI: **{dpi}** · Visual declutter: "
        f"**{'on' if declutter else 'off'}** "
        "(Settings → Configuration)"
    )
    if st.button("Import files") and uploaded:
        total = len(uploaded)
        bar = st.progress(0.0, text=f"Importing 0/{total}")
        status = st.empty()
        ok = 0
        errors: list[str] = []
        for i, f in enumerate(uploaded):
            status.caption(f"Importing `{f.name}`…")
            try:
                project = ingest.import_bytes(
                    f.name, f.getvalue(), render_dpi=dpi
                )
                bump_archive_generation(runtime)
                ok += 1
            except TranscribeError as exc:
                errors.append(f"{f.name}: {exc}")
            done = i + 1
            bar.progress(
                min(1.0, done / total),
                text=f"Importing {done}/{total}",
            )
        if ok:
            st.session_state["import_flash"] = (
                f"Imported {ok} file{'s' if ok != 1 else ''}"
                + (f" ({len(errors)} failed)" if errors else "")
            )
        if errors:
            st.session_state["import_errors"] = errors
        st.rerun()
    st.write(f"Pages in notebook: **{len(project.pages)}**")
    title_key = f"import_notebook_title__{project.id}"
    if title_key not in st.session_state:
        st.session_state[title_key] = project.title or ""
    title_in = st.text_input(
        "Notebook name",
        key=title_key,
        help="Display title for this notebook. The notebook folder path is unchanged.",
    )
    if st.button("Save notebook name"):
        cleaned = title_in.strip()
        if not cleaned:
            st.error("Notebook name cannot be empty.")
        else:
            project = projects.update_notebook_metadata(title=cleaned)
            bump_archive_generation(runtime)
            st.success("Notebook name saved")
    tags_in = st.text_input(
        "Notebook tags (comma-separated)", value=", ".join(project.tags)
    )
    if st.button("Save notebook tags"):
        project = projects.update_notebook_metadata(
            tags=[t for t in tags_in.split(",")]
        )
        bump_archive_generation(runtime)
        st.success("Tags saved")
