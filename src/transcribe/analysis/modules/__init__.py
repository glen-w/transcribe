"""Analysis module registry and Wave 1.1 cores."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from transcribe.analysis.document import AnalysisDocument


class AnalysisModule(Protocol):
    module_id: str
    module_version: str

    def run(self, document: AnalysisDocument) -> dict[str, Any]:
        """Return {outcome, payload, warnings?, partial?, capability_reason?}."""
        ...


ModuleFactory = Callable[[], AnalysisModule]


def get_wave11_modules() -> dict[str, AnalysisModule]:
    from transcribe.analysis.modules.lexical_diversity import LexicalDiversityModule
    from transcribe.analysis.modules.stats import StatsModule
    from transcribe.analysis.modules.understandability import UnderstandabilityModule

    mods = [StatsModule(), LexicalDiversityModule(), UnderstandabilityModule()]
    return {m.module_id: m for m in mods}
