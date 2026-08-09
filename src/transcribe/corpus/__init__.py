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
from transcribe.corpus.paths import CorpusPaths

__all__ = [
    "CorpusEntry",
    "CorpusIndex",
    "CorpusIndexStore",
    "CorpusPaths",
    "ImportRun",
    "ImportRunStore",
    "compute_plan_fingerprint",
    "ordered_corpus_then_notebook_lock",
    "plans_are_idempotent_retries",
    "validate_corpus_index",
    "validate_entry_matches_project",
]
