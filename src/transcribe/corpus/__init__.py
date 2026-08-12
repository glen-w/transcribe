"""Workspace corpus package (bulk-import generation foundation).

Heavy orchestrator imports stay lazy via submodule paths to avoid circular
imports with ``transcribe.services.project``.
"""

from __future__ import annotations

from transcribe.corpus.index import (
    CorpusEntry,
    CorpusIndex,
    CorpusIndexStore,
    ordered_corpus_then_notebook_lock,
    validate_corpus_index,
    validate_entry_matches_project,
)
from transcribe.corpus.import_run import (
    ImportRun,
    ImportRunStore,
    compute_plan_fingerprint,
    plans_are_idempotent_retries,
)
from transcribe.corpus.paths import CorpusPaths
from transcribe.corpus.plan import (
    POLICY_CREATE_DUPLICATE_V1,
    POLICY_SKIP_EXISTING_V1,
    ImportPlan,
    ImportPlanItem,
    plan_body_for_fingerprint,
    validate_import_plan,
)

__all__ = [
    "CorpusEntry",
    "CorpusIndex",
    "CorpusIndexStore",
    "CorpusPaths",
    "ImportRun",
    "ImportRunStore",
    "ImportPlan",
    "ImportPlanItem",
    "POLICY_CREATE_DUPLICATE_V1",
    "POLICY_SKIP_EXISTING_V1",
    "compute_plan_fingerprint",
    "ordered_corpus_then_notebook_lock",
    "plan_body_for_fingerprint",
    "plans_are_idempotent_retries",
    "validate_corpus_index",
    "validate_entry_matches_project",
    "validate_import_plan",
]


def __getattr__(name: str):
    if name == "ImportOrchestrator":
        from transcribe.corpus.orchestrator import ImportOrchestrator

        return ImportOrchestrator
    if name == "plan_from_folder":
        from transcribe.corpus.adapters import plan_from_folder

        return plan_from_folder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
