"""Domain dataclasses and (de)serialization for persisted formats."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from transcribe.domain.dates import (
    ApproximateDate,
    canonicalize_page_date_state,
    normalize_tags,
    page_date_fields_from_dict,
)

PROVIDER_METADATA_ALLOWLIST = frozenset(
    {
        "total_duration",
        "load_duration",
        "prompt_eval_count",
        "eval_count",
        "retry_count",
        "prompt_eval_duration",
        "eval_duration",
        "truncated",
    }
)


def filter_provider_metadata(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in PROVIDER_METADATA_ALLOWLIST:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, float) and value != value:  # NaN
                continue
            out[key] = value
    return out


# Safety cap for vision OCR generate. Analysis uses workspace llm.num_predict.
DEFAULT_VISION_NUM_PREDICT = 4096


def _parse_vision_num_predict(raw: Any) -> int:
    if raw is None or raw == "":
        return DEFAULT_VISION_NUM_PREDICT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_VISION_NUM_PREDICT
    if value < 64 or value > 8192:
        return DEFAULT_VISION_NUM_PREDICT
    return value


@dataclass
class GenerationOptions:
    temperature: float = 0.0
    num_predict: int = DEFAULT_VISION_NUM_PREDICT
    # Keep extensible but fingerprint-stable via as_dict / fingerprint helper

    def as_dict(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "num_predict": int(self.num_predict),
        }


CLEANUP_MODES = frozenset({"strip_leak", "sanitize_light", "rewrite"})

PREFER_MODES = frozenset(
    {
        "prefer_is_promote",
        "prefer_only",
        "prefer_promote_with_edit_gate",
    }
)
DEFAULT_PREFER_MODE = "prefer_is_promote"
ATTEMPT_KINDS = frozenset({"vision", "composite"})
EDIT_GATE_CHOICES = frozenset({"keep_edit", "adopt_new"})


@dataclass
class OCRSettings:
    model_name: str = ""
    text_model_name: str = ""
    base_url: str = "http://localhost:11434"
    prompt_id: str = "faithful_markdown"
    custom_prompt: str | None = None
    language: str = "en"
    preprocess_profile: str = "none"
    max_workers: int = 1
    generation_options: GenerationOptions = field(default_factory=GenerationOptions)
    allow_non_loopback: bool = False
    cleanup_enabled: bool = False
    cleanup_mode: str = "strip_leak"
    cleanup_model_name: str = ""
    prefer_mode: str = DEFAULT_PREFER_MODE
    auto_activate_composite: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "text_model_name": self.text_model_name,
            "base_url": self.base_url,
            "prompt_id": self.prompt_id,
            "custom_prompt": self.custom_prompt,
            "language": self.language,
            "preprocess_profile": self.preprocess_profile,
            "max_workers": self.max_workers,
            "generation_options": self.generation_options.as_dict(),
            "allow_non_loopback": self.allow_non_loopback,
            "cleanup_enabled": self.cleanup_enabled,
            "cleanup_mode": self.cleanup_mode,
            "cleanup_model_name": self.cleanup_model_name,
            "prefer_mode": self.prefer_mode,
            "auto_activate_composite": self.auto_activate_composite,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCRSettings:
        opts = data.get("generation_options") or {}
        mode = str(data.get("cleanup_mode") or "strip_leak")
        if mode not in CLEANUP_MODES:
            mode = "strip_leak"
        prefer = str(data.get("prefer_mode") or DEFAULT_PREFER_MODE)
        if prefer not in PREFER_MODES:
            prefer = DEFAULT_PREFER_MODE
        return cls(
            model_name=data.get("model_name", ""),
            text_model_name=data.get("text_model_name", ""),
            base_url=data.get("base_url", "http://localhost:11434"),
            prompt_id=data.get("prompt_id", "faithful_markdown"),
            custom_prompt=data.get("custom_prompt"),
            language=data.get("language", "en"),
            preprocess_profile=data.get("preprocess_profile", "none"),
            max_workers=int(data.get("max_workers", 1)),
            generation_options=GenerationOptions(
                temperature=float(opts.get("temperature", 0.0)),
                num_predict=_parse_vision_num_predict(opts.get("num_predict")),
            ),
            allow_non_loopback=bool(data.get("allow_non_loopback", False)),
            cleanup_enabled=bool(data.get("cleanup_enabled", False)),
            cleanup_mode=mode,
            cleanup_model_name=str(data.get("cleanup_model_name") or ""),
            prefer_mode=prefer,
            auto_activate_composite=bool(data.get("auto_activate_composite", True)),
        )


@dataclass
class CleanupRecord:
    """Post-OCR cleanup outcome; never alters OCRAttempt.status semantics."""

    execution_status: str
    acceptance_status: str
    mode: str | None = None
    model_name: str | None = None
    model_digest: str | None = None
    prompt_id: str | None = None
    prompt_version: str | None = None
    prompt_sha256: str | None = None
    note: str | None = None
    pre_cleanup_text: str | None = None
    original_length: int | None = None
    candidate_length: int | None = None
    length_ratio: float | None = None
    cleanup_validator_policy_id: str | None = None
    cleanup_validator_policy_version: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "execution_status": self.execution_status,
            "acceptance_status": self.acceptance_status,
            "mode": self.mode,
            "model_name": self.model_name,
            "model_digest": self.model_digest,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "prompt_sha256": self.prompt_sha256,
            "note": self.note,
            "pre_cleanup_text": self.pre_cleanup_text,
            "original_length": self.original_length,
            "candidate_length": self.candidate_length,
            "length_ratio": self.length_ratio,
            "cleanup_validator_policy_id": self.cleanup_validator_policy_id,
            "cleanup_validator_policy_version": self.cleanup_validator_policy_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CleanupRecord | None:
        if not data or not isinstance(data, dict):
            return None
        return cls(
            execution_status=str(data.get("execution_status") or "disabled"),
            acceptance_status=str(data.get("acceptance_status") or "not_applicable"),
            mode=data.get("mode"),
            model_name=data.get("model_name"),
            model_digest=data.get("model_digest"),
            prompt_id=data.get("prompt_id"),
            prompt_version=data.get("prompt_version"),
            prompt_sha256=data.get("prompt_sha256"),
            note=data.get("note"),
            pre_cleanup_text=data.get("pre_cleanup_text"),
            original_length=(
                int(data["original_length"])
                if data.get("original_length") is not None
                else None
            ),
            candidate_length=(
                int(data["candidate_length"])
                if data.get("candidate_length") is not None
                else None
            ),
            length_ratio=(
                float(data["length_ratio"])
                if data.get("length_ratio") is not None
                else None
            ),
            cleanup_validator_policy_id=data.get("cleanup_validator_policy_id"),
            cleanup_validator_policy_version=data.get(
                "cleanup_validator_policy_version"
            ),
        )


@dataclass
class RenderProvenance:
    render_id: str
    source_sha256: str
    pdf_page_index: int | None
    render_dpi: int
    renderer: str
    renderer_version: str
    rendered_image_sha256: str
    width: int
    height: int
    image_relpath: str
    # Additive visual-declutter provenance (absent on pre-declutter renders)
    declutter_state: str | None = None
    declutter_version: int | None = None
    declutter_ops: list[str] | None = None
    declutter_identity_sha256: str | None = None
    declutter_params: dict[str, Any] | None = None
    declutter_original_width: int | None = None
    declutter_original_height: int | None = None
    declutter_crop_left: int | None = None
    declutter_crop_top: int | None = None
    declutter_crop_right: int | None = None
    declutter_crop_bottom: int | None = None
    declutter_inset_left: int | None = None
    declutter_inset_top: int | None = None
    declutter_inset_right: int | None = None
    declutter_inset_bottom: int | None = None
    declutter_note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "render_id": self.render_id,
            "source_sha256": self.source_sha256,
            "pdf_page_index": self.pdf_page_index,
            "render_dpi": self.render_dpi,
            "renderer": self.renderer,
            "renderer_version": self.renderer_version,
            "rendered_image_sha256": self.rendered_image_sha256,
            "width": self.width,
            "height": self.height,
            "image_relpath": self.image_relpath,
        }
        if self.declutter_state is not None:
            payload["declutter_state"] = self.declutter_state
            payload["declutter_version"] = self.declutter_version
            payload["declutter_ops"] = list(self.declutter_ops or [])
            payload["declutter_identity_sha256"] = self.declutter_identity_sha256
            payload["declutter_params"] = dict(self.declutter_params or {})
            payload["declutter_original_width"] = self.declutter_original_width
            payload["declutter_original_height"] = self.declutter_original_height
            payload["declutter_crop_left"] = self.declutter_crop_left
            payload["declutter_crop_top"] = self.declutter_crop_top
            payload["declutter_crop_right"] = self.declutter_crop_right
            payload["declutter_crop_bottom"] = self.declutter_crop_bottom
            payload["declutter_inset_left"] = self.declutter_inset_left
            payload["declutter_inset_top"] = self.declutter_inset_top
            payload["declutter_inset_right"] = self.declutter_inset_right
            payload["declutter_inset_bottom"] = self.declutter_inset_bottom
            payload["declutter_note"] = self.declutter_note or ""
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RenderProvenance:
        return cls(
            render_id=data["render_id"],
            source_sha256=data["source_sha256"],
            pdf_page_index=data["pdf_page_index"],
            render_dpi=int(data["render_dpi"]),
            renderer=data["renderer"],
            renderer_version=data["renderer_version"],
            rendered_image_sha256=data["rendered_image_sha256"],
            width=int(data["width"]),
            height=int(data["height"]),
            image_relpath=data["image_relpath"],
            declutter_state=data.get("declutter_state"),
            declutter_version=(
                int(data["declutter_version"])
                if data.get("declutter_version") is not None
                else None
            ),
            declutter_ops=(
                list(data["declutter_ops"])
                if data.get("declutter_ops") is not None
                else None
            ),
            declutter_identity_sha256=data.get("declutter_identity_sha256"),
            declutter_params=(
                dict(data["declutter_params"])
                if data.get("declutter_params") is not None
                else None
            ),
            declutter_original_width=(
                int(data["declutter_original_width"])
                if data.get("declutter_original_width") is not None
                else None
            ),
            declutter_original_height=(
                int(data["declutter_original_height"])
                if data.get("declutter_original_height") is not None
                else None
            ),
            declutter_crop_left=(
                int(data["declutter_crop_left"])
                if data.get("declutter_crop_left") is not None
                else None
            ),
            declutter_crop_top=(
                int(data["declutter_crop_top"])
                if data.get("declutter_crop_top") is not None
                else None
            ),
            declutter_crop_right=(
                int(data["declutter_crop_right"])
                if data.get("declutter_crop_right") is not None
                else None
            ),
            declutter_crop_bottom=(
                int(data["declutter_crop_bottom"])
                if data.get("declutter_crop_bottom") is not None
                else None
            ),
            declutter_inset_left=(
                int(data["declutter_inset_left"])
                if data.get("declutter_inset_left") is not None
                else None
            ),
            declutter_inset_top=(
                int(data["declutter_inset_top"])
                if data.get("declutter_inset_top") is not None
                else None
            ),
            declutter_inset_right=(
                int(data["declutter_inset_right"])
                if data.get("declutter_inset_right") is not None
                else None
            ),
            declutter_inset_bottom=(
                int(data["declutter_inset_bottom"])
                if data.get("declutter_inset_bottom") is not None
                else None
            ),
            declutter_note=data.get("declutter_note"),
        )


@dataclass
class SourceDocument:
    source_id: str
    original_filename: str
    stored_relpath: str
    media_type: str
    sha256: str
    page_count: int
    imported_at: str
    render_dpi: int
    # Optional additive v1 fields (bulk-import generation); absence is legacy-conformant
    original_path: str | None = None
    source_size_bytes: int | None = None
    import_run_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "source_id": self.source_id,
            "original_filename": self.original_filename,
            "stored_relpath": self.stored_relpath,
            "media_type": self.media_type,
            "sha256": self.sha256,
            "page_count": self.page_count,
            "imported_at": self.imported_at,
            "render_dpi": self.render_dpi,
        }
        if self.original_path is not None:
            payload["original_path"] = self.original_path
        if self.source_size_bytes is not None:
            payload["source_size_bytes"] = self.source_size_bytes
        if self.import_run_id is not None:
            payload["import_run_id"] = self.import_run_id
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceDocument:
        size = data.get("source_size_bytes")
        return cls(
            source_id=data["source_id"],
            original_filename=data["original_filename"],
            stored_relpath=data["stored_relpath"],
            media_type=data["media_type"],
            sha256=data["sha256"],
            page_count=int(data["page_count"]),
            imported_at=data["imported_at"],
            render_dpi=int(data.get("render_dpi", 200)),
            original_path=data.get("original_path"),
            source_size_bytes=int(size) if size is not None else None,
            import_run_id=data.get("import_run_id"),
        )


@dataclass
class PageIndex:
    page_id: str
    source_id: str
    page_index: int
    active_render_id: str
    width: int
    height: int
    date: ApproximateDate | None = None
    date_approved: bool = True
    date_source: str | None = None
    tags: list[str] = field(default_factory=list)
    analysis_excluded: bool = False

    def as_dict(self) -> dict[str, Any]:
        date, approved, source = canonicalize_page_date_state(
            self.date, self.date_approved, self.date_source
        )
        return {
            "page_id": self.page_id,
            "source_id": self.source_id,
            "page_index": self.page_index,
            "active_render_id": self.active_render_id,
            "width": self.width,
            "height": self.height,
            "date": date.as_dict() if date else None,
            "date_approved": approved,
            "date_source": source,
            "tags": list(self.tags),
            "analysis_excluded": bool(self.analysis_excluded),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageIndex:
        date, approved, source = page_date_fields_from_dict(data)
        return cls(
            page_id=data["page_id"],
            source_id=data["source_id"],
            page_index=int(data["page_index"]),
            active_render_id=data["active_render_id"],
            width=int(data["width"]),
            height=int(data["height"]),
            date=date,
            date_approved=approved,
            date_source=source,
            tags=normalize_tags(data.get("tags")),
            analysis_excluded=bool(data.get("analysis_excluded", False)),
        )

    def set_date_state(
        self,
        date: ApproximateDate | None,
        *,
        approved: bool,
        source: str | None,
    ) -> None:
        d, a, s = canonicalize_page_date_state(date, approved, source)
        self.date = d
        self.date_approved = a
        self.date_source = s


def page_label(project: "Project", page_id: str) -> str:
    """Human-readable page name for progress (filename, plus PDF page index)."""
    page = next((p for p in project.pages if p.page_id == page_id), None)
    if page is None:
        return f"{page_id[:8]}…"
    source = next((s for s in project.sources if s.source_id == page.source_id), None)
    name = ""
    if source is not None and source.original_filename:
        name = source.original_filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not name:
        name = f"{page_id[:8]}…"
    if source is not None and int(source.page_count or 1) > 1:
        return f"{name} · p.{page.page_index + 1}"
    return name


@dataclass
class Project:
    id: str
    title: str
    created_at: str
    updated_at: str
    settings: OCRSettings
    sources: list[SourceDocument] = field(default_factory=list)
    pages: list[PageIndex] = field(default_factory=list)
    renders: dict[str, RenderProvenance] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    cover_page_id: str | None = None
    date_start: ApproximateDate | None = None
    date_end: ApproximateDate | None = None
    format: str = "transcribe.project"
    schema_version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "schema_version": self.schema_version,
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "settings": self.settings.as_dict(),
            "sources": [s.as_dict() for s in self.sources],
            "pages": [p.as_dict() for p in self.pages],
            "renders": {k: v.as_dict() for k, v in self.renders.items()},
            "tags": list(self.tags),
            "cover_page_id": self.cover_page_id,
            "date_start": self.date_start.as_dict() if self.date_start else None,
            "date_end": self.date_end.as_dict() if self.date_end else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        renders_raw = data.get("renders") or {}
        return cls(
            id=data["id"],
            title=data.get("title", ""),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            settings=OCRSettings.from_dict(data.get("settings") or {}),
            sources=[SourceDocument.from_dict(s) for s in data.get("sources") or []],
            pages=[PageIndex.from_dict(p) for p in data.get("pages") or []],
            renders={k: RenderProvenance.from_dict(v) for k, v in renders_raw.items()},
            tags=normalize_tags(data.get("tags")),
            cover_page_id=data.get("cover_page_id"),
            date_start=ApproximateDate.from_dict(data.get("date_start")),
            date_end=ApproximateDate.from_dict(data.get("date_end")),
            format=str(data.get("format", "transcribe.project")),
            schema_version=int(data.get("schema_version", 1)),
        )

    def global_index_for(self, page_id: str) -> int:
        for i, page in enumerate(self.pages):
            if page.page_id == page_id:
                return i
        raise KeyError(page_id)


ATTEMPT_STATUSES = frozenset(
    {"running", "succeeded", "failed", "cancelled", "interrupted"}
)


@dataclass
class AttemptError:
    code: str
    message: str
    retriable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AttemptError | None:
        if not data:
            return None
        return cls(
            code=data.get("code", "error"),
            message=data.get("message", ""),
            retriable=bool(data.get("retriable", False)),
        )


@dataclass
class AttemptProvenance:
    model_name: str
    model_digest: str | None
    model_identity_verified: bool
    prompt_id: str
    prompt_version: str
    prompt_sha256: str
    prompt_text: str
    input_sha256: str
    preprocess_profile: str
    preprocess_version: int
    generation_options: dict[str, Any]
    application_version: str
    ollama_host: str
    request_id: str
    render_id: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AttemptProvenance:
        return cls(
            model_name=data["model_name"],
            model_digest=data.get("model_digest"),
            model_identity_verified=bool(data.get("model_identity_verified", False)),
            prompt_id=data["prompt_id"],
            prompt_version=data["prompt_version"],
            prompt_sha256=data["prompt_sha256"],
            prompt_text=data["prompt_text"],
            input_sha256=data["input_sha256"],
            preprocess_profile=data["preprocess_profile"],
            preprocess_version=int(data["preprocess_version"]),
            generation_options=dict(data.get("generation_options") or {}),
            application_version=data["application_version"],
            ollama_host=data["ollama_host"],
            request_id=data["request_id"],
            render_id=data["render_id"],
        )


@dataclass
class ComparisonEntry:
    attempt_id: str
    score: float | None = None
    rationale: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "score": self.score,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComparisonEntry:
        return cls(
            attempt_id=str(data["attempt_id"]),
            score=(float(data["score"]) if data.get("score") is not None else None),
            rationale=data.get("rationale"),
        )


@dataclass
class ComparisonRecord:
    """Last multipass ranking for a page (vision attempts only)."""

    pass_id: str
    ranked_attempt_ids: list[str]
    created_at: str
    entries: list[ComparisonEntry] = field(default_factory=list)
    ranker_model_name: str | None = None
    ranker_model_digest: str | None = None
    ranker_prompt_id: str | None = None
    ranker_prompt_version: str | None = None
    ranker_prompt_sha256: str | None = None
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "pass_id": self.pass_id,
            "ranked_attempt_ids": list(self.ranked_attempt_ids),
            "created_at": self.created_at,
            "entries": [e.as_dict() for e in self.entries],
            "ranker_model_name": self.ranker_model_name,
            "ranker_model_digest": self.ranker_model_digest,
            "ranker_prompt_id": self.ranker_prompt_id,
            "ranker_prompt_version": self.ranker_prompt_version,
            "ranker_prompt_sha256": self.ranker_prompt_sha256,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ComparisonRecord | None:
        if not data or not isinstance(data, dict):
            return None
        entries_raw = data.get("entries") or []
        return cls(
            pass_id=str(data.get("pass_id") or ""),
            ranked_attempt_ids=[str(x) for x in (data.get("ranked_attempt_ids") or [])],
            created_at=str(data.get("created_at") or ""),
            entries=[
                ComparisonEntry.from_dict(e) for e in entries_raw if isinstance(e, dict)
            ],
            ranker_model_name=data.get("ranker_model_name"),
            ranker_model_digest=data.get("ranker_model_digest"),
            ranker_prompt_id=data.get("ranker_prompt_id"),
            ranker_prompt_version=data.get("ranker_prompt_version"),
            ranker_prompt_sha256=data.get("ranker_prompt_sha256"),
            note=data.get("note"),
        )


@dataclass
class OCRAttempt:
    attempt_id: str
    status: str
    input_fingerprint: str
    fingerprint_payload: dict[str, Any]
    raw_text: str | None
    provenance: AttemptProvenance | None
    provider_metadata: dict[str, Any]
    started_at: str
    completed_at: str | None = None
    error: AttemptError | None = None
    cleanup: CleanupRecord | None = None
    attempt_kind: str = "vision"
    pass_id: str | None = None
    source_attempt_ids: list[str] = field(default_factory=list)
    composite_note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "attempt_id": self.attempt_id,
            "status": self.status,
            "input_fingerprint": self.input_fingerprint,
            "fingerprint_payload": self.fingerprint_payload,
            "raw_text": self.raw_text,
            "provenance": self.provenance.as_dict() if self.provenance else None,
            "provider_metadata": filter_provider_metadata(self.provider_metadata),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error.as_dict() if self.error else None,
            "attempt_kind": self.attempt_kind or "vision",
        }
        if self.cleanup is not None:
            payload["cleanup"] = self.cleanup.as_dict()
        if self.pass_id is not None:
            payload["pass_id"] = self.pass_id
        if self.source_attempt_ids:
            payload["source_attempt_ids"] = list(self.source_attempt_ids)
        if self.composite_note is not None:
            payload["composite_note"] = self.composite_note
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCRAttempt:
        prov = data.get("provenance")
        kind = str(data.get("attempt_kind") or "vision")
        if kind not in ATTEMPT_KINDS:
            kind = "vision"
        return cls(
            attempt_id=data["attempt_id"],
            status=data["status"],
            input_fingerprint=data.get("input_fingerprint", ""),
            fingerprint_payload=dict(data.get("fingerprint_payload") or {}),
            raw_text=data.get("raw_text"),
            provenance=AttemptProvenance.from_dict(prov) if prov else None,
            provider_metadata=filter_provider_metadata(data.get("provider_metadata")),
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            error=AttemptError.from_dict(data.get("error")),
            cleanup=CleanupRecord.from_dict(data.get("cleanup")),
            attempt_kind=kind,
            pass_id=data.get("pass_id"),
            source_attempt_ids=[str(x) for x in (data.get("source_attempt_ids") or [])],
            composite_note=data.get("composite_note"),
        )


@dataclass
class PageResult:
    page_id: str
    active_attempt_id: str | None = None
    preferred_attempt_id: str | None = None
    edited_text: str | None = None
    attempts: list[OCRAttempt] = field(default_factory=list)
    comparison: ComparisonRecord | None = None
    updated_at: str = ""
    format: str = "transcribe.page-result"
    schema_version: int = 1

    @property
    def status(self) -> str:
        attempt = self.active_attempt()
        if attempt is None:
            return "pending"
        return attempt.status

    def active_attempt(self) -> OCRAttempt | None:
        if not self.active_attempt_id:
            return None
        for attempt in self.attempts:
            if attempt.attempt_id == self.active_attempt_id:
                return attempt
        return None

    def preferred_attempt(self) -> OCRAttempt | None:
        if not self.preferred_attempt_id:
            return None
        for attempt in self.attempts:
            if attempt.attempt_id == self.preferred_attempt_id:
                return attempt
        return None

    def attempt_by_id(self, attempt_id: str) -> OCRAttempt | None:
        for attempt in self.attempts:
            if attempt.attempt_id == attempt_id:
                return attempt
        return None

    def effective_text(self) -> str | None:
        if self.edited_text is not None:
            return self.edited_text
        attempt = self.active_attempt()
        if attempt is None:
            return None
        return attempt.raw_text

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "format": self.format,
            "schema_version": self.schema_version,
            "page_id": self.page_id,
            "active_attempt_id": self.active_attempt_id,
            "edited_text": self.edited_text,
            "attempts": [a.as_dict() for a in self.attempts],
            "status": self.status,
            "updated_at": self.updated_at,
        }
        if self.preferred_attempt_id is not None:
            payload["preferred_attempt_id"] = self.preferred_attempt_id
        if self.comparison is not None:
            payload["comparison"] = self.comparison.as_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageResult:
        result = cls(
            page_id=data["page_id"],
            active_attempt_id=data.get("active_attempt_id"),
            preferred_attempt_id=data.get("preferred_attempt_id"),
            edited_text=data.get("edited_text"),
            attempts=[OCRAttempt.from_dict(a) for a in data.get("attempts") or []],
            comparison=ComparisonRecord.from_dict(data.get("comparison")),
            updated_at=data.get("updated_at", ""),
            format=str(data.get("format", "transcribe.page-result")),
            schema_version=int(data.get("schema_version", 1)),
        )
        # Derived status must match active attempt when present.
        _ = result.status
        return result


MAX_ATTEMPTS_RETAINED = 40


def prune_attempts(
    attempts: list[OCRAttempt],
    *,
    active_attempt_id: str | None,
    preferred_attempt_id: str | None,
    max_retained: int = MAX_ATTEMPTS_RETAINED,
) -> list[OCRAttempt]:
    """Retain active, preferred, latest per (model, digest), latest composite per pass."""
    if len(attempts) <= max_retained:
        return list(attempts)

    protected: set[str] = set()
    if active_attempt_id:
        protected.add(active_attempt_id)
    if preferred_attempt_id:
        protected.add(preferred_attempt_id)

    latest_by_model: dict[tuple[str, str | None], OCRAttempt] = {}
    latest_composite_by_pass: dict[str, OCRAttempt] = {}
    for attempt in attempts:
        if attempt.status != "succeeded":
            continue
        if attempt.attempt_kind == "composite":
            key = attempt.pass_id or ""
            prev = latest_composite_by_pass.get(key)
            if prev is None or attempt.started_at >= prev.started_at:
                latest_composite_by_pass[key] = attempt
            continue
        model = ""
        digest = None
        if attempt.provenance is not None:
            model = attempt.provenance.model_name
            digest = attempt.provenance.model_digest
        mkey = (model, digest)
        prev = latest_by_model.get(mkey)
        if prev is None or attempt.started_at >= prev.started_at:
            latest_by_model[mkey] = attempt

    for attempt in latest_by_model.values():
        protected.add(attempt.attempt_id)
    for attempt in latest_composite_by_pass.values():
        protected.add(attempt.attempt_id)

    ordered = sorted(attempts, key=lambda a: a.started_at, reverse=True)
    if len(protected) > max_retained:
        priority: list[OCRAttempt] = []
        priority_ids: set[str] = set()
        for aid in (active_attempt_id, preferred_attempt_id):
            if not aid or aid in priority_ids:
                continue
            for attempt in ordered:
                if attempt.attempt_id == aid:
                    priority.append(attempt)
                    priority_ids.add(aid)
                    break
        for attempt in ordered:
            if len(priority) >= max_retained:
                break
            if (
                attempt.attempt_id in protected
                and attempt.attempt_id not in priority_ids
            ):
                priority.append(attempt)
                priority_ids.add(attempt.attempt_id)
        # Oldest first, newest last (matches prior retention order).
        return sorted(priority[:max_retained], key=lambda a: a.started_at)

    kept: list[OCRAttempt] = []
    kept_ids: set[str] = set()
    for attempt in ordered:
        if attempt.attempt_id in protected:
            if attempt.attempt_id not in kept_ids:
                kept.append(attempt)
                kept_ids.add(attempt.attempt_id)
    for attempt in ordered:
        if len(kept) >= max_retained:
            break
        if attempt.attempt_id not in kept_ids:
            kept.append(attempt)
            kept_ids.add(attempt.attempt_id)
    return sorted(kept, key=lambda a: a.started_at)
