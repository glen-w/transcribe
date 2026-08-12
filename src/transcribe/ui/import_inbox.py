"""Import recovery / inbox — recent ImportRun outcomes for the corpus."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from transcribe.corpus.adapters import plan_from_folder
from transcribe.corpus.import_run import ImportRun, ImportRunStore, TERMINAL_STATUSES
from transcribe.corpus.orchestrator import ImportOrchestrator
from transcribe.corpus.paths import CorpusPaths
from transcribe.corpus.plan import POLICY_CREATE_DUPLICATE_V1, POLICY_SKIP_EXISTING_V1
from transcribe.errors import TranscribeError, ValidationError
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.archive import bump_archive_generation


def _list_runs(corpus: CorpusPaths) -> list[ImportRun]:
    if not corpus.import_runs_dir.is_dir():
        return []
    store = ImportRunStore(corpus)
    runs: list[ImportRun] = []
    for path in sorted(corpus.import_runs_dir.glob("*.json"), reverse=True):
        try:
            runs.append(store.load(path.stem))
        except Exception:  # noqa: BLE001 — skip corrupt run files in inbox
            continue
    return runs


def render_import_inbox(runtime: RuntimePaths) -> None:
    """Corpus import recovery: plan a folder, list runs, resume failures."""
    st.caption(
        "Bulk import a folder of scans into a new notebook, then review what "
        "committed, skipped, or failed. Single-file import remains under Workflow → Import."
    )
    corpus = CorpusPaths.from_runtime(runtime)
    clock, ids = SystemClock(), UuidGenerator()
    orchestrator = ImportOrchestrator(corpus, clock=clock, ids=ids)

    st.markdown("#### Import folder")
    folder_text = st.text_input(
        "Folder path",
        key="import_inbox_folder",
        help="Absolute path to a folder of JPEG / PNG / PDF files",
    )
    policy = st.selectbox(
        "Duplicate policy",
        options=["skip_existing_v1", "create_duplicate_v1"],
        format_func=lambda p: (
            "Skip duplicates already in the target notebook"
            if p == "skip_existing_v1"
            else "Always create new pages even when bytes match"
        ),
        key="import_inbox_policy",
    )
    title = st.text_input("Notebook title (optional)", key="import_inbox_title")
    cols = st.columns(2)
    dry = cols[0].checkbox("Preview only (do not commit)", key="import_inbox_dry")
    if cols[1].button("Run bulk import", type="primary"):
        folder = Path(folder_text.strip()) if folder_text.strip() else None
        if folder is None:
            st.error("Enter a folder path.")
        else:
            try:
                plan = plan_from_folder(
                    folder,
                    ids=ids,
                    title=title.strip() or None,
                    import_policy_id=(
                        POLICY_CREATE_DUPLICATE_V1
                        if policy == "create_duplicate_v1"
                        else POLICY_SKIP_EXISTING_V1
                    ),
                )
                st.write(
                    f"Plan `{plan.plan_id}` · {len(plan.items)} item(s) · "
                    f"policy `{plan.import_policy_id}`"
                )
                for item in plan.items:
                    st.caption(
                        f"{item.op} · {item.original_filename or item.item_id} · "
                        f"{len(item.page_indexes)} page(s)"
                    )
                if not dry:
                    run = orchestrator.create_run_from_plan(plan)
                    completed = orchestrator.commit_run(run.import_run_id)
                    bump_archive_generation(runtime)
                    st.success(
                        f"Import run `{completed.import_run_id}` → **{completed.status}**"
                    )
                    st.session_state["import_inbox_flash_run"] = completed.import_run_id
                    st.rerun()
            except (TranscribeError, ValidationError, OSError) as exc:
                st.error(str(exc))

    st.divider()
    st.markdown("#### Recent import runs")
    flash = st.session_state.pop("import_inbox_flash_run", None)
    if flash:
        st.info(f"Updated run `{flash}`")

    runs = _list_runs(corpus)
    if not runs:
        st.caption("No ImportRun records yet.")
        return

    for run in runs[:20]:
        committed = sum(1 for i in run.items if i.state == "committed")
        skipped = sum(1 for i in run.items if i.state == "skipped")
        failed = sum(1 for i in run.items if i.state == "failed")
        pending = sum(1 for i in run.items if i.state == "pending")
        with st.expander(
            f"`{run.import_run_id}` · {run.status} · "
            f"{committed} ok / {skipped} skipped / {failed} failed / {pending} pending",
            expanded=run.import_run_id == flash,
        ):
            st.caption(
                f"plan `{run.plan_id}` · policy `{run.import_policy_id}` · "
                f"updated {run.updated_at}"
            )
            for item in run.items:
                bits = [item.state]
                if item.skip_classification:
                    bits.append(item.skip_classification)
                if item.error_message:
                    bits.append(item.error_message)
                st.write(f"- `{item.item_id}` · " + " · ".join(bits))
            if run.status not in TERMINAL_STATUSES or pending:
                if st.button("Resume", key=f"resume_{run.import_run_id}"):
                    try:
                        completed = orchestrator.commit_run(run.import_run_id)
                        bump_archive_generation(runtime)
                        st.success(f"Resumed → **{completed.status}**")
                        st.rerun()
                    except (TranscribeError, ValidationError, OSError) as exc:
                        st.error(str(exc))
