"""Streamlit UI for Transcribe.

JobCoordinator is owned via st.cache_resource so reruns do not drop live jobs.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import streamlit as st

from transcribe.errors import JobConflictError, TranscribeError
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.providers.ollama import OllamaVisionProvider, is_loopback_host, normalize_base_url
from transcribe.services.export import ExportService
from transcribe.services.job import JobCoordinator, JobProgress, build_coordinator
from transcribe.services.project import ProjectService, open_project_paths


@st.cache_resource
def get_coordinator(project_root: str) -> JobCoordinator:
    _paths, _projects, coord, _ingest = build_coordinator(
        project_root, clock=SystemClock(), ids=UuidGenerator()
    )
    return coord


def _services(project_root: str):
    paths = open_project_paths(Path(project_root))
    clock = SystemClock()
    ids = UuidGenerator()
    projects = ProjectService(paths, clock=clock, ids=ids)
    from transcribe.ingest import IngestService

    ingest = IngestService(paths, clock=clock, ids=ids)
    return paths, projects, ingest


def _render_job_progress(progress: JobProgress) -> None:
    st.write(
        f"Job: **{progress.status}** — completed {progress.completed}/"
        f"{progress.total} (failed {progress.failed}, skipped {progress.skipped})"
    )
    if progress.current_page_ids:
        st.caption("Current page(s): " + ", ".join(p[:8] for p in progress.current_page_ids))
    if progress.message:
        st.caption(progress.message)
    if progress.status == "running":
        done = progress.completed + progress.failed
        if progress.total > 0:
            st.progress(min(1.0, done / progress.total))
        st.info(
            "OCR is running in the background. Progress also prints in the "
            "Streamlit terminal as `[transcribe] …` lines. The first page can "
            "take several minutes while Ollama loads the vision model."
        )


def main() -> None:
    st.set_page_config(page_title="Transcribe", layout="wide")
    st.title("Transcribe")
    st.caption("Local-first handwritten notebook OCR via Ollama")

    default_root = str(Path.cwd() / "notebook-project")
    root = st.sidebar.text_input("Project directory", value=st.session_state.get("root", default_root))
    st.session_state["root"] = root

    col_a, col_b = st.sidebar.columns(2)
    if col_a.button("Create"):
        try:
            paths = open_project_paths(Path(root))
            ProjectService(paths, clock=SystemClock(), ids=UuidGenerator()).create()
            st.sidebar.success("Created")
            st.cache_resource.clear()
        except TranscribeError as exc:
            st.sidebar.error(str(exc))
    if col_b.button("Open"):
        try:
            paths, projects, ingest = _services(root)
            ingest.cleanup_staging()
            projects.load(reconcile=True)
            st.sidebar.success("Opened")
            st.cache_resource.clear()
        except TranscribeError as exc:
            st.sidebar.error(str(exc))

    try:
        paths, projects, ingest = _services(root)
        project = projects.load(reconcile=True)
    except TranscribeError as exc:
        st.info("Create or open a project directory to begin.")
        st.caption(str(exc))
        return

    coord = get_coordinator(str(paths.root))
    live = coord.get_progress()
    # Track running→done so a fragment can trigger one full rerun to re-enable buttons.
    was_running = st.session_state.get("_job_was_running", False)
    st.session_state["_job_was_running"] = live.status == "running"

    tab_import, tab_run, tab_review, tab_export = st.tabs(
        ["Import", "Run", "Review", "Export"]
    )

    with tab_import:
        uploaded = st.file_uploader(
            "JPEG / PNG / PDF",
            type=["jpg", "jpeg", "png", "pdf"],
            accept_multiple_files=True,
        )
        dpi = st.number_input("PDF render DPI", min_value=72, max_value=600, value=200)
        if st.button("Import files") and uploaded:
            for f in uploaded:
                try:
                    project = ingest.import_bytes(
                        project, f.name, f.getvalue(), render_dpi=int(dpi)
                    )
                    st.success(f"Imported {f.name}")
                except TranscribeError as exc:
                    st.error(f"{f.name}: {exc}")
            st.rerun()
        st.write(f"Pages in project: **{len(project.pages)}**")

    with tab_run:
        base_url = st.text_input("Ollama base URL", value=project.settings.base_url)
        try:
            normalized = normalize_base_url(base_url)
            remote = not is_loopback_host(normalized)
        except Exception as exc:
            st.error(str(exc))
            normalized = project.settings.base_url
            remote = False

        allow_remote = False
        if remote:
            st.warning(
                "This Ollama host is not loopback. Page images will leave this machine."
            )
            allow_remote = st.checkbox("I understand and want to use this remote host")

        provider = OllamaVisionProvider(normalized)
        c1, c2 = st.columns([1, 1])
        refresh = c2.button("Refresh Models")
        discovery = provider.list_vision_models(refresh=refresh)
        if discovery.error:
            st.caption(f"Discovery: {discovery.error}")
        names = [m.name for m in discovery.models]
        all_discovery = provider.list_models(refresh=False)
        unknown = [m.name for m in all_discovery.models if not m.capability_known]
        model = st.selectbox(
            "Vision model",
            options=names or [project.settings.model_name or ""],
            index=0 if names else 0,
        )
        manual = st.text_input(
            "Advanced / manual model override",
            value="",
            help="Use when capabilities are unknown on older Ollama builds.",
        )
        if manual.strip():
            model = manual.strip()
        if unknown:
            with st.expander("Models with unknown capabilities"):
                st.write(", ".join(unknown))

        prompt_id = st.selectbox("Prompt", ["faithful_markdown", "faithful_text"])
        custom = st.text_area("Custom prompt override (optional)", value=project.settings.custom_prompt or "")
        preprocess = st.selectbox("Preprocess", ["none", "gentle_contrast"])
        workers = st.selectbox("Workers", [1, 2], index=0)
        force = st.checkbox("Force re-run (ignore matching fingerprints)")

        if st.button("Save settings"):
            settings = project.settings
            settings.base_url = normalized
            settings.model_name = model
            settings.prompt_id = prompt_id
            settings.custom_prompt = custom.strip() or None
            settings.preprocess_profile = preprocess
            settings.max_workers = int(workers)
            settings.allow_non_loopback = allow_remote
            settings.generation_options.temperature = 0.0
            project = projects.save_settings(project, settings)
            coord.provider = OllamaVisionProvider(normalized)
            st.success("Settings saved")

        # Fragment auto-refreshes progress without full-app sleep/rerun (no icon flicker).
        poll = timedelta(seconds=2) if live.status == "running" or was_running else None

        @st.fragment(run_every=poll)
        def job_status_panel() -> None:
            progress = coord.get_progress()
            _render_job_progress(progress)
            if (
                st.session_state.get("_job_was_running")
                and progress.status != "running"
            ):
                st.session_state["_job_was_running"] = False
                st.rerun()

        job_status_panel()

        b1, b2 = st.columns(2)
        if b1.button("Start transcription", disabled=live.status == "running"):
            if remote and not allow_remote:
                st.error("Enable the remote-host acknowledgement first.")
            else:
                try:
                    settings = project.settings
                    settings.base_url = normalized
                    settings.model_name = model
                    settings.prompt_id = prompt_id
                    settings.custom_prompt = custom.strip() or None
                    settings.preprocess_profile = preprocess
                    settings.max_workers = int(workers)
                    settings.allow_non_loopback = allow_remote
                    project = projects.save_settings(project, settings)
                    coord.provider = OllamaVisionProvider(normalized)
                    coord.start(force=force)
                    st.session_state["_job_was_running"] = True
                    st.rerun()
                except (JobConflictError, TranscribeError) as exc:
                    st.error(str(exc))
        if b2.button("Stop after current page", disabled=live.status != "running"):
            coord.request_cancel()
            st.info("Stopping after current page…")

    with tab_review:
        if not project.pages:
            st.info("No pages yet.")
        else:
            idx = st.number_input(
                "Page number", min_value=1, max_value=len(project.pages), value=1
            )
            page = project.pages[int(idx) - 1]
            render = project.renders[page.active_render_id]
            img_path = paths.resolve_contained(render.image_relpath)
            result = projects.load_page_result(page.page_id)
            left, right = st.columns(2)
            with left:
                st.image(str(img_path), width="stretch")
            with right:
                status = result.status if result else "pending"
                st.write(f"Status: **{status}**")
                attempt = result.active_attempt() if result else None
                raw = attempt.raw_text if attempt else ""
                edited = result.edited_text if result else None
                if edited is not None and attempt and attempt.raw_text is not None:
                    st.caption("An edit is active. New OCR raw text is preserved separately.")
                    if st.button("Use new transcription"):
                        projects.adopt_raw_as_edit(page.page_id)
                        st.rerun()
                default_text = edited if edited is not None else (raw or "")
                text = st.text_area("Transcription", value=default_text, height=400)
                if st.button("Save edit"):
                    projects.save_user_edit(page.page_id, text)
                    st.success("Saved")

    with tab_export:
        if st.button("Export"):
            written = ExportService(paths, projects).export_all(project)
            for kind, path in written.items():
                st.write(f"**{kind}:** `{path}`")
            st.download_button(
                "Download notebook JSON",
                data=path_read(written["notebook"]),
                file_name="notebook.transcribe.json",
            )


def path_read(path: Path) -> bytes:
    return Path(path).read_bytes()


if __name__ == "__main__":
    main()
