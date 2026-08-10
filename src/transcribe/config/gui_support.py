"""Curated guided-edit schema for Settings → Configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommonSettingField:
    key: str
    group: str
    label: str


COMMON_SETTINGS_SCHEMA: tuple[CommonSettingField, ...] = (
    CommonSettingField("ingest.render_dpi", "Import", "PDF render DPI"),
    CommonSettingField(
        "ingest.visual_declutter_enabled",
        "Import",
        "Visual declutter on import",
    ),
    CommonSettingField("ocr.base_url", "OCR defaults", "Default Ollama base URL"),
    CommonSettingField("ocr.preprocess_profile", "OCR defaults", "Preprocess profile"),
    CommonSettingField("ocr.max_workers", "OCR defaults", "Max OCR workers"),
    CommonSettingField("ocr.cleanup_enabled", "OCR defaults", "Cleanup enabled"),
    CommonSettingField("ocr.cleanup_mode", "OCR defaults", "Cleanup mode"),
    CommonSettingField("llm.default_temperature", "LLM", "Default temperature"),
    CommonSettingField("llm.num_predict", "LLM", "Max predict tokens"),
    CommonSettingField("llm.max_unit_tokens", "LLM", "Max unit tokens"),
    CommonSettingField("llm.max_prompt_tokens", "LLM", "Max prompt tokens"),
    CommonSettingField("llm.text_model_preference", "LLM", "Preferred text model"),
    CommonSettingField("analysis.keyphrases.top_n", "Analysis", "Keyphrases top N"),
    CommonSettingField("analysis.highlights.top_n", "Analysis", "Highlights top N"),
    CommonSettingField("analysis.moments.top_n", "Analysis", "Moments top N"),
    CommonSettingField(
        "analysis.semantic_similarity.motif_threshold",
        "Analysis",
        "Semantic motif threshold",
    ),
    CommonSettingField(
        "analysis.topic_shift.shift_threshold",
        "Analysis",
        "Topic-shift threshold",
    ),
    CommonSettingField("analysis.wordclouds.max_tokens", "Analysis", "Wordcloud max tokens"),
    CommonSettingField(
        "analysis.topic_modeling.n_topics",
        "Analysis",
        "Topic modeling topic count",
    ),
)
