"""Diagnostics: workspace corpus-doctor always; notebook doctor when selected."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import ProjectError, TranscribeError
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.corpus_doctor import CorpusDoctorService
from transcribe.services.doctor import DoctorService
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.ui import icons as ic
from transcribe.ui.home import ollama_health_line


def _render_findings(findings) -> None:
    if not findings:
        st.success("No findings.")
        return
    for f in findings:
        line = f"**{f.severity}** `{f.code}` — {f.message}"
        if f.severity == "error":
            st.error(line)
        elif f.severity == "warning":
            st.warning(line)
        else:
            st.info(line)


def render_diagnostics(runtime: RuntimePaths, *, root: str | None) -> None:
    st.caption(ollama_health_line())
    deep = st.checkbox("Deep hashing (slower)", value=False, key="diagnostics_deep")
    if st.button("Run diagnostics", type="primary", key="diagnostics_run", icon=ic.RUN):
        st.session_state["diagnostics_ran"] = True
        st.session_state["diagnostics_deep_used"] = bool(deep)

    if not st.session_state.get("diagnostics_ran"):
        st.info("Run diagnostics to check the workspace corpus and, if selected, this notebook.")
        return

    used_deep = bool(st.session_state.get("diagnostics_deep_used"))
    corpus = CorpusPaths.from_runtime(runtime)
    st.markdown("#### Workspace")
    try:
        report = CorpusDoctorService(corpus).run(deep=used_deep, per_notebook=False)
        if report.ok:
            st.success("Workspace corpus doctor passed.")
        else:
            st.error("Workspace corpus doctor reported errors.")
        _render_findings(report.findings)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Workspace doctor failed: {exc}")

    st.markdown("#### This notebook")
    if not root:
        st.caption("Select a notebook in View to run the notebook doctor.")
        return
    try:
        paths = open_project_paths(Path(root))
        projects = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
        nb_report = DoctorService(paths, projects).run(deep=used_deep)
        if nb_report.ok:
            st.success("Notebook doctor passed.")
        else:
            st.error("Notebook doctor reported errors.")
        _render_findings(nb_report.findings)
    except (ProjectError, TranscribeError, OSError) as exc:
        st.error(str(exc))
