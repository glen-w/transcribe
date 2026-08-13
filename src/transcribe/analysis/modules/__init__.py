"""Analysis module registry and core module set."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from transcribe.analysis.document import AnalysisDocument


class AnalysisModule(Protocol):
    module_id: str
    module_version: str

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        """Return {outcome, payload, warnings?, partial?, capability_reason?, evidence?}."""
        ...


ModuleFactory = Callable[[], AnalysisModule]

# Internal delivery-slice ids (historical port order). Prefer full core via through=None.
THROUGH_FOUNDATIONS = "1.1"
THROUGH_WORDCLOUDS = "1.2"
THROUGH_OVERVIEW = "1.3"
THROUGH_LANGUAGE = "1.4"
THROUGH_THEMES = "1c"
THROUGH_MOOD = "1d"
THROUGH_SYNTHESIS = "1e.1"
THROUGH_CORE = "1e.2"


def get_registered_modules(*, through: str | None = None) -> dict[str, AnalysisModule]:
    """Return core analysis module instances.

    ``through`` selects a historical delivery slice for tests/partial runs.
    Default (``None``) is the full frozen core set.
    """
    from transcribe.analysis.modules.affect_tension import AffectTensionModule
    from transcribe.analysis.modules.bertopic import BertopicModule
    from transcribe.analysis.modules.contextual_emotion import ContextualEmotionModule
    from transcribe.analysis.modules.emotion import EmotionModule
    from transcribe.analysis.modules.entity_sentiment import EntitySentimentModule
    from transcribe.analysis.modules.epistemic_markers import EpistemicMarkersModule
    from transcribe.analysis.modules.fine_grained_emotion import (
        FineGrainedEmotionModule,
    )
    from transcribe.analysis.modules.highlights import HighlightsModule
    from transcribe.analysis.modules.insights import InsightsModule
    from transcribe.analysis.modules.keyphrases import KeyphrasesModule
    from transcribe.analysis.modules.lexical_diversity import LexicalDiversityModule
    from transcribe.analysis.modules.llm_action_items import LLMActionItemsModule
    from transcribe.analysis.modules.llm_custom_qa import LLMCustomQAModule
    from transcribe.analysis.modules.llm_summary import LLMSummaryModule
    from transcribe.analysis.modules.moments import MomentsModule
    from transcribe.analysis.modules.narrative_summary import NarrativeSummaryModule
    from transcribe.analysis.modules.ner import NERModule
    from transcribe.analysis.modules.semantic_similarity import SemanticSimilarityModule
    from transcribe.analysis.modules.sentiment import SentimentModule
    from transcribe.analysis.modules.stats import StatsModule
    from transcribe.analysis.modules.summary import SummaryModule
    from transcribe.analysis.modules.topic_modeling import TopicModelingModule
    from transcribe.analysis.modules.topic_shift import TopicShiftModule
    from transcribe.analysis.modules.understandability import UnderstandabilityModule
    from transcribe.analysis.modules.wordclouds import WordcloudsModule

    foundations = [StatsModule(), LexicalDiversityModule(), UnderstandabilityModule()]
    wordclouds = [*foundations, WordcloudsModule()]
    overview = [*wordclouds, NERModule(), SentimentModule(), EpistemicMarkersModule()]
    language = [*overview, KeyphrasesModule(), EntitySentimentModule()]
    themes = [
        *language,
        TopicModelingModule(),
        SemanticSimilarityModule(),
        TopicShiftModule(),
        BertopicModule(),
    ]
    mood = [
        *themes,
        EmotionModule(),
        ContextualEmotionModule(),
        FineGrainedEmotionModule(),
        AffectTensionModule(),
        MomentsModule(),
    ]
    synthesis = [*mood, HighlightsModule(), SummaryModule(), InsightsModule()]
    core = [
        *synthesis,
        LLMSummaryModule(),
        LLMActionItemsModule(),
        LLMCustomQAModule(),
        NarrativeSummaryModule(),
    ]

    table = {
        THROUGH_FOUNDATIONS: foundations,
        THROUGH_WORDCLOUDS: wordclouds,
        THROUGH_OVERVIEW: overview,
        THROUGH_LANGUAGE: language,
        THROUGH_THEMES: themes,
        THROUGH_MOOD: mood,
        THROUGH_SYNTHESIS: synthesis,
        THROUGH_CORE: core,
        "1e": core,
        None: core,
    }
    mods = table.get(through, core)
    return {m.module_id: m for m in mods}


def get_core_modules() -> dict[str, AnalysisModule]:
    """Full frozen core module set."""
    return get_registered_modules()
