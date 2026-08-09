"""Streamlit UI for Transcribe.

JobCoordinator is owned via st.cache_resource so reruns do not drop live jobs.
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

import streamlit as st

from transcribe.errors import JobConflictError, TranscribeError
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.providers.ollama import (
    OllamaVisionProvider,
    is_local_machine_host,
    normalize_base_url,
)
from transcribe.runtime_paths import build_runtime_paths
from transcribe.services.archive import ArchiveService
from transcribe.services.export import ExportService
from transcribe.services.job import JobCoordinator, JobProgress, build_coordinator
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.ui.archive_views import render_archive, render_notebooks, render_search
from transcribe.ui.page_viewer import render_page_viewer


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


def _render_workflow(runtime, root: str) -> None:
    try:
        paths, projects, ingest = _services(root)
        project = projects.load(reconcile=True)
    except TranscribeError as exc:
        st.info("Create or open a project directory to begin.")
        st.caption(str(exc))
        return

    if st.session_state.get("show_page_viewer") and st.session_state.get("view_page_id"):
        render_page_viewer(
            paths=paths,
            projects=projects,
            project=project,
            page_id=st.session_state["view_page_id"],
            page_ids=st.session_state.get("view_page_ids")
            or [p.page_id for p in project.pages],
            view_entries=st.session_state.get("view_entries"),
            highlight_query=st.session_state.get("view_highlight", ""),
            back_label="Back to workflow",
        )
        return

    coord = get_coordinator(str(paths.root))
    live = coord.get_progress()
    was_running = st.session_state.get("_job_was_running", False)
    st.session_state["_job_was_running"] = live.status == "running"

    (
        tab_import,
        tab_run,
        tab_pages,
        tab_export,
        tab_overview,
        tab_themes,
        tab_mood,
        tab_moments,
        tab_summaries,
        tab_ask,
    ) = st.tabs(
        [
            "Import",
            "Run",
            "Pages",
            "Export",
            "Overview",
            "Themes",
            "Mood & tone",
            "Moments",
            "Summaries",
            "Ask notebook",
        ]
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
                        f.name, f.getvalue(), render_dpi=int(dpi)
                    )
                    st.success(f"Imported {f.name}")
                except TranscribeError as exc:
                    st.error(f"{f.name}: {exc}")
            st.rerun()
        st.write(f"Pages in project: **{len(project.pages)}**")
        tags_in = st.text_input("Notebook tags (comma-separated)", value=", ".join(project.tags))
        if st.button("Save notebook tags"):
            project = projects.update_notebook_metadata(
                tags=[t for t in tags_in.split(",")]
            )
            st.success("Tags saved")

    with tab_run:
        base_url = st.text_input("Ollama base URL", value=project.settings.base_url)
        try:
            normalized = normalize_base_url(base_url)
            remote = not is_local_machine_host(normalized)
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
        text_model_options = [m.name for m in all_discovery.models] or [
            project.settings.text_model_name or ""
        ]
        text_model = st.selectbox(
            "Text analysis model",
            options=text_model_options,
            index=(
                text_model_options.index(project.settings.text_model_name)
                if project.settings.text_model_name in text_model_options
                else 0
            ),
            help="Required for LLM analysis modules. Vision/embedding models are rejected.",
        )
        text_manual = st.text_input(
            "Advanced / manual text model override",
            value="",
            help="Exact Ollama model name for Summaries / Ask notebook LLM modules.",
        )
        if text_manual.strip():
            text_model = text_manual.strip()
        manual = st.text_input(
            "Advanced / manual vision model override",
            value="",
            help="Use when capabilities are unknown on older Ollama builds.",
        )
        if manual.strip():
            model = manual.strip()
        if unknown:
            with st.expander("Models with unknown capabilities"):
                st.write(", ".join(unknown))

        prompt_id = st.selectbox("Prompt", ["faithful_markdown", "faithful_text"])
        custom = st.text_area(
            "Custom prompt override (optional)", value=project.settings.custom_prompt or ""
        )
        preprocess = st.selectbox("Preprocess", ["none", "gentle_contrast"])
        workers = st.selectbox("Workers", [1, 2], index=0)
        force = st.checkbox("Force re-run (ignore matching fingerprints)")

        if st.button("Save settings"):
            if live.status == "running":
                st.warning(
                    "A job is running; settings will apply to the next job only "
                    "(the active JobPlan is frozen)."
                )
            settings = project.settings
            settings.base_url = normalized
            settings.model_name = model
            settings.text_model_name = text_model
            settings.prompt_id = prompt_id
            settings.custom_prompt = custom.strip() or None
            settings.preprocess_profile = preprocess
            settings.max_workers = int(workers)
            settings.allow_non_loopback = allow_remote
            settings.generation_options.temperature = 0.0
            project = projects.save_settings(project, settings)
            if live.status != "running":
                coord.provider = OllamaVisionProvider(normalized)
            st.success("Settings saved")

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

    with tab_pages:
        if not project.pages:
            st.info("No pages yet.")
        else:
            page_ids = [p.page_id for p in project.pages]
            default_id = st.session_state.get("view_page_id") or page_ids[0]
            if default_id not in page_ids:
                default_id = page_ids[0]
            st.session_state["view_page_id"] = default_id
            st.session_state["view_page_ids"] = page_ids
            project = render_page_viewer(
                paths=paths,
                projects=projects,
                project=project,
                page_id=default_id,
                page_ids=page_ids,
                highlight_query="",
                show_back=False,
            )

    with tab_export:
        export_dest = st.text_input(
            "Export directory",
            value=str(runtime.export_dir / Path(root).name),
        )
        if st.button("Export"):
            dest = Path(export_dest) if export_dest.strip() else None
            written = ExportService(paths, projects).export_all(project, dest)
            for kind, path in written.items():
                st.write(f"**{kind}:** `{path}`")
            st.download_button(
                "Download notebook JSON",
                data=path_read(written["notebook"]),
                file_name="notebook.transcribe.json",
            )

    with tab_overview:
        from transcribe.analysis.adapter import build_page_v1_document
        from transcribe.analysis.cache_identity import (
            build_cache_identity_object,
            cache_identity_hex,
        )
        from transcribe.analysis.document import AnalysisDocumentError
        from transcribe.analysis.modules import get_wave13_modules
        from transcribe.analysis.modules import wordclouds as wordclouds_mod
        from transcribe.analysis.parents import resolve_optional_parents
        from transcribe.analysis.runner import AnalysisRunner, load_published_read_model
        from transcribe.analysis.storage import AnalysisStorage
        from transcribe.ports import SystemClock, UuidGenerator

        st.subheader("Overview")
        st.caption(
            "Read-model of validated published analysis results "
            "(stats, lexical diversity, understandability, wordclouds, "
            "ner, sentiment, epistemic markers)."
        )
        runner = AnalysisRunner(
            projects, clock=SystemClock(), ids=UuidGenerator()
        )
        if st.button("Run analysis (through Wave 1.3)"):
            with st.spinner("Running analysis modules…"):
                from transcribe.analysis.modules import get_wave13_modules

                results = runner.run_batch(list(get_wave13_modules().keys()))
            for mid, env in results.items():
                st.write(
                    f"**{mid}:** outcome=`{env.get('outcome')}` "
                    f"capability=`{env.get('capability')}`"
                )
            st.rerun()

        storage = AnalysisStorage(paths)
        from transcribe.analysis.modules import get_wave13_modules

        modules = get_wave13_modules()
        current_identity: dict[str, str | None] = {}
        try:
            doc = build_page_v1_document(project, projects)
            for mid, module in modules.items():
                config: dict = {}
                lexicon = None
                enrichment = "none"
                cache_fn = getattr(module, "cache_config", None)
                if callable(cache_fn):
                    config = dict(cache_fn())
                if mid == "wordclouds":
                    config = wordclouds_mod.wordclouds_config()
                    lexicon = wordclouds_mod.wordclouds_lexicon_or_model()
                    enrichment = wordclouds_mod.ENRICHMENT_MODE
                elif mid == "ner":
                    from transcribe.analysis.modules import ner as ner_mod

                    lexicon = ner_mod.ner_lexicon_or_model()
                elif mid == "sentiment":
                    from transcribe.analysis.modules import sentiment as sent_mod

                    lexicon = sent_mod.sentiment_lexicon_or_model()
                elif mid == "epistemic_markers":
                    from transcribe.analysis.modules import epistemic_markers as epi_mod

                    lexicon = epi_mod.epistemic_lexicon_or_model()
                parents = resolve_optional_parents(
                    mid, enrichment_mode=enrichment, storage=storage
                )
                current_identity[mid] = cache_identity_hex(
                    build_cache_identity_object(
                        project_id=project.id,
                        module_id=module.module_id,
                        module_version=module.module_version,
                        document=doc,
                        config=config,
                        parents=parents,
                        lexicon_or_model=lexicon,
                    )
                )
        except AnalysisDocumentError:
            for mid in modules:
                current_identity[mid] = None

        for mid in modules:
            model = load_published_read_model(
                storage, mid, current_cache_identity=current_identity.get(mid)
            )
            status = model["status"]
            env = model.get("envelope")
            if status == "unavailable":
                st.warning(f"**{mid}:** unavailable (no validated published result)")
            elif status == "stale":
                st.warning(
                    f"**{mid}:** stale relative to current notebook text "
                    f"(last outcome `{env.get('outcome') if env else '?'}`)"
                )
            elif env is not None:
                cap = env.get("capability")
                outcome = env.get("outcome")
                if outcome == "failed":
                    st.error(f"**{mid}:** failed")
                elif outcome == "insufficient_data":
                    st.info(f"**{mid}:** insufficient_data")
                elif cap in {"unavailable_extra", "unavailable_model"}:
                    st.warning(f"**{mid}:** {cap}")
                elif cap == "partial":
                    st.success(f"**{mid}:** success (partial)")
                else:
                    st.success(f"**{mid}:** success ({cap})")
                payload = env.get("payload") or {}
                if mid == "wordclouds" and outcome == "success":
                    tokens = payload.get("tokens") or []
                    if isinstance(tokens, list) and tokens:
                        chart_rows = {
                            "token": [t.get("token", "") for t in tokens[:40]],
                            "weight": [float(t.get("weight") or 0) for t in tokens[:40]],
                        }
                        st.bar_chart(chart_rows, x="token", y="weight")
                    else:
                        st.warning(
                            f"**{mid}:** published success but token list missing/empty"
                        )
                if mid == "ner" and outcome == "success":
                    counts = payload.get("entity_counts") or {}
                    if counts:
                        items = list(counts.items())[:20]
                        st.bar_chart(
                            {
                                "entity": [k for k, _ in items],
                                "count": [int(v) for _, v in items],
                            },
                            x="entity",
                            y="count",
                        )
                    else:
                        st.caption("No named entities found.")
                if mid == "sentiment" and outcome == "success":
                    units = payload.get("units") or []
                    if units:
                        st.line_chart(
                            {
                                "order": [u.get("order") for u in units],
                                "compound": [float(u.get("compound") or 0) for u in units],
                            },
                            x="order",
                            y="compound",
                        )
                if mid == "epistemic_markers" and outcome == "success":
                    g = payload.get("global_stats") or {}
                    st.caption(
                        f"hedge_share={g.get('hedge_share')} "
                        f"booster_share={g.get('booster_share')} "
                        f"hits={g.get('total_marker_hits')}"
                    )
                evidence = env.get("evidence") or []
                if evidence and mid in {"ner", "epistemic_markers"}:
                    from transcribe.analysis.document import content_fingerprint as cfp

                    try:
                        cur_fp = cfp(build_page_v1_document(project, projects))
                    except Exception:  # noqa: BLE001
                        cur_fp = env.get("content_fingerprint")
                    live = [
                        e
                        for e in evidence
                        if cur_fp is None or e.get("content_fingerprint") == cur_fp
                    ]
                    stale_n = len(evidence) - len(live)
                    if stale_n:
                        st.warning(
                            f"**{mid}:** {stale_n} stale evidence citation(s) hidden"
                        )
                with st.expander(f"{mid} payload"):
                    st.json(payload)
            else:
                st.warning(f"**{mid}:** unavailable")

    with tab_themes:
        from transcribe.analysis.modules import get_wave1c_modules
        from transcribe.analysis.runner import AnalysisRunner, load_published_read_model
        from transcribe.analysis.storage import AnalysisStorage
        from transcribe.ports import SystemClock, UuidGenerator

        st.subheader("Themes")
        st.caption(
            "Keyphrases, topics, semantic motifs, and topic shifts along page order. "
            "BERTopic remains an optional extra (`unavailable_extra` when missing)."
        )
        runner = AnalysisRunner(projects, clock=SystemClock(), ids=UuidGenerator())
        theme_ids = [
            "keyphrases",
            "topic_modeling",
            "semantic_similarity",
            "topic_shift",
            "bertopic",
        ]
        if st.button("Run Themes analysis (Wave 1c)"):
            with st.spinner("Running Themes modules…"):
                results = runner.run_batch(theme_ids)
            for mid in theme_ids:
                env = results.get(mid) or {}
                st.write(
                    f"**{mid}:** outcome=`{env.get('outcome')}` "
                    f"capability=`{env.get('capability')}`"
                )
            st.rerun()

        storage = AnalysisStorage(paths)
        w1c = get_wave1c_modules()
        assert set(theme_ids).issubset(set(w1c))
        for mid in theme_ids:
            rm = load_published_read_model(storage, mid, current_cache_identity=None)
            env = rm.get("envelope")
            if not env:
                st.info(f"**{mid}:** unavailable — run Themes analysis first")
                continue
            cap = env.get("capability")
            banner = f"**{mid}:** capability=`{cap}` outcome=`{env.get('outcome')}`"
            if cap == "unavailable_extra":
                st.warning(banner + " (optional extra not available)")
            elif cap in {"insufficient_data", "skipped_not_applicable"}:
                st.info(banner)
            elif cap == "failed":
                st.error(banner)
            else:
                st.markdown(banner)
            payload = env.get("payload") or {}
            if mid == "keyphrases" and payload.get("phrases"):
                st.write(
                    ", ".join(
                        p.get("phrase", "") for p in payload["phrases"][:12] if p.get("phrase")
                    )
                )
            elif mid == "topic_modeling" and payload.get("topics"):
                for topic in payload["topics"][:5]:
                    terms = ", ".join(topic.get("terms") or [])
                    st.write(f"- **{topic.get('label')}**: {terms}")
            elif mid == "semantic_similarity":
                motifs = payload.get("motifs") or []
                st.caption(
                    f"{payload.get('n_units', 0)} units · {len(motifs)} motif pair(s)"
                )
            elif mid == "topic_shift":
                shifts = payload.get("shifts") or []
                st.caption(
                    f"{payload.get('n_units', 0)} units · {len(shifts)} shift boundary(ies)"
                )
            with st.expander(f"{mid} payload"):
                st.json(payload)

    with tab_mood:
        from transcribe.analysis.runner import AnalysisRunner, load_published_read_model
        from transcribe.analysis.storage import AnalysisStorage
        from transcribe.ports import SystemClock, UuidGenerator

        st.subheader("Mood & tone")
        st.caption(
            "Emotion chronology, contextual smoothing, affect tension, and hedging. "
            "Fine-grained emotion stays an optional extra."
        )
        runner = AnalysisRunner(projects, clock=SystemClock(), ids=UuidGenerator())
        mood_ids = [
            "sentiment",
            "emotion",
            "contextual_emotion",
            "fine_grained_emotion",
            "affect_tension",
            "epistemic_markers",
        ]
        if st.button("Run Mood & tone analysis (Wave 1d)"):
            ordered = [
                "sentiment",
                "emotion",
                "contextual_emotion",
                "fine_grained_emotion",
                "affect_tension",
                "epistemic_markers",
            ]
            with st.spinner("Running Mood modules…"):
                results = runner.run_batch(ordered)
            for mid in mood_ids:
                env = results.get(mid) or {}
                st.write(
                    f"**{mid}:** outcome=`{env.get('outcome')}` "
                    f"capability=`{env.get('capability')}`"
                )
            st.rerun()

        storage = AnalysisStorage(paths)
        for mid in mood_ids:
            rm = load_published_read_model(storage, mid, current_cache_identity=None)
            env = rm.get("envelope")
            if not env:
                st.info(f"**{mid}:** unavailable — run Mood analysis first")
                continue
            cap = env.get("capability")
            banner = f"**{mid}:** capability=`{cap}` outcome=`{env.get('outcome')}`"
            if cap == "unavailable_extra":
                st.warning(banner + " (optional extra not available)")
            elif cap == "unavailable_dependency":
                st.warning(banner + " (run emotion + sentiment first)")
            elif cap in {"insufficient_data", "skipped_not_applicable"}:
                st.info(banner)
            else:
                st.markdown(banner)
            payload = env.get("payload") or {}
            if mid == "emotion" and payload.get("global_stats"):
                st.caption(
                    f"intensity_mean={payload['global_stats'].get('intensity_mean')}"
                )
            elif mid == "affect_tension" and payload.get("global_stats"):
                st.caption(
                    f"tension_mean={payload['global_stats'].get('tension_mean')} · "
                    f"conflicts={payload['global_stats'].get('n_conflicting')}"
                )
            with st.expander(f"{mid} payload"):
                st.json(payload)

    with tab_moments:
        from transcribe.analysis.runner import AnalysisRunner, load_published_read_model
        from transcribe.analysis.storage import AnalysisStorage
        from transcribe.ports import SystemClock, UuidGenerator

        st.subheader("Moments")
        st.caption(
            "Notebook salience fork (no TX momentum). Soft features from emotion, "
            "sentiment, and topic_shift enrich scores when available."
        )
        runner = AnalysisRunner(projects, clock=SystemClock(), ids=UuidGenerator())
        if st.button("Run Moments analysis"):
            ordered = [
                "sentiment",
                "emotion",
                "topic_shift",
                "moments",
            ]
            with st.spinner("Finding moments…"):
                results = runner.run_batch(ordered)
            env = results.get("moments") or {}
            st.write(
                f"**moments:** outcome=`{env.get('outcome')}` "
                f"capability=`{env.get('capability')}`"
            )
            st.rerun()

        storage = AnalysisStorage(paths)
        rm = load_published_read_model(storage, "moments", current_cache_identity=None)
        env = rm.get("envelope")
        if not env:
            st.info("**moments:** unavailable — run Moments analysis first")
        else:
            cap = env.get("capability")
            st.markdown(
                f"**moments:** capability=`{cap}` outcome=`{env.get('outcome')}`"
            )
            payload = env.get("payload") or {}
            for row in payload.get("moments") or []:
                st.write(
                    f"- score=`{row.get('score')}` · `{row.get('quote', '')[:120]}`"
                )
            for w in env.get("warnings") or []:
                st.caption(w.get("message") or w.get("code"))
            with st.expander("moments payload"):
                st.json(payload)

    with tab_summaries:
        from transcribe.analysis.runner import AnalysisRunner, load_published_read_model
        from transcribe.analysis.storage import AnalysisStorage
        from transcribe.ports import SystemClock, UuidGenerator

        st.subheader("Summaries")
        st.caption(
            "Deterministic highlights → summary → insights, plus optional LLM "
            "outputs (honesty-labeled). Works offline when Ollama is down."
        )
        runner = AnalysisRunner(projects, clock=SystemClock(), ids=UuidGenerator())
        storage = AnalysisStorage(paths)
        synth_ids = [
            "topic_modeling",
            "highlights",
            "summary",
            "insights",
            "llm_summary",
            "llm_action_items",
            "narrative_summary",
        ]
        if st.button("Run synthesis & LLM suite"):
            ordered = [
                "ner",
                "sentiment",
                "keyphrases",
                "topic_modeling",
                "highlights",
                "summary",
                "insights",
                "llm_summary",
                "llm_action_items",
                "narrative_summary",
            ]
            with st.spinner("Running synthesis modules…"):
                results = runner.run_batch(ordered)
            for mid in synth_ids:
                env = results.get(mid) or {}
                label = ""
                payload = env.get("payload") or {}
                if payload.get("honesty_label"):
                    label = f" honesty=`{payload['honesty_label']}`"
                st.write(
                    f"**{mid}:** outcome=`{env.get('outcome')}` "
                    f"capability=`{env.get('capability')}`{label}"
                )
            st.rerun()

        for mid in synth_ids:
            rm = load_published_read_model(storage, mid, current_cache_identity=None)
            env = rm.get("envelope")
            if not env:
                st.info(f"**{mid}:** unavailable — run synthesis first")
                continue
            if rm.get("status") == "stale":
                st.warning(
                    f"**{mid}:** published result not verified current "
                    "(pass a live cache identity before treating evidence as fresh)"
                )
            cap = env.get("capability")
            payload = env.get("payload") or {}
            honesty = payload.get("honesty_label")
            banner = f"**{mid}:** capability=`{cap}` outcome=`{env.get('outcome')}`"
            if honesty:
                banner += f" — _{honesty}_"
            if cap == "unavailable_model":
                st.warning(banner + " (LLM offline)")
            else:
                st.markdown(banner)
            with st.expander(f"{mid} payload"):
                st.json(payload)

    with tab_ask:
        from transcribe.analysis.runner import AnalysisRunner, load_published_read_model
        from transcribe.analysis.storage import AnalysisStorage
        from transcribe.ports import SystemClock, UuidGenerator

        st.subheader("Ask notebook")
        st.caption(
            "Grounded QA with unit evidence. Unsupported answers abstain — "
            "no fabricated citations."
        )
        question = st.text_input("Question", key="ask_notebook_question")
        if st.button("Ask", disabled=not (question or "").strip()):
            runner = AnalysisRunner(
                projects, clock=SystemClock(), ids=UuidGenerator()
            )
            with st.spinner("Asking notebook…"):
                env = runner.run_module(
                    "llm_custom_qa", question_text=question.strip()
                )
            st.write(
                f"outcome=`{env.get('outcome')}` capability=`{env.get('capability')}`"
            )
            payload = env.get("payload") or {}
            if payload.get("honesty_label"):
                st.caption(f"Honesty: {payload['honesty_label']}")
            if payload.get("answer"):
                st.markdown(payload["answer"])
            evidence = env.get("evidence") or []
            if evidence and env.get("published"):
                st.json(evidence)
            for w in env.get("warnings") or []:
                st.warning(w.get("message") or w.get("code"))
            with st.expander("Raw payload"):
                st.json(payload)

        storage = AnalysisStorage(paths)
        rm = load_published_read_model(
            storage, "llm_custom_qa", current_cache_identity=None
        )
        if rm.get("envelope"):
            st.divider()
            if rm.get("status") == "stale":
                st.caption(
                    "Last published Ask notebook result (not verified current — "
                    "re-ask to refresh)"
                )
            else:
                st.caption("Last published Ask notebook result")
            st.json((rm["envelope"] or {}).get("payload") or {})


def main() -> None:
    st.set_page_config(page_title="Transcribe", layout="wide")
    st.title("Transcribe")
    st.caption("Local-first handwritten notebook OCR via Ollama")

    runtime = build_runtime_paths()
    runtime.ensure_layout()
    default_root = str(runtime.default_project_dir())
    root = st.sidebar.text_input(
        "Project directory", value=st.session_state.get("root", default_root)
    )
    st.session_state["root"] = root
    st.sidebar.caption(f"Projects root: `{runtime.projects_dir}`")
    st.sidebar.caption(f"Inbox: `{runtime.inbox_dir}`")
    st.sidebar.caption(f"Exports: `{runtime.export_dir}`")

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
            st.session_state["ui_mode"] = "Workflow"
        except TranscribeError as exc:
            st.sidebar.error(str(exc))

    mode = st.sidebar.radio(
        "Mode",
        ["Archive", "Notebooks", "Search", "Workflow"],
        index=["Archive", "Notebooks", "Search", "Workflow"].index(
            st.session_state.get("ui_mode", "Archive")
        )
        if st.session_state.get("ui_mode", "Archive")
        in ["Archive", "Notebooks", "Search", "Workflow"]
        else 0,
    )
    st.session_state["ui_mode"] = mode

    archive = ArchiveService(runtime)
    archive.ensure_index()

    # Page viewer overlay when navigated from Archive/Search/Notebooks.
    if (
        mode != "Workflow"
        and st.session_state.get("show_page_viewer")
        and st.session_state.get("view_page_id")
        and st.session_state.get("root")
    ):
        try:
            return_mode = st.session_state.get("page_return_mode", mode)
            render_page_viewer(
                page_id=st.session_state["view_page_id"],
                page_ids=st.session_state.get("view_page_ids"),
                view_entries=st.session_state.get("view_entries"),
                highlight_query=st.session_state.get("view_highlight", ""),
                back_label=f"Back to {return_mode}",
            )
            return
        except TranscribeError as exc:
            st.error(str(exc))
            st.session_state["show_page_viewer"] = False

    if mode == "Archive":
        render_archive(runtime, archive)
    elif mode == "Notebooks":
        render_notebooks(runtime, archive)
    elif mode == "Search":
        render_search(runtime, archive)
    else:
        _render_workflow(runtime, root)


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
