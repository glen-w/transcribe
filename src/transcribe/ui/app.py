"""Streamlit UI for Transcribe.

JobCoordinator, BatchOcrCoordinator, and AnalysisCoordinator are owned via
st.cache_resource so reruns do not drop live OCR / analysis jobs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

from transcribe.analysis.coordinator import AnalysisCoordinator, build_analysis_coordinator
from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import TranscribeError
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import build_runtime_paths
from transcribe.services.archive import ArchiveService, bump_archive_generation
from transcribe.services.project import (
    ProjectService,
    allocate_notebook_root,
    open_project_paths,
)
from transcribe.ui.archive_views import render_archive, render_notebooks, render_search
from transcribe.ui.settings_interface import render_settings_page
from transcribe.ui.page_viewer import render_page_viewer
from transcribe.ui.run_analysis import render_run_analysis_form
from transcribe.ui.run_import import render_run_import
from transcribe.ui.run_transcribe import render_run_transcribe
from transcribe.ui.shell import (
    configure_streamlit_page,
    inject_global_styles,
    is_open_notebook_workflow,
    is_workflow_mode,
    normalize_ui_mode,
    render_brand,
    render_mode_nav,
    render_page_shell,
    set_ui_mode,
    sync_notebook_selector,
)
from transcribe.ui.targets import PENDING_IMPORT_TARGET_KEY, TARGET_BATCH


@st.cache_resource
def get_analysis_coordinator(project_root: str) -> AnalysisCoordinator:
    _paths, _projects, coord = build_analysis_coordinator(
        project_root,
        clock=SystemClock(),
        ids=UuidGenerator(),
    )
    return coord


@st.cache_resource
def get_archive(projects_dir: str, data_dir: str) -> ArchiveService:
    """Keep ArchiveService across Streamlit reruns so TTL / generation state sticks."""
    from transcribe.runtime_paths import RuntimePaths

    live = build_runtime_paths()
    runtime = RuntimePaths(
        repo_root=live.repo_root,
        data_dir=Path(data_dir),
        projects_dir=Path(projects_dir),
        inbox_dir=live.inbox_dir,
        export_dir=live.export_dir,
    )
    return ArchiveService(runtime)


def _services(project_root: str):
    paths = open_project_paths(Path(project_root))
    clock = SystemClock()
    ids = UuidGenerator()
    projects = ProjectService(paths, clock=clock, ids=ids)
    from transcribe.config.facade import get_config
    from transcribe.ingest import IngestService

    dpi = int(get_config().effective.ingest.render_dpi)
    declutter = bool(get_config().effective.ingest.visual_declutter_enabled)
    ingest = IngestService(
        paths,
        clock=clock,
        ids=ids,
        default_dpi=dpi,
        visual_declutter_enabled=declutter,
    )
    return paths, projects, ingest


def _render_workflow(runtime, root: str, *, section: str = "Import") -> None:
    section = normalize_ui_mode(section)
    try:
        paths, projects, _ingest = _services(root)
        project = projects.load(reconcile=True)
    except TranscribeError as exc:
        st.info("Select or create a notebook to begin.")
        st.caption(str(exc))
        return

    if (
        section == "Review"
        and st.session_state.get("show_page_viewer")
        and st.session_state.get("view_page_id")
    ):
        from transcribe.ui.action_menus.nav import viewer_page_ids

        render_page_viewer(
            paths=paths,
            projects=projects,
            project=project,
            page_id=st.session_state["view_page_id"],
            page_ids=st.session_state.get("view_page_ids")
            or viewer_page_ids(project),
            view_entries=st.session_state.get("view_entries"),
            highlight_query=st.session_state.get("view_highlight", ""),
            back_label="Back to Review",
        )
        return

    if section == "Analyse":
        st.caption(f"Project: `{paths.root}`")
        from transcribe.ui.run_analysis import analysis_run_in_progress
        from transcribe.ui.run_detection import render_detection_workspace

        focus_detect = bool(st.session_state.pop("analyse_focus_detect", False))
        analysis_coord = get_analysis_coordinator(str(paths.root))
        analyse_tabs = st.tabs(["Run Analysis", "Published results", "Detect"])
        with analyse_tabs[0]:
            running = render_run_analysis_form(
                projects=projects, project=project, coord=analysis_coord
            )
        with analyse_tabs[1]:
            if running or analysis_run_in_progress(analysis_coord):
                st.info("Published results available when the current run finishes.")
            else:
                _render_analysis_result_tabs(runtime, paths, projects, project)
        with analyse_tabs[2]:
            render_detection_workspace(
                projects=projects, project_root=str(paths.root)
            )
        if focus_detect:
            st.info("Opened Detect from notebook actions.")
        return

    st.caption(f"Project: `{paths.root}`")

    if section == "Export":
        _render_export_panel(runtime, paths, projects, project, root)
        return

    if section == "Review":
        if not project.pages:
            st.info("No pages yet.")
        else:
            from transcribe.ui.action_menus.nav import viewer_page_ids

            page_ids = viewer_page_ids(project)
            default_id = st.session_state.get("view_page_id") or page_ids[0]
            if default_id not in page_ids:
                default_id = page_ids[0]
            # Rebuild nav for the open notebook so stale Archive/Search entries
            # (e.g. a deleted notebook) cannot override Review.
            view_entries = [
                {"page_id": pid, "project_root": str(paths.root)} for pid in page_ids
            ]
            st.session_state["view_page_id"] = default_id
            st.session_state["view_page_ids"] = page_ids
            st.session_state["view_entries"] = view_entries
            render_page_viewer(
                paths=paths,
                projects=projects,
                project=project,
                page_id=default_id,
                page_ids=page_ids,
                view_entries=view_entries,
                highlight_query="",
                show_back=False,
            )
        return


def _render_export_panel(runtime, paths, projects, project, root: str) -> None:
    from transcribe.ui.export_panel import render_export_panel

    archive = get_archive(str(runtime.projects_dir), str(runtime.data_dir))
    render_export_panel(runtime, paths, projects, project, root, archive=archive)


def _render_analysis_result_tabs(runtime, paths, projects, project) -> None:
    from transcribe.analysis.health import derive_analysis_health, scope_analysis_health
    from transcribe.analysis.modules import (
        THROUGH_OVERVIEW,
        THROUGH_THEMES,
        get_registered_modules,
    )
    from transcribe.analysis.runner import AnalysisRunner, module_freshness
    from transcribe.analysis.storage import AnalysisStorage
    from transcribe.ports import SystemClock, UuidGenerator
    from transcribe.ui.analysis_health_view import render_status_strip
    from transcribe.ui.analysis_product_views import (
        render_ask_product,
        render_moments_product,
        render_mood_product,
        render_overview_product,
        render_summaries_product,
        render_themes_product,
    )

    runner = AnalysisRunner(projects, clock=SystemClock(), ids=UuidGenerator())
    storage = AnalysisStorage(paths)
    content_revision = projects.content_revision(project)

    overview_ids = list(get_registered_modules(through=THROUGH_OVERVIEW).keys())
    theme_ids = [
        "keyphrases",
        "topic_modeling",
        "semantic_similarity",
        "topic_shift",
        "bertopic",
    ]
    mood_ids = [
        "sentiment",
        "emotion",
        "contextual_emotion",
        "fine_grained_emotion",
        "affect_tension",
        "epistemic_markers",
    ]
    synth_ids = [
        "topic_modeling",
        "highlights",
        "summary",
        "insights",
        "llm_summary",
        "llm_action_items",
        "narrative_summary",
    ]
    batch_ids = list(
        dict.fromkeys(overview_ids + theme_ids + mood_ids + ["moments"] + synth_ids)
    )
    analysis_coord = get_analysis_coordinator(str(paths.root))
    active_run_status = "running" if analysis_coord.is_running() else None
    if active_run_status is None:
        # Surface interrupted reopen state on the shared strip when present.
        try:
            runs_dir = storage.runs_dir()
            if runs_dir.is_dir():
                for path in sorted(runs_dir.glob("*.json"), reverse=True):
                    rec = storage.read_run_record(path.stem)
                    if rec and rec.get("status") == "interrupted":
                        active_run_status = "interrupted"
                        break
        except Exception:  # noqa: BLE001 — strip is best-effort
            pass
    batch_health = derive_analysis_health(
        storage=storage,
        runner=runner,
        module_ids=batch_ids,
        content_revision=content_revision,
        active_run_status=active_run_status,
    )
    overview_health = scope_analysis_health(batch_health, overview_ids)
    themes_health = scope_analysis_health(batch_health, theme_ids)
    mood_health = scope_analysis_health(batch_health, mood_ids)
    moments_health = scope_analysis_health(batch_health, ["moments"])
    summaries_health = scope_analysis_health(batch_health, synth_ids)

    # Phase 6 #8 — sole default freshness/health answer across batch tabs.
    render_status_strip(batch_health)

    (
        tab_overview,
        tab_themes,
        tab_mood,
        tab_moments,
        tab_places,
        tab_summaries,
        tab_ask,
    ) = st.tabs(
        [
            "Overview",
            "Themes",
            "Mood & tone",
            "Moments",
            "People & places",
            "Summaries",
            "Ask notebook",
        ]
    )

    with tab_overview:

        def _page_metrics() -> None:
            from transcribe.ui.page_metrics_view import render_overview_page_metrics

            render_overview_page_metrics(projects, project)

        render_overview_product(
            overview_health, overview_ids, render_page_metrics=_page_metrics
        )

    with tab_themes:
        themes = get_registered_modules(through=THROUGH_THEMES)
        assert set(theme_ids).issubset(set(themes))
        render_themes_product(themes_health, theme_ids)

    with tab_mood:
        render_mood_product(mood_health, mood_ids)

    with tab_moments:
        def _jump_to_page(page_id: str) -> None:
            st.session_state["review_page_id"] = page_id
            st.session_state["nav_section"] = "Review"
            st.rerun()

        render_moments_product(moments_health, on_jump=_jump_to_page)

    with tab_places:
        from transcribe.ui.places_map import render_notebook_places_tab

        ner_mh = batch_health.modules.get("ner")
        render_notebook_places_tab(
            project_root=paths.root,
            runtime=runtime,
            ner_health=ner_mh,
        )

    with tab_summaries:
        render_summaries_product(summaries_health, synth_ids)

    with tab_ask:
        st.caption("Ask notebook is ad-hoc and does not update batch analysis health.")
        render_ask_product(runner=runner)
        question = st.session_state.get("ask_notebook_question") or ""
        rm = module_freshness(
            runner,
            storage,
            ["llm_custom_qa"],
            question_text=question.strip() or None,
        )[0]
        if rm.get("envelope"):
            st.divider()
            if rm.get("status") == "stale":
                st.caption(
                    "Last Ask answer is out of date — ask again to refresh."
                )
            else:
                st.caption("Last Ask answer")
                payload = (rm["envelope"] or {}).get("payload") or {}
                if payload.get("answer"):
                    st.markdown(payload["answer"])
                with st.expander("Advanced · last Ask"):
                    st.json(payload)



_PAGE_SHELL: dict[str, tuple[str, str]] = {
    "Archive": (
        "Archive",
        "Browse notebooks by timeline, tags, and recent activity.",
    ),
    "View": (
        "View",
        "Open a notebook volume and jump into its pages.",
    ),
    "Search": (
        "Search",
        "Find text across transcribed notebook pages.",
    ),
    "Places": (
        "Places",
        "Map places mentioned across all notebooks (from published NER).",
    ),
    "New notebook": (
        "New notebook",
        "Create a notebook, then import pages and run OCR.",
    ),
    "Import": (
        "Import",
        "Add pages to this notebook, or batch-import folders into the corpus.",
    ),
    "Transcribe": (
        "Transcribe",
        "Configure Ollama and run OCR on this notebook or many notebooks.",
    ),
    "Review": (
        "Review",
        "Browse and edit transcribed pages.",
    ),
    "Analyse": (
        "Analyse",
        "Run notebook analysis from Quick / Balanced / Thorough presets.",
    ),
    "Export": (
        "Export",
        "Export notebook JSON, Markdown, plain text, HTML, EPUB, and PDF.",
    ),
    "Settings": (
        "Settings",
        "Workspace knobs: analysis presets, models, profiles, and interface menus.",
    ),
}


def _notebook_dropdown_options(archive: ArchiveService) -> list[tuple[str, str]]:
    """``(root_path, title)`` pairs for the sidebar notebook selectbox."""
    notebooks = archive.list_notebooks(order="newest")
    out: list[tuple[str, str]] = []
    for nb in notebooks:
        try:
            root = str(nb.root.expanduser().resolve())
        except OSError:
            root = str(nb.root)
        out.append((root, nb.title or nb.root.name))
    return out


def _render_new_notebook(runtime, archive: ArchiveService) -> None:
    st.caption(
        "Creates a new notebook folder under the workspace notebooks directory, "
        "then opens Import."
    )
    if "new_notebook_title" not in st.session_state:
        st.session_state["new_notebook_title"] = "Untitled notebook"
    title_in = st.text_input(
        "Notebook name",
        key="new_notebook_title",
        help="Display title. A folder name is derived automatically.",
    )
    if st.button("Create notebook", type="primary", key="new_notebook_create"):
        cleaned = (title_in or "").strip() or "Untitled notebook"
        try:
            root = allocate_notebook_root(runtime.projects_dir, cleaned)
            paths = open_project_paths(root)
            ProjectService(
                paths,
                clock=SystemClock(),
                ids=UuidGenerator(),
                corpus_paths=CorpusPaths.from_runtime(runtime),
            ).create(title=cleaned)
            bump_archive_generation(runtime)
            archive.ensure_index()
            st.cache_resource.clear()
            st.session_state["root"] = str(paths.root)
            sync_notebook_selector(str(paths.root))
            st.session_state.pop("new_notebook_title", None)
            st.toast(f"Created “{cleaned}”")
            set_ui_mode("Import")
        except TranscribeError as exc:
            st.error(str(exc))


def main() -> None:
    configure_streamlit_page()
    inject_global_styles()

    runtime = build_runtime_paths()
    runtime.ensure_layout()

    archive = get_archive(str(runtime.projects_dir), str(runtime.data_dir))
    archive.ensure_index()
    notebook_options = _notebook_dropdown_options(archive)

    raw_mode = st.session_state.get("ui_mode")
    if raw_mode == "Inbox":
        st.session_state[PENDING_IMPORT_TARGET_KEY] = TARGET_BATCH
    mode = normalize_ui_mode(raw_mode)
    st.session_state["ui_mode"] = mode

    with st.sidebar:
        render_brand()
        mode = render_mode_nav(mode, notebook_options=notebook_options)

    root = st.session_state.get("root") or ""

    # Page viewer overlay when navigated from Archive/Search/View.
    if (
        not is_workflow_mode(mode)
        and st.session_state.get("show_page_viewer")
        and st.session_state.get("view_page_id")
        and root
    ):
        try:
            render_page_viewer(
                page_id=st.session_state["view_page_id"],
                page_ids=st.session_state.get("view_page_ids"),
                view_entries=st.session_state.get("view_entries"),
                highlight_query=st.session_state.get("view_highlight", ""),
                show_back=False,
            )
            return
        except TranscribeError as exc:
            st.error(str(exc))
            st.session_state["show_page_viewer"] = False

    title, desc = _PAGE_SHELL[mode]
    # Analyse owns its own page shell inside Run Analysis.
    if mode != "Analyse":
        render_page_shell(title, desc)

    if mode == "Archive":
        render_archive(runtime, archive)
    elif mode == "View":
        render_notebooks(runtime, archive)
    elif mode == "Search":
        render_search(runtime, archive)
    elif mode == "Places":
        from transcribe.ui.places_map import render_corpus_places_page

        render_corpus_places_page(runtime)
    elif mode == "Settings":
        render_settings_page()
    elif mode == "New notebook":
        _render_new_notebook(runtime, archive)
    elif mode in {"Import", "Transcribe"}:
        projects = ingest = project = None
        if root:
            try:
                _paths, projects, ingest = _services(root)
                project = projects.load(reconcile=True)
                st.caption(f"Project: `{_paths.root}`")
            except TranscribeError as exc:
                st.caption(str(exc))
                projects = ingest = project = None
        if mode == "Import":
            render_run_import(
                runtime,
                root=root or None,
                projects=projects,
                ingest=ingest,
                project=project,
            )
        else:
            render_run_transcribe(
                runtime,
                root=root or None,
                projects=projects,
                project=project,
            )
    elif is_open_notebook_workflow(mode):
        if not root:
            st.info("Select a notebook above, or create one under Workflow → New notebook.")
            return
        _render_workflow(runtime, root, section=mode)


def path_read(path: Path) -> bytes:
    return Path(path).read_bytes()


def cli_main() -> None:
    """Console entry: ``transcribe-ui`` → Streamlit on port 8510 by default."""
    app_path = str(Path(__file__).resolve())
    port = os.getenv("TRANSCRIBE_PORT", "8510")
    address = os.getenv("TRANSCRIBE_HOST", "127.0.0.1")
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        f"--server.port={port}",
        f"--server.address={address}",
        "--browser.gatherUsageStats=false",
    ]
    from streamlit.web import cli as stcli

    raise SystemExit(stcli.main())


if __name__ == "__main__":
    main()
