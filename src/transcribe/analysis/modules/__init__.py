"""Analysis module registry and Wave 1 cores."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from transcribe.analysis.document import AnalysisDocument


class AnalysisModule(Protocol):
    module_id: str
    module_version: str

    def run(self, document: AnalysisDocument, *, parents: dict | None = None) -> dict[str, Any]:
        """Return {outcome, payload, warnings?, partial?, capability_reason?, evidence?}."""
        ...


ModuleFactory = Callable[[], AnalysisModule]

WAVE_1_1 = "1.1"
WAVE_1_2 = "1.2"
WAVE_1_3 = "1.3"
WAVE_1_4 = "1.4"
WAVE_1_C = "1c"
WAVE_1_E1 = "1e.1"
WAVE_1_E2 = "1e.2"


def get_registered_modules(*, wave: str | None = None) -> dict[str, AnalysisModule]:
    """Return module instances for a delivery wave (default: through 1e.2)."""
    from transcribe.analysis.modules.entity_sentiment import EntitySentimentModule
    from transcribe.analysis.modules.epistemic_markers import EpistemicMarkersModule
    from transcribe.analysis.modules.highlights import HighlightsModule
    from transcribe.analysis.modules.insights import InsightsModule
    from transcribe.analysis.modules.keyphrases import KeyphrasesModule
    from transcribe.analysis.modules.lexical_diversity import LexicalDiversityModule
    from transcribe.analysis.modules.llm_action_items import LLMActionItemsModule
    from transcribe.analysis.modules.llm_custom_qa import LLMCustomQAModule
    from transcribe.analysis.modules.llm_summary import LLMSummaryModule
    from transcribe.analysis.modules.narrative_summary import NarrativeSummaryModule
    from transcribe.analysis.modules.ner import NERModule
    from transcribe.analysis.modules.sentiment import SentimentModule
    from transcribe.analysis.modules.stats import StatsModule
    from transcribe.analysis.modules.summary import SummaryModule
    from transcribe.analysis.modules.topic_modeling import TopicModelingModule
    from transcribe.analysis.modules.understandability import UnderstandabilityModule
    from transcribe.analysis.modules.wordclouds import WordcloudsModule

    wave11 = [StatsModule(), LexicalDiversityModule(), UnderstandabilityModule()]
    wave12 = [*wave11, WordcloudsModule()]
    wave13 = [*wave12, NERModule(), SentimentModule(), EpistemicMarkersModule()]
    wave14 = [*wave13, KeyphrasesModule(), EntitySentimentModule()]
    wave1c = [*wave14, TopicModelingModule()]
    wave1e1 = [*wave1c, HighlightsModule(), SummaryModule(), InsightsModule()]
    wave1e2 = [
        *wave1e1,
        LLMSummaryModule(),
        LLMActionItemsModule(),
        LLMCustomQAModule(),
        NarrativeSummaryModule(),
    ]

    table = {
        WAVE_1_1: wave11,
        WAVE_1_2: wave12,
        WAVE_1_3: wave13,
        WAVE_1_4: wave14,
        WAVE_1_C: wave1c,
        WAVE_1_E1: wave1e1,
        WAVE_1_E2: wave1e2,
        "1e": wave1e2,
        None: wave1e2,
    }
    mods = table.get(wave, wave1e2)
    return {m.module_id: m for m in mods}


def get_wave11_modules() -> dict[str, AnalysisModule]:
    return get_registered_modules(wave=WAVE_1_1)


def get_wave12_modules() -> dict[str, AnalysisModule]:
    return get_registered_modules(wave=WAVE_1_2)


def get_wave13_modules() -> dict[str, AnalysisModule]:
    return get_registered_modules(wave=WAVE_1_3)


def get_wave14_modules() -> dict[str, AnalysisModule]:
    return get_registered_modules(wave=WAVE_1_4)


def get_wave1e_modules() -> dict[str, AnalysisModule]:
    return get_registered_modules(wave=WAVE_1_E2)
