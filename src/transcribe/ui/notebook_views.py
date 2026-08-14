"""Notebook View consume pages (published.json product bodies)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import streamlit as st

from transcribe.analysis.health import derive_analysis_health, scope_analysis_health
from transcribe.analysis.modules import THROUGH_OVERVIEW, THROUGH_THEMES, get_registered_modules
from transcribe.analysis.runner import AnalysisRunner, module_freshness
from transcribe.analysis.storage import AnalysisStorage
from transcribe.config.facade import get_config
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.services.analysis_compare import COMPARABLE_SPECS
from transcribe.ui.analysis_product_views import (
    render_ask_product,
    render_moments_product,
    render_mood_product,
    render_overview_product,
    render_summaries_product,
    render_themes_product,
)
from transcribe.ui.navigation import (
    PageSpec,
    ViewPanel,
    notebook_has_detection_results,
    notebook_has_published_analysis,
    page_spec_for,
)
from transcribe.ui.notebook_view_page import render_analyse_cta, render_notebook_view_page, select_view_panel
from transcribe.ui.page_viewer import render_page_viewer
from transcribe.ui.shell import render_page_shell
from transcribe.ui.view_jumps import jump_to_reading


def _module_id_lists() -> dict[str, list[str]]:
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
    return {
        "overview": overview_ids,
        "themes": theme_ids,
        "mood": mood_ids,
        "synth": synth_ids,
        "places_extra": ["entity_sentiment"],
    }


def load_view_health(paths, projects, project, *, get_analysis_coordinator) -> dict[str, Any]:
    """Shared health batch for View pages (status strip + product bodies)."""
    ids = _module_id_lists()
    runner = AnalysisRunner(projects, clock=SystemClock(), ids=UuidGenerator())
    storage = AnalysisStorage(paths)
    content_revision = projects.content_revision(project)
    batch_ids = list(
        dict.fromkeys(
            ids["overview"]
            + ids["themes"]
            + ids["mood"]
            + ["moments"]
            + ids["synth"]
            + ids["places_extra"]
        )
    )
    analysis_coord = get_analysis_coordinator(str(paths.root))
    active_run_status = "running" if analysis_coord.is_running() else None
    if active_run_status is None:
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
    return {
        "runner": runner,
        "storage": storage,
        "ids": ids,
        "batch_health": batch_health,
        "overview_health": scope_analysis_health(batch_health, ids["overview"]),
        "themes_health": scope_analysis_health(batch_health, ids["themes"]),
        "mood_health": scope_analysis_health(batch_health, ids["mood"]),
        "moments_health": scope_analysis_health(batch_health, ["moments"]),
        "summaries_health": scope_analysis_health(batch_health, ids["synth"]),
    }


def _on_jump(page_id: str, *, project, paths, return_mode: str) -> None:
    jump_to_reading(
        page_id,
        project=project,
        project_root=paths.root,
        return_mode=return_mode,
    )


def render_view_overview(runtime, paths, projects, project, *, get_analysis_coordinator) -> None:
    spec = page_spec_for("Overview")
    assert spec is not None
    ctx = load_view_health(
        paths, projects, project, get_analysis_coordinator=get_analysis_coordinator
    )
    visible = list(get_config().effective.ui.overview_cards)
    comparable_on = any(cid in COMPARABLE_SPECS for cid in visible if cid != "page_metrics")

    def _body() -> None:
        def _page_metrics() -> None:
            from transcribe.ui.page_metrics_view import render_overview_page_metrics

            render_overview_page_metrics(
                projects,
                project,
                on_jump=lambda pid: _on_jump(
                    pid, project=project, paths=paths, return_mode="Overview"
                ),
            )

        render_overview_product(
            ctx["overview_health"],
            ctx["ids"]["overview"],
            render_page_metrics=_page_metrics if "page_metrics" in visible else None,
            projects_dir=runtime.projects_dir if comparable_on else None,
            project_id=project.id,
            on_jump=lambda pid: _on_jump(
                pid, project=project, paths=paths, return_mode="Overview"
            ),
            visible_cards=visible,
            heading=False,
        )

    render_notebook_view_page(spec, health=ctx["batch_health"], body=_body)


def _spec_for_panel(spec: PageSpec, panel: ViewPanel) -> PageSpec:
    return replace(spec, title=panel.title, description=panel.description)


def render_view_themes(runtime, paths, projects, project, *, get_analysis_coordinator) -> None:
    spec = page_spec_for("Themes")
    assert spec is not None
    published = notebook_has_published_analysis(paths.root)
    ctx = load_view_health(
        paths, projects, project, get_analysis_coordinator=get_analysis_coordinator
    )
    panel = select_view_panel("Themes", project_id=project.id, render=False)
    assert panel is not None
    spec = _spec_for_panel(spec, panel)

    def _body() -> None:
        chosen = select_view_panel("Themes", project_id=project.id, render=True)
        assert chosen is not None
        if chosen.id == "people":
            from transcribe.ui.places_map import render_notebook_places_tab

            st.caption("All-notebook map: Places in the primary nav.")
            ner_mh = ctx["batch_health"].modules.get("ner")
            entity_mh = ctx["batch_health"].modules.get("entity_sentiment")
            render_notebook_places_tab(
                project_root=paths.root,
                runtime=runtime,
                ner_health=ner_mh,
                entity_sentiment_health=entity_mh,
                heading=False,
            )
            return
        themes = get_registered_modules(through=THROUGH_THEMES)
        assert set(ctx["ids"]["themes"]).issubset(set(themes))
        st.caption("Corpus Places map is under Places in the primary nav.")
        render_themes_product(
            ctx["themes_health"],
            ctx["ids"]["themes"],
            on_jump=lambda pid: _on_jump(
                pid, project=project, paths=paths, return_mode="Themes"
            ),
            project_id=project.id,
            heading=False,
        )

    empty_title = "No published NER yet" if panel.id == "people" else "No published analysis yet"
    empty_body = (
        "Run Analyse (including NER) to map people and places in this notebook."
        if panel.id == "people"
        else "Run Analyse on this notebook to see themes."
    )
    render_notebook_view_page(
        spec,
        health=ctx["batch_health"],
        show_analyse_cta=not published,
        analyse_cta_key="themes_analyse_cta",
        body=_body if published else None,
        empty_kind=None if published else "no_results_yet",
        empty_title=empty_title,
        empty_body=empty_body,
    )


def render_view_mood(runtime, paths, projects, project, *, get_analysis_coordinator) -> None:
    spec = page_spec_for("Mood")
    assert spec is not None
    published = notebook_has_published_analysis(paths.root)
    ctx = load_view_health(
        paths, projects, project, get_analysis_coordinator=get_analysis_coordinator
    )
    panel = select_view_panel("Mood", project_id=project.id, render=False)
    assert panel is not None
    spec = _spec_for_panel(spec, panel)

    def _body() -> None:
        chosen = select_view_panel("Mood", project_id=project.id, render=True)
        assert chosen is not None
        if chosen.id == "moments":
            render_moments_product(
                ctx["moments_health"],
                on_jump=lambda pid: _on_jump(
                    pid, project=project, paths=paths, return_mode="Moments"
                ),
                project_id=project.id,
                heading=False,
            )
            return
        render_mood_product(
            ctx["mood_health"],
            ctx["ids"]["mood"],
            projects_dir=runtime.projects_dir,
            project_id=project.id,
            on_jump=lambda pid: _on_jump(
                pid, project=project, paths=paths, return_mode="Mood"
            ),
            heading=False,
        )

    empty_title = "No published analysis yet"
    empty_body = (
        "Run Analyse on this notebook to see moments."
        if panel.id == "moments"
        else "Run Analyse on this notebook to see mood and tone."
    )
    render_notebook_view_page(
        spec,
        health=ctx["batch_health"],
        show_analyse_cta=not published,
        analyse_cta_key="mood_analyse_cta",
        body=_body if published else None,
        empty_kind=None if published else "no_results_yet",
        empty_title=empty_title,
        empty_body=empty_body,
    )


def render_view_summaries(runtime, paths, projects, project, *, get_analysis_coordinator) -> None:
    _ = runtime
    spec = page_spec_for("Summaries")
    assert spec is not None
    published = notebook_has_published_analysis(paths.root)
    ctx = load_view_health(
        paths, projects, project, get_analysis_coordinator=get_analysis_coordinator
    )
    panel = select_view_panel("Summaries", project_id=project.id, render=False)
    assert panel is not None
    spec = _spec_for_panel(spec, panel)
    question_key = f"ask_notebook_question_{project.id}"

    def _body() -> None:
        chosen = select_view_panel("Summaries", project_id=project.id, render=True)
        assert chosen is not None
        if chosen.id == "ask":
            st.caption("Ask notebook is ad-hoc and does not update batch analysis health.")
            render_ask_product(runner=ctx["runner"], question_key=question_key, heading=False)
            question = st.session_state.get(question_key) or ""
            rm = module_freshness(
                ctx["runner"],
                ctx["storage"],
                ["llm_custom_qa"],
                question_text=question.strip() or None,
            )[0]
            if rm.get("envelope"):
                st.divider()
                if rm.get("status") == "stale":
                    st.caption("Last Ask answer is out of date — ask again to refresh.")
                else:
                    st.caption("Last Ask answer")
                    payload = (rm["envelope"] or {}).get("payload") or {}
                    if payload.get("answer"):
                        st.markdown(payload["answer"])
                    with st.expander("Advanced · last Ask"):
                        st.json(payload)
            return
        if not published:
            render_analyse_cta(key="summaries_analyse_cta")
            return
        render_summaries_product(
            ctx["summaries_health"], ctx["ids"]["synth"], heading=False
        )

    render_notebook_view_page(
        spec,
        health=ctx["batch_health"],
        body=_body,
    )


def render_view_detect(*, projects, project, project_root: str) -> None:
    spec = page_spec_for("Detect")
    assert spec is not None
    from transcribe.services.project import open_project_paths
    from transcribe.ui.action_menus.nav import viewer_page_ids
    from transcribe.ui.run_detection import render_detection_workspace

    if st.session_state.get("show_page_viewer") and st.session_state.get("view_page_id"):
        render_page_shell(spec.title, spec.description)
        paths = open_project_paths(Path(project_root))
        page_ids = st.session_state.get("view_page_ids") or viewer_page_ids(project)
        render_page_viewer(
            paths=paths,
            projects=projects,
            project=project,
            page_id=st.session_state["view_page_id"],
            page_ids=page_ids,
            view_entries=st.session_state.get("view_entries"),
            highlight_query=st.session_state.get("view_highlight", ""),
            back_label="Back to Detect",
            presentation="read",
        )
        return

    render_page_shell(spec.title, spec.description)
    render_detection_workspace(
        projects=projects,
        project_root=project_root,
        project_id=getattr(project, "id", "nb"),
        show_shell=False,
    )
    if not notebook_has_detection_results(project_root):
        st.caption("No detection findings yet — run a detector on this page.")
