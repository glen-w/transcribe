"""Optional-parent resolution (must run before cache identity construction)."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.storage import AnalysisStorage

# Wave 1.2: wordclouds baseline never consumes keyphrases.
_BASELINE_NEVER_CONSUME = frozenset({"wordclouds"})


def resolve_optional_parents(
    module_id: str,
    *,
    enrichment_mode: str,
    storage: AnalysisStorage,
) -> list[dict[str, Any]]:
    """Return parents actually consumed for identity.

    For ``wordclouds`` with ``enrichment_mode == "baseline"``, always returns ``[]``
    even when a compatible published ``keyphrases`` success exists.
    """
    if module_id in _BASELINE_NEVER_CONSUME and enrichment_mode == "baseline":
        # Explicitly ignore ambient keyphrases (absent / incompatible / failed / success).
        _ = storage.read_published("keyphrases")
        return []
    return []
