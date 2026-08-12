"""Import recovery / inbox — recent ImportRun outcomes for the corpus."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from transcribe.corpus.adapters import (
    OVERWRITE_CONFIRM_PHRASE,
    ON_EXISTING_OVERWRITE,
    ON_EXISTING_SKIP,
    plan_from_folder,
    plan_from_folders,
    scan_folder_notebooks,
)
from transcribe.corpus.folder_overwrite import prepare_folder_overwrite
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


def _policy_id(policy: str) -> str:
    return (
        POLICY_CREATE_DUPLICATE_V1
        if policy == "create_duplicate_v1"
        else POLICY_SKIP_EXISTING_V1
    )


def _render_single_folder(
    corpus: CorpusPaths,
    orchestrator: ImportOrchestrator,
    runtime: RuntimePaths,
    *,
    ids: UuidGenerator,
) -> None:
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
    if cols[1].button("Run bulk import", type="primary", key="import_inbox_run_single"):
        folder = Path(folder_text.strip()) if folder_text.strip() else None
        if folder is None:
            st.error("Enter a folder path.")
        else:
            try:
                plan = plan_from_folder(
                    folder,
                    ids=ids,
                    title=title.strip() or None,
                    import_policy_id=_policy_id(policy),
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


def _render_parent_folders(
    corpus: CorpusPaths,
    orchestrator: ImportOrchestrator,
    runtime: RuntimePaths,
    *,
    clock: SystemClock,
    ids: UuidGenerator,
) -> None:
    st.markdown("#### Import folders (one notebook each)")
    st.caption(
        "Each immediate child folder with JPEG/PNG/PDF files becomes a notebook "
        "named after that folder. Nested folders and loose files in the parent are ignored."
    )
    parent_text = st.text_input(
        "Parent folder path",
        key="import_inbox_parent",
        help="Absolute path to a directory whose child folders become notebooks",
    )
    policy = st.selectbox(
        "Duplicate policy (within each notebook)",
        options=["skip_existing_v1", "create_duplicate_v1"],
        format_func=lambda p: (
            "Skip duplicates already in the target notebook"
            if p == "skip_existing_v1"
            else "Always create new pages even when bytes match"
        ),
        key="import_inbox_folders_policy",
    )
    on_existing = st.radio(
        "On existing notebooks (same folder name already imported)",
        options=[ON_EXISTING_SKIP, ON_EXISTING_OVERWRITE],
        format_func=lambda m: (
            "Skip already-imported folders"
            if m == ON_EXISTING_SKIP
            else "Overwrite already-imported folders"
        ),
        key="import_inbox_on_existing",
        horizontal=True,
    )
    dry = st.checkbox(
        "Preview only (do not commit or delete)",
        key="import_inbox_folders_dry",
    )

    parent = Path(parent_text.strip()) if parent_text.strip() else None
    scan = None
    if parent is not None:
        try:
            scan = scan_folder_notebooks(parent, corpus)
        except (TranscribeError, ValidationError, OSError) as exc:
            st.error(str(exc))
            scan = None

    if scan is not None:
        st.write(
            f"**Scan** · new `{len(scan.new_folders)}` · "
            f"already imported `{len(scan.already_imported)}` · "
            f"empty skipped `{len(scan.empty_skipped)}`"
        )
        if scan.new_folders:
            st.caption(
                "New: " + ", ".join(f"`{p.name}`" for p in scan.new_folders)
            )
        if scan.already_imported:
            st.markdown("**Already imported**")
            for conflict in scan.already_imported:
                st.write(
                    f"- `{conflict.managed_relpath}` · "
                    f"notebook `{conflict.notebook_id}` · {conflict.title}"
                )
        if scan.empty_skipped:
            st.caption(
                "Empty skipped: "
                + ", ".join(f"`{p.name}`" for p in scan.empty_skipped)
            )

    confirm_text = ""
    overwrite_ready = True
    if (
        on_existing == ON_EXISTING_OVERWRITE
        and scan is not None
        and scan.already_imported
    ):
        st.warning(
            "Overwrite permanently deletes the managed notebook directories for the "
            "folders listed above (imported copies under the projects directory). "
            "External originals outside that directory are not touched."
        )
        confirm_text = st.text_input(
            f'Type {OVERWRITE_CONFIRM_PHRASE} to enable overwrite',
            key="import_inbox_overwrite_confirm",
        )
        overwrite_ready = confirm_text == OVERWRITE_CONFIRM_PHRASE
        if not overwrite_ready and not dry:
            st.caption("Run is disabled until the confirmation phrase matches exactly.")

    run_disabled = (
        parent is None
        or (
            on_existing == ON_EXISTING_OVERWRITE
            and scan is not None
            and bool(scan.already_imported)
            and not dry
            and not overwrite_ready
        )
    )
    if st.button(
        "Run folders import",
        type="primary",
        key="import_inbox_run_folders",
        disabled=run_disabled,
    ):
        if parent is None:
            st.error("Enter a parent folder path.")
            return
        try:
            plan, plan_scan = plan_from_folders(
                parent,
                ids=ids,
                corpus_paths=corpus,
                import_policy_id=_policy_id(policy),
                on_existing=on_existing,
            )
            notebooks: dict[str, list] = {}
            for item in plan.items:
                notebooks.setdefault(item.notebook_id, []).append(item)
            st.write(
                f"Plan `{plan.plan_id}` · {len(plan.items)} item(s) · "
                f"{len(notebooks)} notebook(s) · policy `{plan.import_policy_id}`"
            )
            for nb_id, items in notebooks.items():
                title = (items[0].provenance or {}).get("title") or nb_id
                st.caption(
                    f"`{title}` · id `{nb_id}` · {len(items)} source(s) · "
                    f"{sum(len(i.page_indexes) for i in items)} page(s)"
                )
            if dry:
                return
            if on_existing == ON_EXISTING_OVERWRITE and plan_scan.already_imported:
                prepare_folder_overwrite(
                    plan_scan.already_imported,
                    corpus,
                    confirm=confirm_text,
                    clock=clock,
                )
                st.info(
                    f"Wiped {len(plan_scan.already_imported)} existing managed notebook(s)."
                )
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


def render_import_inbox(runtime: RuntimePaths) -> None:
    """Corpus import recovery: plan folder(s), list runs, resume failures."""
    st.caption(
        "Bulk import scans into new notebooks, then review what committed, "
        "skipped, or failed. Single-file import remains under Workflow → Import."
    )
    corpus = CorpusPaths.from_runtime(runtime)
    clock, ids = SystemClock(), UuidGenerator()
    orchestrator = ImportOrchestrator(corpus, clock=clock, ids=ids)

    mode = st.radio(
        "Import mode",
        options=["single", "folders"],
        format_func=lambda m: (
            "One folder → one notebook"
            if m == "single"
            else "Parent of folders → one notebook each"
        ),
        key="import_inbox_mode",
        horizontal=True,
    )
    if mode == "folders":
        _render_parent_folders(
            corpus, orchestrator, runtime, clock=clock, ids=ids
        )
    else:
        _render_single_folder(corpus, orchestrator, runtime, ids=ids)

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
