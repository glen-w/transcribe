"""Workspace corpus package (bulk-import generation foundation)."""

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
from transcribe.corpus.orchestrator import ImportOrchestrator
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
    "ImportOrchestrator",
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
