"""Typed config subtrees (defaults match shipped behaviour at promotion time)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

ProfileTargetId = Literal["workflow", "ocr", "llm", "export"]
PROFILE_TARGETS: tuple[ProfileTargetId, ...] = ("workflow", "ocr", "llm", "export")


@dataclass(frozen=True)
class PresetPolicyConfig:
    allow_llm: bool = False
    llm_module_ids: tuple[str, ...] = ()
    allow_heavy: bool = False
    heavy_module_ids: tuple[str, ...] = ()
    include_excluded_from_default: bool = False
    module_ids: tuple[str, ...] | None = None
    content_version: int = 1

    def policy_body_dict(self) -> dict[str, Any]:
        """Policy content without content_version (for change detection / fingerprints)."""
        return {
            "allow_llm": self.allow_llm,
            "llm_module_ids": list(self.llm_module_ids),
            "allow_heavy": self.allow_heavy,
            "heavy_module_ids": list(self.heavy_module_ids),
            "include_excluded_from_default": self.include_excluded_from_default,
            "module_ids": None if self.module_ids is None else list(self.module_ids),
        }

    def as_dict(self) -> dict[str, Any]:
        body = self.policy_body_dict()
        body["content_version"] = int(self.content_version)
        return body

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> PresetPolicyConfig:
        if not data:
            return cls()
        mid = data.get("module_ids", None)
        if mid is not None:
            mid = tuple(str(x) for x in mid)
        version_raw = data.get("content_version", 1)
        try:
            content_version = max(1, int(version_raw))
        except (TypeError, ValueError):
            content_version = 1
        return cls(
            allow_llm=bool(data.get("allow_llm", False)),
            llm_module_ids=tuple(str(x) for x in (data.get("llm_module_ids") or ())),
            allow_heavy=bool(data.get("allow_heavy", False)),
            heavy_module_ids=tuple(str(x) for x in (data.get("heavy_module_ids") or ())),
            include_excluded_from_default=bool(
                data.get("include_excluded_from_default", False)
            ),
            module_ids=mid,
            content_version=content_version,
        )


@dataclass(frozen=True)
class UiPresetsConfig:
    quick: PresetPolicyConfig = field(
        default_factory=lambda: PresetPolicyConfig(
            allow_llm=False,
            allow_heavy=False,
            include_excluded_from_default=False,
        )
    )
    balanced: PresetPolicyConfig = field(
        default_factory=lambda: PresetPolicyConfig(
            allow_llm=True,
            llm_module_ids=("llm_summary",),
            allow_heavy=True,
            heavy_module_ids=("semantic_similarity",),
            include_excluded_from_default=False,
        )
    )
    thorough: PresetPolicyConfig = field(
        default_factory=lambda: PresetPolicyConfig(
            allow_llm=True,
            llm_module_ids=(),
            allow_heavy=True,
            heavy_module_ids=(),
            include_excluded_from_default=True,
        )
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "quick": self.quick.as_dict(),
            "balanced": self.balanced.as_dict(),
            "thorough": self.thorough.as_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> UiPresetsConfig:
        data = data or {}
        return cls(
            quick=PresetPolicyConfig.from_dict(data.get("quick")),
            balanced=PresetPolicyConfig.from_dict(data.get("balanced")),
            thorough=PresetPolicyConfig.from_dict(data.get("thorough")),
        )


@dataclass(frozen=True)
class KeyphrasesConfig:
    top_n: int = 25

    def as_dict(self) -> dict[str, Any]:
        return {"top_n": self.top_n}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> KeyphrasesConfig:
        data = data or {}
        return cls(top_n=int(data.get("top_n", 25)))


@dataclass(frozen=True)
class HighlightsConfig:
    top_n: int = 12

    def as_dict(self) -> dict[str, Any]:
        return {"top_n": self.top_n}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> HighlightsConfig:
        data = data or {}
        return cls(top_n=int(data.get("top_n", 12)))


@dataclass(frozen=True)
class MomentsConfig:
    top_n: int = 10

    def as_dict(self) -> dict[str, Any]:
        return {"top_n": self.top_n}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> MomentsConfig:
        data = data or {}
        return cls(top_n=int(data.get("top_n", 10)))


@dataclass(frozen=True)
class SemanticSimilarityConfig:
    motif_threshold: float = 0.55
    max_motifs: int = 25

    def as_dict(self) -> dict[str, Any]:
        return {
            "motif_threshold": self.motif_threshold,
            "max_motifs": self.max_motifs,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> SemanticSimilarityConfig:
        data = data or {}
        return cls(
            motif_threshold=float(data.get("motif_threshold", 0.55)),
            max_motifs=int(data.get("max_motifs", 25)),
        )


@dataclass(frozen=True)
class TopicShiftConfig:
    shift_threshold: float = 0.25

    def as_dict(self) -> dict[str, Any]:
        return {"shift_threshold": self.shift_threshold}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> TopicShiftConfig:
        data = data or {}
        return cls(shift_threshold=float(data.get("shift_threshold", 0.25)))


@dataclass(frozen=True)
class WordcloudsConfig:
    max_tokens: int = 100
    min_token_length: int = 2

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "min_token_length": self.min_token_length,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> WordcloudsConfig:
        data = data or {}
        return cls(
            max_tokens=int(data.get("max_tokens", 100)),
            min_token_length=int(data.get("min_token_length", 2)),
        )


@dataclass(frozen=True)
class TopicModelingConfig:
    n_topics: int = 5
    terms_per_topic: int = 8

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_topics": self.n_topics,
            "terms_per_topic": self.terms_per_topic,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> TopicModelingConfig:
        data = data or {}
        return cls(
            n_topics=int(data.get("n_topics", 5)),
            terms_per_topic=int(data.get("terms_per_topic", 8)),
        )


@dataclass(frozen=True)
class AnalysisConfig:
    ui_presets: UiPresetsConfig = field(default_factory=UiPresetsConfig)
    keyphrases: KeyphrasesConfig = field(default_factory=KeyphrasesConfig)
    highlights: HighlightsConfig = field(default_factory=HighlightsConfig)
    moments: MomentsConfig = field(default_factory=MomentsConfig)
    semantic_similarity: SemanticSimilarityConfig = field(
        default_factory=SemanticSimilarityConfig
    )
    topic_shift: TopicShiftConfig = field(default_factory=TopicShiftConfig)
    wordclouds: WordcloudsConfig = field(default_factory=WordcloudsConfig)
    topic_modeling: TopicModelingConfig = field(default_factory=TopicModelingConfig)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ui_presets": self.ui_presets.as_dict(),
            "keyphrases": self.keyphrases.as_dict(),
            "highlights": self.highlights.as_dict(),
            "moments": self.moments.as_dict(),
            "semantic_similarity": self.semantic_similarity.as_dict(),
            "topic_shift": self.topic_shift.as_dict(),
            "wordclouds": self.wordclouds.as_dict(),
            "topic_modeling": self.topic_modeling.as_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> AnalysisConfig:
        data = data or {}
        return cls(
            ui_presets=UiPresetsConfig.from_dict(data.get("ui_presets")),
            keyphrases=KeyphrasesConfig.from_dict(data.get("keyphrases")),
            highlights=HighlightsConfig.from_dict(data.get("highlights")),
            moments=MomentsConfig.from_dict(data.get("moments")),
            semantic_similarity=SemanticSimilarityConfig.from_dict(
                data.get("semantic_similarity")
            ),
            topic_shift=TopicShiftConfig.from_dict(data.get("topic_shift")),
            wordclouds=WordcloudsConfig.from_dict(data.get("wordclouds")),
            topic_modeling=TopicModelingConfig.from_dict(data.get("topic_modeling")),
        )


@dataclass(frozen=True)
class LlmConfig:
    default_temperature: float = 0.0
    num_predict: int = 1024
    max_unit_tokens: int = 1500
    max_prompt_tokens: int = 6000
    text_model_preference: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "default_temperature": self.default_temperature,
            "num_predict": self.num_predict,
            "max_unit_tokens": self.max_unit_tokens,
            "max_prompt_tokens": self.max_prompt_tokens,
            "text_model_preference": self.text_model_preference,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> LlmConfig:
        data = data or {}
        return cls(
            default_temperature=float(data.get("default_temperature", 0.0)),
            num_predict=int(data.get("num_predict", 1024)),
            max_unit_tokens=int(data.get("max_unit_tokens", 1500)),
            max_prompt_tokens=int(data.get("max_prompt_tokens", 6000)),
            text_model_preference=str(data.get("text_model_preference") or ""),
        )


@dataclass(frozen=True)
class OcrWorkspaceConfig:
    """Workspace OCR defaults for new projects only (not live project authority)."""

    base_url: str = ""
    prompt_id: str = "faithful_markdown"
    language: str = "en"
    preprocess_profile: str = "none"
    max_workers: int = 1
    cleanup_enabled: bool = False
    cleanup_mode: str = "strip_leak"
    cleanup_model_name: str = ""
    text_model_name: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "prompt_id": self.prompt_id,
            "language": self.language,
            "preprocess_profile": self.preprocess_profile,
            "max_workers": self.max_workers,
            "cleanup_enabled": self.cleanup_enabled,
            "cleanup_mode": self.cleanup_mode,
            "cleanup_model_name": self.cleanup_model_name,
            "text_model_name": self.text_model_name,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> OcrWorkspaceConfig:
        data = data or {}
        return cls(
            base_url=str(data.get("base_url") or ""),
            prompt_id=str(data.get("prompt_id") or "faithful_markdown"),
            language=str(data.get("language") or "en"),
            preprocess_profile=str(data.get("preprocess_profile") or "none"),
            max_workers=int(data.get("max_workers", 1)),
            cleanup_enabled=bool(data.get("cleanup_enabled", False)),
            cleanup_mode=str(data.get("cleanup_mode") or "strip_leak"),
            cleanup_model_name=str(data.get("cleanup_model_name") or ""),
            text_model_name=str(data.get("text_model_name") or ""),
        )


@dataclass(frozen=True)
class IngestConfig:
    """Workspace ingest defaults (PDF rasterisation, visual declutter, etc.)."""

    render_dpi: int = 200
    visual_declutter_enabled: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "render_dpi": self.render_dpi,
            "visual_declutter_enabled": self.visual_declutter_enabled,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> IngestConfig:
        data = data or {}
        dpi = int(data.get("render_dpi", 200))
        if dpi < 72:
            dpi = 72
        elif dpi > 600:
            dpi = 600
        # Missing key resolves to the intended default (on).
        declutter = data.get("visual_declutter_enabled", True)
        return cls(
            render_dpi=dpi,
            visual_declutter_enabled=bool(declutter),
        )

KNOWN_CONFIG_SUBTREES: frozenset[str] = frozenset(
    {"analysis", "llm", "ocr", "ingest", "export"}
)


@dataclass(frozen=True)
class ProfileActivations:
    workflow: str = "default"
    ocr: str = "default"
    llm: str = "default"
    export: str = "default"

    def as_dict(self) -> dict[str, Any]:
        return {
            "active_workflow_profile": self.workflow,
            "active_ocr_profile": self.ocr,
            "active_llm_profile": self.llm,
            "active_export_profile": self.export,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> ProfileActivations:
        data = data or {}
        return cls(
            workflow=str(data.get("active_workflow_profile") or "default"),
            ocr=str(data.get("active_ocr_profile") or "default"),
            llm=str(data.get("active_llm_profile") or "default"),
            export=str(data.get("active_export_profile") or "default"),
        )


def _default_export_config() -> Any:
    from transcribe.services.export_options import ExportConfig

    return ExportConfig()


@dataclass(frozen=True)
class EffectiveConfig:
    """Immutable resolved configuration for UI and operation snapshots."""

    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    ocr: OcrWorkspaceConfig = field(default_factory=OcrWorkspaceConfig)
    ingest: IngestConfig = field(default_factory=IngestConfig)
    export: Any = field(default_factory=_default_export_config)
    activations: ProfileActivations = field(default_factory=ProfileActivations)

    def as_dict(self) -> dict[str, Any]:
        return {
            "analysis": self.analysis.as_dict(),
            "llm": self.llm.as_dict(),
            "ocr": self.ocr.as_dict(),
            "ingest": self.ingest.as_dict(),
            "export": self.export.as_dict(),
            **self.activations.as_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> EffectiveConfig:
        from transcribe.services.export_options import ExportConfig

        data = data or {}
        return cls(
            analysis=AnalysisConfig.from_dict(data.get("analysis")),
            llm=LlmConfig.from_dict(data.get("llm")),
            ocr=OcrWorkspaceConfig.from_dict(data.get("ocr")),
            ingest=IngestConfig.from_dict(data.get("ingest")),
            export=ExportConfig.from_dict(data.get("export")),
            activations=ProfileActivations.from_dict(data),
        )


def deep_merge_dict(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Merge nested dicts; overlay wins. Non-dict values replace."""
    out = dict(base)
    for key, value in overlay.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, Mapping)
            and not isinstance(value, (str, bytes))
        ):
            out[key] = deep_merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def workspace_document(
    *,
    config: Mapping[str, Any],
    activations: ProfileActivations,
    schema_version: int,
) -> dict[str, Any]:
    from transcribe.config.versions import SETTINGS_FORMAT

    body = dict(config)
    body.update(activations.as_dict())
    return {
        "format": SETTINGS_FORMAT,
        "schema_version": schema_version,
        "config": {
            "analysis": body.get("analysis", {}),
            "llm": body.get("llm", {}),
            "ocr": body.get("ocr", {}),
            "ingest": body.get("ingest", {}),
            "export": body.get("export", {}),
        },
        "active_workflow_profile": activations.workflow,
        "active_ocr_profile": activations.ocr,
        "active_llm_profile": activations.llm,
        "active_export_profile": activations.export,
    }


def strip_unknown_config_keys(data: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only known top-level config subtrees for write validate."""
    return {
        "analysis": dict(data.get("analysis") or {}),
        "llm": dict(data.get("llm") or {}),
        "ocr": dict(data.get("ocr") or {}),
        "ingest": dict(data.get("ingest") or {}),
        "export": dict(data.get("export") or {}),
    }


def empty_config_dict() -> dict[str, Any]:
    """Empty workspace config skeleton (all known subtrees)."""
    return {key: {} for key in sorted(KNOWN_CONFIG_SUBTREES)}
