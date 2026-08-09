"""Analysis module registry and Wave 1 cores."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from transcribe.analysis.document import AnalysisDocument


class AnalysisModule(Protocol):
    module_id: str
    module_version: str

    def run(self, document: AnalysisDocument) -> dict[str, Any]:
        """Return {outcome, payload, warnings?, partial?, capability_reason?, evidence?}."""
        ...


ModuleFactory = Callable[[], AnalysisModule]

WAVE_1_1 = "1.1"
WAVE_1_2 = "1.2"
WAVE_1_3 = "1.3"


def get_registered_modules(*, wave: str | None = None) -> dict[str, AnalysisModule]:
    """Return module instances for a delivery wave (default: through 1.3)."""
    from transcribe.analysis.modules.epistemic_markers import EpistemicMarkersModule
    from transcribe.analysis.modules.lexical_diversity import LexicalDiversityModule
    from transcribe.analysis.modules.ner import NERModule
    from transcribe.analysis.modules.sentiment import SentimentModule
    from transcribe.analysis.modules.stats import StatsModule
    from transcribe.analysis.modules.understandability import UnderstandabilityModule
    from transcribe.analysis.modules.wordclouds import WordcloudsModule

    wave11 = [StatsModule(), LexicalDiversityModule(), UnderstandabilityModule()]
    wave12 = [*wave11, WordcloudsModule()]
    wave13 = [*wave12, NERModule(), SentimentModule(), EpistemicMarkersModule()]
    if wave == WAVE_1_1:
        mods = wave11
    elif wave == WAVE_1_2:
        mods = wave12
    else:
        # Default and "1.3" include Language foundations.
        mods = wave13
    return {m.module_id: m for m in mods}


def get_wave11_modules() -> dict[str, AnalysisModule]:
    """Backward-compatible alias: Wave 1.1 three modules only."""
    return get_registered_modules(wave=WAVE_1_1)


def get_wave12_modules() -> dict[str, AnalysisModule]:
    """Wave 1.1 + baseline wordclouds."""
    return get_registered_modules(wave=WAVE_1_2)


def get_wave13_modules() -> dict[str, AnalysisModule]:
    """Through Wave 1.3 Language foundations."""
    return get_registered_modules(wave=WAVE_1_3)
