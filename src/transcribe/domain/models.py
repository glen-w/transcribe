"""Domain dataclasses and (de)serialization for persisted formats."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from transcribe.domain.dates import ApproximateDate, normalize_tags

PROVIDER_METADATA_ALLOWLIST = frozenset(
    {
        "total_duration",
        "load_duration",
        "prompt_eval_count",
        "eval_count",
        "retry_count",
        "prompt_eval_duration",
        "eval_duration",
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


@dataclass
class GenerationOptions:
    temperature: float = 0.0
    # Keep extensible but fingerprint-stable via as_dict

    def as_dict(self) -> dict[str, Any]:
        return {"temperature": self.temperature}


CLEANUP_MODES = frozenset({"strip_leak", "sanitize_light", "rewrite"})


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
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCRSettings:
        opts = data.get("generation_options") or {}
        mode = str(data.get("cleanup_mode") or "strip_leak")
        if mode not in CLEANUP_MODES:
            mode = "strip_leak"
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
            ),
            allow_non_loopback=bool(data.get("allow_non_loopback", False)),
            cleanup_enabled=bool(data.get("cleanup_enabled", False)),
            cleanup_mode=mode,
            cleanup_model_name=str(data.get("cleanup_model_name") or ""),
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

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RenderProvenance:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


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

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceDocument:
        return cls(
            source_id=data["source_id"],
            original_filename=data["original_filename"],
            stored_relpath=data["stored_relpath"],
            media_type=data["media_type"],
            sha256=data["sha256"],
            page_count=int(data["page_count"]),
            imported_at=data["imported_at"],
            render_dpi=int(data.get("render_dpi", 200)),
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
    tags: list[str] = field(default_factory=list)
    analysis_excluded: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "source_id": self.source_id,
            "page_index": self.page_index,
            "active_render_id": self.active_render_id,
            "width": self.width,
            "height": self.height,
            "date": self.date.as_dict() if self.date else None,
            "tags": list(self.tags),
            "analysis_excluded": bool(self.analysis_excluded),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageIndex:
        return cls(
            page_id=data["page_id"],
            source_id=data["source_id"],
            page_index=int(data["page_index"]),
            active_render_id=data["active_render_id"],
            width=int(data["width"]),
            height=int(data["height"]),
            date=ApproximateDate.from_dict(data.get("date")),
            tags=normalize_tags(data.get("tags")),
            analysis_excluded=bool(data.get("analysis_excluded", False)),
        )


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
        }
        if self.cleanup is not None:
            payload["cleanup"] = self.cleanup.as_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCRAttempt:
        prov = data.get("provenance")
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
        )


@dataclass
class PageResult:
    page_id: str
    active_attempt_id: str | None = None
    edited_text: str | None = None
    attempts: list[OCRAttempt] = field(default_factory=list)
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

    def effective_text(self) -> str | None:
        if self.edited_text is not None:
            return self.edited_text
        attempt = self.active_attempt()
        if attempt is None:
            return None
        return attempt.raw_text

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "schema_version": self.schema_version,
            "page_id": self.page_id,
            "active_attempt_id": self.active_attempt_id,
            "edited_text": self.edited_text,
            "attempts": [a.as_dict() for a in self.attempts],
            "status": self.status,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageResult:
        result = cls(
            page_id=data["page_id"],
            active_attempt_id=data.get("active_attempt_id"),
            edited_text=data.get("edited_text"),
            attempts=[OCRAttempt.from_dict(a) for a in data.get("attempts") or []],
            updated_at=data.get("updated_at", ""),
            format=str(data.get("format", "transcribe.page-result")),
            schema_version=int(data.get("schema_version", 1)),
        )
        # Derived status must match active attempt when present.
        _ = result.status
        return result


MAX_ATTEMPTS_RETAINED = 20
