"""Run analysis modules with lock-free compute and atomic publish."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.adapter import build_page_v1_document, build_paragraph_v1_document
from transcribe.analysis.cache_identity import (
    build_cache_identity_object,
    cache_identity_hex,
    config_fingerprint,
)
from transcribe.analysis.chunking import (
    CHUNKING_UNITS_V1,
    GROUND_DOC_CHUNKS_V1,
    GROUND_HIGHLIGHTS_SUMMARY_V1,
    chunks_fingerprint,
    pack_units_v1,
)
from transcribe.analysis.document import (
    AnalysisDocument,
    AnalysisDocumentError,
    concatenate_document_text,
    validate_analysis_document,
)
from transcribe.analysis.eligibility import (
    POLICY_ID,
    POLICY_VERSION,
    eligibility_fingerprint,
    evaluate_notebook_eligibility_v1,
)
from transcribe.analysis.envelope import build_envelope
from transcribe.analysis.modules import get_registered_modules
from transcribe.analysis.modules._llm_common import GENERATION_SETTINGS, PROMPT_VERSION
from transcribe.analysis.parents import (
    batch_module_order,
    parent_payloads,
    resolve_hard_parents,
    resolve_optional_parents,
)
from transcribe.analysis.storage import AnalysisStorage
from transcribe.persistence.locks import mutation_lock
from transcribe.ports import Clock, IdGenerator
from transcribe.services.project import ProjectService

ELIGIBILITY_REQUIRED = frozenset(
    {"keyphrases", "topic_modeling", "bertopic", "highlights", "insights"}
)
PARAGRAPH_PREFERRED = frozenset({"highlights", "llm_custom_qa", "moments"})
LLM_MODULES = frozenset(
    {"llm_summary", "llm_action_items", "llm_custom_qa", "narrative_summary"}
)


def _module_config(module: Any) -> dict[str, Any]:
    fn = getattr(module, "cache_config", None)
    if callable(fn):
        return dict(fn())
    mid = getattr(module, "module_id", "")
    if mid == "wordclouds":
        from transcribe.analysis.modules import wordclouds as wc

        return wc.wordclouds_config()
    return {}


def _module_lexicon(module: Any) -> Any:
    mid = getattr(module, "module_id", "")
    loaders = {
        "wordclouds": "wordclouds_lexicon_or_model",
        "ner": "ner_lexicon_or_model",
        "sentiment": "sentiment_lexicon_or_model",
        "epistemic_markers": "epistemic_lexicon_or_model",
        "emotion": "emotion_lexicon_or_model",
        "contextual_emotion": "emotion_lexicon_or_model",
    }
    attr = loaders.get(mid)
    if not attr:
        return None
    mod = __import__(f"transcribe.analysis.modules.{mid}", fromlist=[attr])
    return getattr(mod, attr)()


def _module_enrichment_mode(module: Any) -> str:
    mid = getattr(module, "module_id", "")
    if mid == "wordclouds":
        from transcribe.analysis.modules import wordclouds as wc

        return wc.ENRICHMENT_MODE
    if mid in {"topic_modeling", "bertopic"}:
        return "baseline"
    return "none"


def _module_provenance(module: Any) -> dict[str, Any]:
    mid = module.module_id
    try:
        mod = __import__(f"transcribe.analysis.modules.{mid}", fromlist=["provenance_files"])
        files_fn = getattr(mod, "provenance_files", lambda: [])
        files = files_fn()
    except Exception:  # noqa: BLE001
        files = []
    commit = getattr(module, "ported_from_commit", None)
    if commit is None:
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


def _build_document(project: Any, project_service: ProjectService, module_id: str) -> AnalysisDocument:
    if module_id in PARAGRAPH_PREFERRED:
        try:
            return build_paragraph_v1_document(project, project_service)
        except AnalysisDocumentError:
            # Fall back to page units if paragraph split yields nothing useful.
            return build_page_v1_document(project, project_service)
    return build_page_v1_document(project, project_service)


def _apply_eligibility(
    document: AnalysisDocument,
) -> tuple[AnalysisDocument | None, dict[str, Any] | None, dict[str, Any]]:
    """Return (filtered_doc_or_None, skip_result, eligibility_meta)."""
    elig = evaluate_notebook_eligibility_v1(document.units)
    meta = {
        "eligibility_policy_id": POLICY_ID,
        "eligibility_policy_version": POLICY_VERSION,
        "eligibility_fingerprint": eligibility_fingerprint(elig),
        "eligibility": elig,
    }
    eligible_ids = set(elig["eligible_unit_ids"])
    if not eligible_ids:
        return (
            None,
            {
                "outcome": "skipped_not_applicable",
                "payload": {},
                "warnings": [
                    {
                        "code": "no_eligible_units",
                        "message": "notebook_eligibility_v1 produced empty set",
                    }
                ],
            },
            meta,
        )
    units = [u for u in document.units if u.unit_id in eligible_ids]
    filtered = AnalysisDocument(
        document_id=document.document_id,
        text=concatenate_document_text(units),
        units=units,
        granularity_version=document.granularity_version,
        split_profile=document.split_profile,
    )
    return validate_analysis_document(filtered), None, meta


def _llm_fields(module: Any, document: AnalysisDocument) -> dict[str, Any]:
    if module.module_id not in LLM_MODULES:
        return {"llm": None, "resolved_model_digest": None}
    from transcribe.analysis.llm_runtime import get_text_llm_client

    client = get_text_llm_client()
    model = client.resolve_model() if client.healthcheck() else None
    digest = client.model_digest(model) if model else None
    question = getattr(module, "question_text", None) or None
    grounding = (
        GROUND_HIGHLIGHTS_SUMMARY_V1
        if module.module_id == "narrative_summary"
        else GROUND_DOC_CHUNKS_V1
    )
    chunks = pack_units_v1(document)
    return {
        "resolved_model_digest": digest,
        "llm": {
            "prompt_or_template_version": PROMPT_VERSION,
            "generation_settings": dict(GENERATION_SETTINGS),
            "grounding_strategy_id": grounding,
            "chunking_policy_id": CHUNKING_UNITS_V1,
            "question_text": question if module.module_id == "llm_custom_qa" else None,
            "resolved_model_digest": digest,
            "input_fingerprint": chunks_fingerprint(chunks),
            "model_name": model,
        },
    }


def _identity_kwargs(
    module: Any,
    *,
    project_id: str,
    document: AnalysisDocument,
    parents: list,
    eligibility_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    elig = eligibility_meta or {}
    llm_bits = _llm_fields(module, document)
    return {
        "project_id": project_id,
        "module_id": module.module_id,
        "module_version": module.module_version,
        "document": document,
        "config": _module_config(module),
        "parents": parents,
        "lexicon_or_model": _module_lexicon(module),
        "eligibility_policy_id": elig.get("eligibility_policy_id"),
        "eligibility_policy_version": elig.get("eligibility_policy_version"),
        "eligibility_fingerprint": elig.get("eligibility_fingerprint"),
        "resolved_model_digest": llm_bits.get("resolved_model_digest"),
        "llm": llm_bits.get("llm"),
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
        modules = get_registered_modules()
        module = modules.get(module_id)
        if module is None:
            raise KeyError(f"unknown module_id: {module_id}")

        project = self.project_service.load(reconcile=True)
        self.reconcile()

        try:
            document = _build_document(project, self.project_service, module.module_id)
        except AnalysisDocumentError as exc:
            return self._publish_preflight_insufficient(
                project_id=project.id,
                module=module,
                code=exc.code,
                message=str(exc),
            )

        eligibility_meta: dict[str, Any] | None = None
        if module.module_id in ELIGIBILITY_REQUIRED:
            filtered, skip, eligibility_meta = _apply_eligibility(document)
            if skip is not None:
                return self._publish_terminal_from_result(
                    project_id=project.id,
                    module=module,
                    document=document,
                    parents=[],
                    result=skip,
                    eligibility_meta=eligibility_meta,
                )
            assert filtered is not None
            document = filtered

        ok, hard_parents, hard_fail = resolve_hard_parents(
            module.module_id, storage=self.storage
        )
        if not ok and hard_fail is not None:
            return self._publish_terminal_from_result(
                project_id=project.id,
                module=module,
                document=document,
                parents=[],
                result=hard_fail,
                eligibility_meta=eligibility_meta,
            )

        optional = resolve_optional_parents(
            module.module_id,
            enrichment_mode=_module_enrichment_mode(module),
            storage=self.storage,
        )
        # Prefer hard parents; merge optional not already present.
        seen = {p["module_id"] for p in hard_parents}
        parents = list(hard_parents) + [p for p in optional if p["module_id"] not in seen]

        planned_identity_obj = build_cache_identity_object(
            **_identity_kwargs(
                module,
                project_id=project.id,
                document=document,
                parents=parents,
                eligibility_meta=eligibility_meta,
            )
        )
        planned_identity = cache_identity_hex(planned_identity_obj)
        content_fp = planned_identity_obj["content_fingerprint"]
        cfg_fp = planned_identity_obj["config_fingerprint"]
        llm_obj = planned_identity_obj.get("llm")
        resolved_digest = planned_identity_obj.get("resolved_model_digest")

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
            outcome="insufficient_data",
            payload={},
            provenance=_module_provenance(module),
            config_fingerprint=cfg_fp,
            parents=parents,
            attempt_id=attempt_id,
            published=False,
            lexicon_or_model=_module_lexicon(module),
            resolved_model_digest=resolved_digest,
            llm=llm_obj,
        )
        with mutation_lock(self.paths.mutation_lock):
            self.storage.write_attempt(module.module_id, running)

        evidence = None
        try:
            payloads = parent_payloads(self.storage, parents)
            run_fn = module.run
            try:
                result = run_fn(document, parents=payloads)
            except TypeError:
                result = run_fn(document)
            outcome = result["outcome"]
            payload = result.get("payload") or {}
            warnings = result.get("warnings") or []
            partial = bool(result.get("partial"))
            capability_reason = result.get("capability_reason")
            evidence = result.get("evidence")
            attempt_state = "failed" if outcome == "failed" else "succeeded"
        except Exception as exc:  # noqa: BLE001
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
            parents=parents,
            attempt_id=attempt_id,
            published=False,
            lexicon_or_model=_module_lexicon(module),
            resolved_model_digest=resolved_digest,
            llm=llm_obj,
            evidence=evidence,
        )
        with mutation_lock(self.paths.mutation_lock):
            self.storage.write_attempt(module.module_id, terminal)
            project_now = self.project_service._load_unlocked(reconcile=False)
            try:
                doc_now = _build_document(
                    project_now, self.project_service, module.module_id
                )
                elig_now = eligibility_meta
                if module.module_id in ELIGIBILITY_REQUIRED:
                    filtered_now, skip_now, elig_now = _apply_eligibility(doc_now)
                    if skip_now is None and filtered_now is not None:
                        doc_now = filtered_now
                ok_now, hard_now, _ = resolve_hard_parents(
                    module.module_id, storage=self.storage
                )
                parents_now = hard_now if ok_now else []
                opt_now = resolve_optional_parents(
                    module.module_id,
                    enrichment_mode=_module_enrichment_mode(module),
                    storage=self.storage,
                )
                seen = {p["module_id"] for p in parents_now}
                parents_now = parents_now + [
                    p for p in opt_now if p["module_id"] not in seen
                ]
                identity_now = cache_identity_hex(
                    build_cache_identity_object(
                        **_identity_kwargs(
                            module,
                            project_id=project_now.id,
                            document=doc_now,
                            parents=parents_now,
                            eligibility_meta=elig_now,
                        )
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
            return self.storage.read_attempt(module.module_id, attempt_id) or terminal

    def run_batch(self, module_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
        ids = module_ids or list(get_registered_modules().keys())
        ids = batch_module_order(ids)
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

    def _publish_terminal_from_result(
        self,
        *,
        project_id: str,
        module: Any,
        document: AnalysisDocument,
        parents: list,
        result: dict[str, Any],
        eligibility_meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        planned_identity_obj = build_cache_identity_object(
            **_identity_kwargs(
                module,
                project_id=project_id,
                document=document,
                parents=parents,
                eligibility_meta=eligibility_meta,
            )
        )
        planned_identity = cache_identity_hex(planned_identity_obj)
        attempt_id = self.ids.new_id()
        envelope = build_envelope(
            project_id=project_id,
            module_id=module.module_id,
            module_version=module.module_version,
            cache_identity=planned_identity,
            content_fingerprint=planned_identity_obj["content_fingerprint"],
            attempt_state="succeeded",
            outcome=result["outcome"],
            payload=result.get("payload") or {},
            provenance=_module_provenance(module),
            config_fingerprint=planned_identity_obj["config_fingerprint"],
            warnings=result.get("warnings") or [],
            partial=bool(result.get("partial")),
            capability_reason=result.get("capability_reason"),
            parents=parents,
            attempt_id=attempt_id,
            published=False,
            lexicon_or_model=_module_lexicon(module),
            resolved_model_digest=planned_identity_obj.get("resolved_model_digest"),
            llm=planned_identity_obj.get("llm"),
        )
        with mutation_lock(self.paths.mutation_lock):
            self.storage.write_attempt(module.module_id, envelope)
            self.storage.publish_if_current(
                module_id=module.module_id,
                envelope=envelope,
                expected_cache_identity=planned_identity,
                current_cache_identity=planned_identity,
            )
            return self.storage.read_published(module.module_id) or envelope

    def _publish_preflight_insufficient(
        self,
        *,
        project_id: str,
        module: Any,
        code: str,
        message: str,
    ) -> dict[str, Any]:
        attempt_id = self.ids.new_id()
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
            "lexicon_or_model": _module_lexicon(module),
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
            parents=[],
            attempt_id=attempt_id,
            published=False,
            lexicon_or_model=_module_lexicon(module),
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
