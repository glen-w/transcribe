"""Frozen AnalysisRunPlan for durable batch Analyse launches."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from transcribe.analysis.llm_runtime import (
    TextLLMContext,
    bind_text_llm_context,
    get_text_llm_client,
    ollama_base_url_for_binding,
)
from transcribe.config.facade import snapshot_for_operation
from transcribe.config.models import EffectiveConfig
from transcribe.domain.fingerprint import canonical_json_bytes
from transcribe.ports import Clock, IdGenerator, to_iso
from transcribe.services.project import ProjectService

ANALYSIS_RUN_FORMAT = "transcribe.analysis-run"
ANALYSIS_RUN_SCHEMA_VERSION = 1
RUN_TERMINAL_STATUSES = frozenset({"completed", "cancelled", "failed", "interrupted"})
RUN_ACTIVE_STATUSES = frozenset({"running"})
# Keep in sync with AnalysisRunner.LLM_MODULES (avoid importing runner here).
_LLM_MODULES = frozenset({"llm_summary", "llm_action_items", "llm_custom_qa", "narrative_summary"})


@dataclass(frozen=True)
class FrozenTextModel:
    """Text-model identity resolved once at plan build."""

    model_name: str
    resolved_model_digest: str
    base_url: str | None = None
    identity_verified: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "resolved_model_digest": self.resolved_model_digest,
            "base_url": self.base_url,
            "identity_verified": self.identity_verified,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> FrozenTextModel | None:
        if not data:
            return None
        name = str(data.get("model_name") or "").strip()
        digest = str(data.get("resolved_model_digest") or "").strip()
        if not name or not digest:
            return None
        return cls(
            model_name=name,
            resolved_model_digest=digest,
            base_url=(str(data["base_url"]) if data.get("base_url") else None),
            identity_verified=bool(data.get("identity_verified", True)),
        )


@dataclass(frozen=True)
class AnalysisRunPlan:
    """Immutable execution plan resolved once at analysis batch start."""

    run_id: str
    project_id: str
    module_ids: tuple[str, ...]
    question_text: str | None
    effective_config: EffectiveConfig
    config_fingerprint: str
    text_model: FrozenTextModel | None
    plan_hash: str
    preset_label: str | None = None
    preset_key: str | None = None
    preset_content_version: int | None = None
    preset_policy_fingerprint: str | None = None
    created_at: str | None = None

    def needs_llm(self) -> bool:
        return any(mid in _LLM_MODULES for mid in self.module_ids)

    def build_llm_context(self) -> TextLLMContext | None:
        """Rebuild a TextLLMContext from frozen identity (live client, frozen digest)."""
        if self.text_model is None:
            return None
        client = get_text_llm_client(base_url=self.text_model.base_url)
        return TextLLMContext(
            client=client,
            model_name=self.text_model.model_name,
            resolved_model_digest=self.text_model.resolved_model_digest,
            base_url=self.text_model.base_url,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "module_ids": list(self.module_ids),
            "question_text": self.question_text,
            "effective_config": self.effective_config.as_dict(),
            "config_fingerprint": self.config_fingerprint,
            "text_model": self.text_model.as_dict() if self.text_model else None,
            "plan_hash": self.plan_hash,
            "preset_label": self.preset_label,
            "preset_key": self.preset_key,
            "preset_content_version": self.preset_content_version,
            "preset_policy_fingerprint": self.preset_policy_fingerprint,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AnalysisRunPlan:
        modules = tuple(str(m) for m in (data.get("module_ids") or ()))
        cfg_raw = data.get("effective_config")
        if not isinstance(cfg_raw, Mapping):
            cfg_raw = {}
        version_raw = data.get("preset_content_version")
        content_version: int | None
        if version_raw is None:
            content_version = None
        else:
            try:
                content_version = int(version_raw)
            except (TypeError, ValueError):
                content_version = None
        plan = cls(
            run_id=str(data.get("run_id") or ""),
            project_id=str(data.get("project_id") or ""),
            module_ids=modules,
            question_text=(
                str(data["question_text"]) if data.get("question_text") is not None else None
            ),
            effective_config=EffectiveConfig.from_dict(cfg_raw),
            config_fingerprint=str(data.get("config_fingerprint") or ""),
            text_model=FrozenTextModel.from_dict(
                data.get("text_model") if isinstance(data.get("text_model"), Mapping) else None
            ),
            plan_hash=str(data.get("plan_hash") or ""),
            preset_label=(
                str(data["preset_label"]) if data.get("preset_label") is not None else None
            ),
            preset_key=(str(data["preset_key"]) if data.get("preset_key") is not None else None),
            preset_content_version=content_version,
            preset_policy_fingerprint=(
                str(data["preset_policy_fingerprint"])
                if data.get("preset_policy_fingerprint") is not None
                else None
            ),
            created_at=(str(data["created_at"]) if data.get("created_at") is not None else None),
        )
        return plan


def compute_plan_hash(plan: AnalysisRunPlan | Mapping[str, Any]) -> str:
    """SHA-256 of execution-significant plan fields (excludes run_id / created_at / plan_hash)."""
    if isinstance(plan, AnalysisRunPlan):
        body = {
            "project_id": plan.project_id,
            "module_ids": list(plan.module_ids),
            "question_text": plan.question_text,
            "effective_config": plan.effective_config.as_dict(),
            "text_model": plan.text_model.as_dict() if plan.text_model else None,
            "config_fingerprint": plan.config_fingerprint,
            "preset_key": plan.preset_key,
            "preset_content_version": plan.preset_content_version,
            "preset_policy_fingerprint": plan.preset_policy_fingerprint,
        }
    else:
        cfg = plan.get("effective_config")
        body = {
            "project_id": plan.get("project_id"),
            "module_ids": list(plan.get("module_ids") or ()),
            "question_text": plan.get("question_text"),
            "effective_config": cfg if isinstance(cfg, Mapping) else {},
            "text_model": plan.get("text_model"),
            "config_fingerprint": plan.get("config_fingerprint"),
            "preset_key": plan.get("preset_key"),
            "preset_content_version": plan.get("preset_content_version"),
            "preset_policy_fingerprint": plan.get("preset_policy_fingerprint"),
        }
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def verify_plan_hash(plan: AnalysisRunPlan) -> bool:
    """True when stored plan_hash matches recomputation."""
    if not plan.plan_hash:
        return False
    return plan.plan_hash == compute_plan_hash(plan)


class PlanHashMismatchError(ValueError):
    """Pending / stored plan_hash does not match recomputed plan body."""


def config_fingerprint_for_plan(
    effective: EffectiveConfig,
    *,
    text_model: FrozenTextModel | None,
    module_ids: Sequence[str],
    question_text: str | None,
) -> str:
    payload = {
        "effective_config": effective.as_dict(),
        "text_model": text_model.as_dict() if text_model else None,
        "module_ids": list(module_ids),
        "question_text": question_text,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_analysis_run_plan(
    *,
    project_service: ProjectService,
    module_ids: Sequence[str],
    question_text: str | None = None,
    preset_label: str | None = None,
    preset_key: str | None = None,
    preset_content_version: int | None = None,
    preset_policy_fingerprint: str | None = None,
    clock: Clock,
    ids: IdGenerator,
    project: Any | None = None,
) -> AnalysisRunPlan:
    """Freeze launch inputs once. Call before AnalysisCoordinator.start."""
    from transcribe.analysis.parents import batch_module_order
    from transcribe.analysis.presets import expand_with_hard_parents

    project = project or project_service.load(reconcile=True)
    ordered = tuple(batch_module_order(list(expand_with_hard_parents(list(module_ids)))))
    if not ordered:
        raise ValueError("analysis run plan requires at least one module")

    effective = snapshot_for_operation(
        project_settings=project.settings,
        project_id=project.id,
    )
    q = (question_text or "").strip() or None
    text_model: FrozenTextModel | None = None
    if any(mid in _LLM_MODULES for mid in ordered):
        ctx = bind_text_llm_context(
            text_model_name=getattr(project.settings, "text_model_name", None),
            base_url=ollama_base_url_for_binding(
                getattr(project.settings, "base_url", None),
            ),
        )
        if ctx is not None:
            text_model = FrozenTextModel(
                model_name=ctx.model_name,
                resolved_model_digest=ctx.resolved_model_digest,
                base_url=ctx.base_url,
                identity_verified=True,
            )

    run_id = ids.new_id()
    fp = config_fingerprint_for_plan(
        effective,
        text_model=text_model,
        module_ids=ordered,
        question_text=q,
    )
    draft = AnalysisRunPlan(
        run_id=run_id,
        project_id=project.id,
        module_ids=ordered,
        question_text=q,
        effective_config=effective,
        config_fingerprint=fp,
        text_model=text_model,
        plan_hash="",  # filled below
        preset_label=preset_label,
        preset_key=preset_key,
        preset_content_version=preset_content_version,
        preset_policy_fingerprint=preset_policy_fingerprint,
        created_at=to_iso(clock.now()),
    )
    return AnalysisRunPlan(
        run_id=draft.run_id,
        project_id=draft.project_id,
        module_ids=draft.module_ids,
        question_text=draft.question_text,
        effective_config=draft.effective_config,
        config_fingerprint=draft.config_fingerprint,
        text_model=draft.text_model,
        plan_hash=compute_plan_hash(draft),
        preset_label=draft.preset_label,
        preset_key=draft.preset_key,
        preset_content_version=draft.preset_content_version,
        preset_policy_fingerprint=draft.preset_policy_fingerprint,
        created_at=draft.created_at,
    )


def run_record_payload(
    plan: AnalysisRunPlan,
    *,
    status: str,
    completed: int = 0,
    failed: int = 0,
    skipped: int = 0,
    current_module_id: str | None = None,
    message: str = "",
    started_at: str | None = None,
    ended_at: str | None = None,
    module_outcomes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Durable batch run record (history only; not publish authority)."""
    return {
        "format": ANALYSIS_RUN_FORMAT,
        "schema_version": ANALYSIS_RUN_SCHEMA_VERSION,
        "run_id": plan.run_id,
        "project_id": plan.project_id,
        "status": status,
        "module_ids": list(plan.module_ids),
        "question_text": plan.question_text,
        "config_fingerprint": plan.config_fingerprint,
        "plan_hash": plan.plan_hash,
        "text_model": plan.text_model.as_dict() if plan.text_model else None,
        "preset_label": plan.preset_label,
        "preset_key": plan.preset_key,
        "preset_content_version": plan.preset_content_version,
        "preset_policy_fingerprint": plan.preset_policy_fingerprint,
        "effective_config": plan.effective_config.as_dict(),
        "total": len(plan.module_ids),
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
        "current_module_id": current_module_id,
        "message": message,
        "module_outcomes": dict(module_outcomes or {}),
        "started_at": started_at or plan.created_at,
        "ended_at": ended_at,
        "plan": plan.as_dict(),
    }
