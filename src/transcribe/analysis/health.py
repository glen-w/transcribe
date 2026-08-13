"""Derived Analyse health shared across Overview / Themes / Mood / Moments / People & places / Summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

from transcribe.analysis.runner import AnalysisRunner, module_freshness
from transcribe.analysis.storage import AnalysisStorage

FreshnessStatus = Literal["ok", "stale", "unavailable"]
AggregateHealth = Literal[
    "healthy",
    "stale",
    "missing",
    "degraded",
    "failed",
    "running",
    "interrupted",
]

_DEGRADED_CAPABILITIES = frozenset(
    {
        "unavailable_model",
        "unavailable_extra",
        "unavailable_dependency",
        "insufficient_data",
        "skipped_not_applicable",
    }
)


@dataclass(frozen=True)
class ModuleHealth:
    module_id: str
    freshness: FreshnessStatus
    capability: str | None
    outcome: str | None
    envelope: dict[str, Any] | None
    live_evidence: list[Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "freshness": self.freshness,
            "capability": self.capability,
            "outcome": self.outcome,
            "envelope": self.envelope,
            "live_evidence": list(self.live_evidence),
        }


@dataclass(frozen=True)
class AnalysisHealth:
    content_revision: str
    modules: dict[str, ModuleHealth]
    aggregate: AggregateHealth
    active_run_status: str | None
    scoped_module_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "content_revision": self.content_revision,
            "aggregate": self.aggregate,
            "active_run_status": self.active_run_status,
            "scoped_module_ids": list(self.scoped_module_ids),
            "modules": {mid: mh.as_dict() for mid, mh in self.modules.items()},
        }


def _module_from_read_model(rm: dict[str, Any]) -> ModuleHealth:
    env = rm.get("envelope")
    env_dict = env if isinstance(env, dict) else None
    freshness = str(rm.get("status") or "unavailable")
    if freshness not in ("ok", "stale", "unavailable"):
        freshness = "unavailable"
    return ModuleHealth(
        module_id=str(rm.get("module_id") or ""),
        freshness=freshness,  # type: ignore[arg-type]
        capability=(
            str(env_dict["capability"])
            if env_dict and env_dict.get("capability") is not None
            else None
        ),
        outcome=(
            str(env_dict["outcome"]) if env_dict and env_dict.get("outcome") is not None else None
        ),
        envelope=env_dict,
        live_evidence=list(rm.get("live_evidence") or []),
    )


def aggregate_module_health(
    modules: Sequence[ModuleHealth],
    *,
    active_run_status: str | None = None,
) -> AggregateHealth:
    """Deterministic aggregate over a module health set."""
    if active_run_status == "running":
        return "running"
    if active_run_status == "interrupted":
        return "interrupted"
    if not modules:
        return "missing"
    if any(m.freshness == "stale" for m in modules):
        return "stale"
    if all(m.freshness == "unavailable" for m in modules):
        return "missing"
    if any(
        m.freshness == "ok" and (m.outcome == "failed" or m.capability == "failed") for m in modules
    ):
        return "failed"
    if any(
        m.freshness == "ok"
        and (
            (m.capability in _DEGRADED_CAPABILITIES)
            or (
                m.outcome
                in {
                    "unavailable_dependency",
                    "insufficient_data",
                    "skipped_not_applicable",
                }
            )
        )
        for m in modules
    ):
        return "degraded"
    return "healthy"


def derive_analysis_health(
    *,
    storage: AnalysisStorage,
    runner: AnalysisRunner,
    module_ids: Sequence[str],
    content_revision: str,
    active_run_status: str | None = None,
    question_text: str | None = None,
) -> AnalysisHealth:
    """Single derived health model for Analyse surfaces (Ask is out of batch scope)."""
    scoped = tuple(str(m) for m in module_ids)
    read_models = module_freshness(runner, storage, scoped, question_text=question_text)
    modules = {rm["module_id"]: _module_from_read_model(rm) for rm in read_models}
    ordered = [modules[mid] for mid in scoped if mid in modules]
    return AnalysisHealth(
        content_revision=content_revision,
        modules=modules,
        aggregate=aggregate_module_health(ordered, active_run_status=active_run_status),
        active_run_status=active_run_status,
        scoped_module_ids=scoped,
    )


def scope_analysis_health(
    health: AnalysisHealth,
    module_ids: Sequence[str],
) -> AnalysisHealth:
    """Re-scope an already-derived health object without recomputing freshness."""
    scoped = tuple(str(m) for m in module_ids)
    modules = {mid: health.modules[mid] for mid in scoped if mid in health.modules}
    ordered = [modules[mid] for mid in scoped if mid in modules]
    return AnalysisHealth(
        content_revision=health.content_revision,
        modules=modules,
        aggregate=aggregate_module_health(ordered, active_run_status=health.active_run_status),
        active_run_status=health.active_run_status,
        scoped_module_ids=scoped,
    )
