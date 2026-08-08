"""Run analysis modules with lock-free compute and atomic publish."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.adapter import build_page_v1_document
from transcribe.analysis.cache_identity import (
    build_cache_identity_object,
    cache_identity_hex,
    config_fingerprint,
)
from transcribe.analysis.document import AnalysisDocumentError
from transcribe.analysis.envelope import build_envelope
from transcribe.analysis.modules import get_wave11_modules
from transcribe.analysis.storage import AnalysisStorage
from transcribe.persistence.locks import mutation_lock
from transcribe.ports import Clock, IdGenerator
from transcribe.services.project import ProjectService


def _module_provenance(module: Any) -> dict[str, Any]:
    from transcribe.analysis.modules import lexical_diversity as ld
    from transcribe.analysis.modules import stats as st
    from transcribe.analysis.modules import understandability as un

    files_fn = {
        "stats": st.provenance_files,
        "lexical_diversity": ld.provenance_files,
        "understandability": un.provenance_files,
    }.get(module.module_id, lambda: [])
    files = files_fn()
    commit = "50a0ede8e7acd03bbd9125a5a5237049f3291304" if files else "n/a"
    return {
        "ported_from": {
            "repo": "TranscriptX",
            "commit": commit,
            "module_id": module.module_id,
            "files": files,
        },
        "semantic_class": getattr(module, "semantic_class", "adaptation"),
        "semantic_delta": getattr(module, "semantic_delta", ""),
    }


class AnalysisRunner:
    def __init__(
        self,
        project_service: ProjectService,
        *,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self.project_service = project_service
        self.paths = project_service.paths
        self.clock = clock
        self.ids = ids
        self.storage = AnalysisStorage(self.paths)

    def reconcile(self) -> list[str]:
        return self.storage.reconcile_interrupted()

    def run_module(self, module_id: str) -> dict[str, Any]:
        modules = get_wave11_modules()
        module = modules.get(module_id)
        if module is None:
            raise KeyError(f"unknown module_id: {module_id}")

        project = self.project_service.load(reconcile=True)
        self.reconcile()

        try:
            document = build_page_v1_document(project, self.project_service)
        except AnalysisDocumentError as exc:
            return self._publish_preflight_insufficient(
                project_id=project.id,
                module=module,
                code=exc.code,
                message=str(exc),
            )

        planned_identity_obj = build_cache_identity_object(
            project_id=project.id,
            module_id=module.module_id,
            module_version=module.module_version,
            document=document,
            config={},
        )
        planned_identity = cache_identity_hex(planned_identity_obj)
        content_fp = planned_identity_obj["content_fingerprint"]
        cfg_fp = planned_identity_obj["config_fingerprint"]

        cached = self.storage.validate_cache_hit(
            module_id=module.module_id,
            expected_cache_identity=planned_identity,
            expected_module_version=module.module_version,
        )
        if cached is not None:
            return cached

        attempt_id = self.ids.new_id()
        running = build_envelope(
            project_id=project.id,
            module_id=module.module_id,
            module_version=module.module_version,
            cache_identity=planned_identity,
            content_fingerprint=content_fp,
            attempt_state="running",
            # Placeholder outcome until terminal write; never published while running.
            outcome="insufficient_data",
            payload={},
            provenance=_module_provenance(module),
            config_fingerprint=cfg_fp,
            attempt_id=attempt_id,
            published=False,
        )
        # Short lock: persist running
        with mutation_lock(self.paths.mutation_lock):
            self.storage.write_attempt(module.module_id, running)

        # Unlocked compute
        try:
            result = module.run(document)
            outcome = result["outcome"]
            payload = result.get("payload") or {}
            warnings = result.get("warnings") or []
            partial = bool(result.get("partial"))
            capability_reason = result.get("capability_reason")
            attempt_state = "failed" if outcome == "failed" else "succeeded"
        except Exception as exc:  # noqa: BLE001 — isolate module failures
            outcome = "failed"
            payload = {"error": {"code": "module_exception", "message": str(exc)}}
            warnings = [{"code": "module_exception", "message": str(exc)}]
            partial = False
            capability_reason = None
            attempt_state = "failed"

        terminal = build_envelope(
            project_id=project.id,
            module_id=module.module_id,
            module_version=module.module_version,
            cache_identity=planned_identity,
            content_fingerprint=content_fp,
            attempt_state=attempt_state,
            outcome=outcome,
            payload=payload,
            provenance=_module_provenance(module),
            config_fingerprint=cfg_fp,
            warnings=warnings,
            partial=partial,
            capability_reason=capability_reason,
            attempt_id=attempt_id,
            published=False,
        )
        with mutation_lock(self.paths.mutation_lock):
            self.storage.write_attempt(module.module_id, terminal)
            # Re-check identity under lock
            project_now = self.project_service._load_unlocked(reconcile=False)
            try:
                doc_now = build_page_v1_document(project_now, self.project_service)
                identity_now = cache_identity_hex(
                    build_cache_identity_object(
                        project_id=project_now.id,
                        module_id=module.module_id,
                        module_version=module.module_version,
                        document=doc_now,
                        config={},
                    )
                )
            except AnalysisDocumentError:
                identity_now = ""
            published = self.storage.publish_if_current(
                module_id=module.module_id,
                envelope=terminal,
                expected_cache_identity=planned_identity,
                current_cache_identity=identity_now,
            )
            if published:
                out = self.storage.read_published(module.module_id)
                return out or terminal
            # reload attempt (may have stale flag)
            return self.storage.read_attempt(module.module_id, attempt_id) or terminal

    def run_batch(self, module_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
        ids = module_ids or list(get_wave11_modules().keys())
        results: dict[str, dict[str, Any]] = {}
        for mid in ids:
            try:
                results[mid] = self.run_module(mid)
            except Exception as exc:  # noqa: BLE001
                results[mid] = {
                    "module_id": mid,
                    "attempt_state": "failed",
                    "outcome": "failed",
                    "capability": "failed",
                    "payload": {"error": {"message": str(exc)}},
                }
        return results

    def _publish_preflight_insufficient(
        self,
        *,
        project_id: str,
        module: Any,
        code: str,
        message: str,
    ) -> dict[str, Any]:
        attempt_id = self.ids.new_id()
        # Empty document: use a synthetic identity from project_id + module only is forbidden;
        # use explicit empty fingerprint marker via config.
        empty_fp = config_fingerprint({"empty": True, "code": code})
        identity_obj = {
            "adapter_version": "1",
            "cache_identity_version": 1,
            "config_fingerprint": empty_fp,
            "content_fingerprint": empty_fp,
            "content_fingerprint_version": 1,
            "eligibility_fingerprint": None,
            "eligibility_policy_id": None,
            "eligibility_policy_version": None,
            "granularity_version": "page_v1",
            "lexicon_or_model": None,
            "llm": None,
            "module_id": module.module_id,
            "module_version": module.module_version,
            "parents": [],
            "project_id": project_id,
            "resolved_model_digest": None,
            "split_profile": "page",
        }
        identity = cache_identity_hex(identity_obj)
        envelope = build_envelope(
            project_id=project_id,
            module_id=module.module_id,
            module_version=module.module_version,
            cache_identity=identity,
            content_fingerprint=empty_fp,
            attempt_state="succeeded",
            outcome="insufficient_data",
            payload={"error": {"code": code, "message": message}},
            provenance=_module_provenance(module),
            config_fingerprint=empty_fp,
            warnings=[{"code": code, "message": message}],
            capability_reason="invalid_document",
            attempt_id=attempt_id,
            published=False,
        )
        with mutation_lock(self.paths.mutation_lock):
            self.storage.write_attempt(module.module_id, envelope)
            self.storage.publish_if_current(
                module_id=module.module_id,
                envelope=envelope,
                expected_cache_identity=identity,
                current_cache_identity=identity,
            )
            return self.storage.read_published(module.module_id) or envelope


def load_published_read_model(
    storage: AnalysisStorage,
    module_id: str,
    *,
    current_cache_identity: str | None,
) -> dict[str, Any]:
    """UI read-model: validated published only; classify stale/unavailable."""
    published = storage.read_published(module_id)
    if published is None:
        return {
            "status": "unavailable",
            "module_id": module_id,
            "envelope": None,
        }
    if (
        current_cache_identity is not None
        and published.get("cache_identity") != current_cache_identity
    ):
        return {
            "status": "stale",
            "module_id": module_id,
            "envelope": published,
        }
    return {
        "status": "ok",
        "module_id": module_id,
        "envelope": published,
        "capability": published.get("capability"),
        "outcome": published.get("outcome"),
    }
