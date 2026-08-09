"""Run analysis modules with lock-free compute and atomic publish."""

from __future__ import annotations

from typing import Any, Sequence

from transcribe.analysis import ADAPTER_VERSION
from transcribe.analysis.adapter import build_page_v1_document, build_paragraph_v1_document
from transcribe.analysis.cache_identity import (
    build_cache_identity_object,
    cache_identity_hex,
    config_fingerprint,
)
from transcribe.analysis.chunking import (
    GROUND_DOC_CHUNKS_V1,
    GROUND_HIGHLIGHTS_SUMMARY_V1,
)
from transcribe.analysis.document import (
    GRANULARITY_PAGE_V1,
    SPLIT_PAGE,
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
from transcribe.analysis.envelope import build_envelope, filter_live_evidence
from transcribe.analysis.llm_runtime import TextLLMContext, bind_text_llm_context
from transcribe.analysis.modules import get_registered_modules
from transcribe.analysis.modules._llm_common import build_llm_object, prepared_excerpts
from transcribe.analysis.modules.narrative_summary import summary_prompt_fingerprint
from transcribe.analysis.parents import (
    batch_module_order,
    parent_payloads,
    parents_for_identity,
    resolve_hard_parents,
    resolve_optional_parents,
)
from transcribe.analysis.storage import AnalysisStorage
from transcribe.config.facade import bind_operation_config, snapshot_for_operation
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
        "highlights": "highlights_lexicon_or_model",
    }
    attr = loaders.get(mid)
    if not attr:
        return None
    # contextual_emotion reuses emotion lexicon helpers
    mod_name = "emotion" if mid == "contextual_emotion" else mid
    mod = __import__(f"transcribe.analysis.modules.{mod_name}", fromlist=[attr])
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
            return build_page_v1_document(project, project_service)
    return build_page_v1_document(project, project_service)


def _apply_eligibility(
    document: AnalysisDocument,
) -> tuple[AnalysisDocument | None, dict[str, Any] | None, dict[str, Any]]:
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


def _llm_fields_from_context(
    module: Any,
    document: AnalysisDocument,
    *,
    llm_ctx: TextLLMContext | None,
    question_text: str | None,
    parent_payload_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if module.module_id not in LLM_MODULES:
        return {"llm": None, "resolved_model_digest": None}

    model = llm_ctx.model_name if llm_ctx else None
    digest = llm_ctx.resolved_model_digest if llm_ctx else None
    question = question_text if module.module_id == "llm_custom_qa" else None

    if module.module_id == "narrative_summary":
        grounding = GROUND_HIGHLIGHTS_SUMMARY_V1
        summary = (parent_payload_map or {}).get("summary") or {}
        overview = str(summary.get("overview") or "")
        bullets = [str(b) for b in (summary.get("bullets") or []) if str(b).strip()]
        input_fp = summary_prompt_fingerprint(overview, bullets)
    else:
        grounding = GROUND_DOC_CHUNKS_V1
        meta = prepared_excerpts(document)
        input_fp = meta["input_fingerprint"]

    return {
        "resolved_model_digest": digest,
        "llm": build_llm_object(
            grounding_strategy_id=grounding,
            model=model,
            digest=digest,
            input_fingerprint=input_fp,
            question_text=question,
        ),
    }


def _identity_kwargs(
    module: Any,
    *,
    project_id: str,
    document: AnalysisDocument,
    parents: list,
    eligibility_meta: dict[str, Any] | None = None,
    llm_bits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    elig = eligibility_meta or {}
    bits = llm_bits or {"llm": None, "resolved_model_digest": None}
    return {
        "project_id": project_id,
        "module_id": module.module_id,
        "module_version": module.module_version,
        "document": document,
        "config": _module_config(module),
        "parents": parents_for_identity(parents),
        "lexicon_or_model": _module_lexicon(module),
        "eligibility_policy_id": elig.get("eligibility_policy_id"),
        "eligibility_policy_version": elig.get("eligibility_policy_version"),
        "eligibility_fingerprint": elig.get("eligibility_fingerprint"),
        "resolved_model_digest": bits.get("resolved_model_digest"),
        "llm": bits.get("llm"),
    }


def _empty_identity_obj(
    *,
    project_id: str,
    module: Any,
    llm_bits: dict[str, Any],
    empty_code: str,
) -> dict[str, Any]:
    empty_fp = config_fingerprint({"empty": True, "code": empty_code})
    return {
        "adapter_version": ADAPTER_VERSION,
        "cache_identity_version": 1,
        "config_fingerprint": empty_fp,
        "content_fingerprint": empty_fp,
        "content_fingerprint_version": 1,
        "eligibility_fingerprint": None,
        "eligibility_policy_id": None,
        "eligibility_policy_version": None,
        "granularity_version": GRANULARITY_PAGE_V1,
        "lexicon_or_model": _module_lexicon(module),
        "llm": llm_bits.get("llm"),
        "module_id": module.module_id,
        "module_version": module.module_version,
        "parents": [],
        "project_id": project_id,
        "resolved_model_digest": llm_bits.get("resolved_model_digest"),
        "split_profile": SPLIT_PAGE,
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

    def planned_cache_identity(
        self,
        module_id: str,
        *,
        question_text: str | None = None,
        project: Any | None = None,
        llm_ctx: TextLLMContext | None = None,
        _stack: frozenset[str] | None = None,
    ) -> str | None:
        """Compute the cache identity this module would plan against the current project.

        Returns None when the document cannot be built (empty / invalid). Used for
        UI freshness and hard-parent stale detection.
        """
        modules = get_registered_modules()
        module = modules.get(module_id)
        if module is None:
            raise KeyError(f"unknown module_id: {module_id}")
        stack = _stack or frozenset()
        if module_id in stack:
            return None
        project = project or self.project_service.load(reconcile=True)

        if module.module_id in LLM_MODULES and llm_ctx is None:
            llm_ctx = bind_text_llm_context(
                text_model_name=getattr(project.settings, "text_model_name", None),
                base_url=getattr(project.settings, "base_url", None),
            )

        def expected_identity(parent_id: str) -> str | None:
            return self.planned_cache_identity(
                parent_id,
                project=project,
                llm_ctx=None,
                _stack=stack | {module_id},
            )

        try:
            document = _build_document(project, self.project_service, module.module_id)
        except AnalysisDocumentError:
            return None

        eligibility_meta: dict[str, Any] | None = None
        if module.module_id in ELIGIBILITY_REQUIRED:
            filtered, skip, eligibility_meta = _apply_eligibility(document)
            if skip is not None:
                # Identity for skip path still binds to the pre-filter document.
                llm_bits = _llm_fields_from_context(
                    module,
                    document,
                    llm_ctx=llm_ctx,
                    question_text=question_text,
                    parent_payload_map={},
                )
                return cache_identity_hex(
                    build_cache_identity_object(
                        **_identity_kwargs(
                            module,
                            project_id=project.id,
                            document=document,
                            parents=[],
                            eligibility_meta=eligibility_meta,
                            llm_bits=llm_bits,
                        )
                    )
                )
            assert filtered is not None
            document = filtered

        ok, hard_parents, _ = resolve_hard_parents(
            module.module_id,
            storage=self.storage,
            expected_identity=expected_identity,
        )
        parents = hard_parents if ok else []
        optional = resolve_optional_parents(
            module.module_id,
            enrichment_mode=_module_enrichment_mode(module),
            storage=self.storage,
            expected_identity=expected_identity,
        )
        seen = {p["module_id"] for p in parents}
        parents = list(parents) + [p for p in optional if p["module_id"] not in seen]
        payloads = parent_payloads(parents)
        llm_bits = _llm_fields_from_context(
            module,
            document,
            llm_ctx=llm_ctx,
            question_text=question_text,
            parent_payload_map=payloads,
        )
        return cache_identity_hex(
            build_cache_identity_object(
                **_identity_kwargs(
                    module,
                    project_id=project.id,
                    document=document,
                    parents=parents,
                    eligibility_meta=eligibility_meta,
                    llm_bits=llm_bits,
                )
            )
        )

    def run_module(
        self,
        module_id: str,
        *,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        modules = get_registered_modules()
        module = modules.get(module_id)
        if module is None:
            raise KeyError(f"unknown module_id: {module_id}")

        project = self.project_service.load(reconcile=True)
        self.reconcile()
        snap = snapshot_for_operation(
            project_settings=project.settings,
            project_id=project.id,
        )
        with bind_operation_config(snap):
            return self._run_module_unlocked(
                module,
                project=project,
                question_text=question_text,
            )

    def _run_module_unlocked(
        self,
        module: Any,
        *,
        project: Any,
        question_text: str | None,
    ) -> dict[str, Any]:
        llm_ctx: TextLLMContext | None = None
        if module.module_id in LLM_MODULES:
            llm_ctx = bind_text_llm_context(
                text_model_name=getattr(project.settings, "text_model_name", None),
                base_url=getattr(project.settings, "base_url", None),
            )

        def expected_identity(parent_id: str) -> str | None:
            return self.planned_cache_identity(
                parent_id,
                project=project,
                llm_ctx=None,
            )

        try:
            document = _build_document(project, self.project_service, module.module_id)
        except AnalysisDocumentError as exc:
            return self._publish_with_revalidation(
                project_id=project.id,
                module=module,
                document=None,
                parents=[],
                result={
                    "outcome": "insufficient_data",
                    "payload": {"error": {"code": exc.code, "message": str(exc)}},
                    "warnings": [{"code": exc.code, "message": str(exc)}],
                    "capability_reason": "invalid_document",
                },
                eligibility_meta=None,
                llm_ctx=llm_ctx,
                question_text=question_text,
                empty_document=True,
                empty_code=exc.code,
            )

        eligibility_meta: dict[str, Any] | None = None
        if module.module_id in ELIGIBILITY_REQUIRED:
            filtered, skip, eligibility_meta = _apply_eligibility(document)
            if skip is not None:
                return self._publish_with_revalidation(
                    project_id=project.id,
                    module=module,
                    document=document,
                    parents=[],
                    result=skip,
                    eligibility_meta=eligibility_meta,
                    llm_ctx=llm_ctx,
                    question_text=question_text,
                )
            assert filtered is not None
            document = filtered

        ok, hard_parents, hard_fail = resolve_hard_parents(
            module.module_id,
            storage=self.storage,
            expected_identity=expected_identity,
        )
        if not ok and hard_fail is not None:
            return self._publish_with_revalidation(
                project_id=project.id,
                module=module,
                document=document,
                parents=[],
                result=hard_fail,
                eligibility_meta=eligibility_meta,
                llm_ctx=llm_ctx,
                question_text=question_text,
            )

        optional = resolve_optional_parents(
            module.module_id,
            enrichment_mode=_module_enrichment_mode(module),
            storage=self.storage,
            expected_identity=expected_identity,
        )
        seen = {p["module_id"] for p in hard_parents}
        parents = list(hard_parents) + [p for p in optional if p["module_id"] not in seen]
        payloads = parent_payloads(parents)

        llm_bits = _llm_fields_from_context(
            module,
            document,
            llm_ctx=llm_ctx,
            question_text=question_text,
            parent_payload_map=payloads,
        )
        planned_identity_obj = build_cache_identity_object(
            **_identity_kwargs(
                module,
                project_id=project.id,
                document=document,
                parents=parents,
                eligibility_meta=eligibility_meta,
                llm_bits=llm_bits,
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
            parents=parents_for_identity(parents),
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
            result = module.run(
                document,
                parents=payloads,
                llm_ctx=llm_ctx,
                question_text=question_text,
            )
            outcome = result["outcome"]
            payload = result.get("payload") or {}
            warnings = list(result.get("warnings") or [])
            partial = bool(result.get("partial"))
            capability_reason = result.get("capability_reason")
            evidence = result.get("evidence")
            diagnostics = result.get("diagnostics")
            attempt_state = "failed" if outcome == "failed" else "succeeded"
        except Exception as exc:  # noqa: BLE001
            outcome = "failed"
            payload = {"error": {"code": "module_exception", "message": str(exc)}}
            warnings = [{"code": "module_exception", "message": str(exc)}]
            partial = False
            capability_reason = None
            diagnostics = None
            attempt_state = "failed"

        if diagnostics and isinstance(diagnostics, dict):
            raw_b = diagnostics.get("raw_bounded")
            if raw_b:
                warnings = list(warnings) + [
                    {"code": "llm_diagnostics", "message": str(raw_b)[:500]}
                ]

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
            parents=parents_for_identity(parents),
            attempt_id=attempt_id,
            published=False,
            lexicon_or_model=_module_lexicon(module),
            resolved_model_digest=resolved_digest,
            llm=llm_obj,
            evidence=evidence,
        )
        return self._publish_terminal(
            module=module,
            terminal=terminal,
            planned_identity=planned_identity,
            planned_llm_bits=llm_bits,
            attempt_id=attempt_id,
            question_text=question_text,
        )

    def run_batch(self, module_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
        ids = module_ids or list(get_registered_modules().keys())
        ids = batch_module_order(ids)
        project = self.project_service.load(reconcile=True)
        self.reconcile()
        snap = snapshot_for_operation(
            project_settings=project.settings,
            project_id=project.id,
        )
        modules = get_registered_modules()
        results: dict[str, dict[str, Any]] = {}
        with bind_operation_config(snap):
            for mid in ids:
                try:
                    module = modules.get(mid)
                    if module is None:
                        raise KeyError(f"unknown module_id: {mid}")
                    results[mid] = self._run_module_unlocked(
                        module,
                        project=project,
                        question_text=None,
                    )
                except Exception as exc:  # noqa: BLE001
                    results[mid] = {
                        "module_id": mid,
                        "attempt_state": "failed",
                        "outcome": "failed",
                        "capability": "failed",
                        "payload": {"error": {"message": str(exc)}},
                    }
        return results

    def _revalidate_identity(
        self,
        *,
        module: Any,
        planned_llm_bits: dict[str, Any],
        question_text: str | None,
        planned_identity: str,
        project_id: str,
    ) -> str:
        """Rebuild identity under lock using planned LLM bits (no network)."""
        _ = planned_identity
        project_now = self.project_service._load_unlocked(reconcile=False)

        def expected_identity(parent_id: str) -> str | None:
            return self.planned_cache_identity(
                parent_id,
                project=project_now,
                llm_ctx=None,
            )

        try:
            doc_now = _build_document(
                project_now, self.project_service, module.module_id
            )
            elig_now: dict[str, Any] | None = None
            if module.module_id in ELIGIBILITY_REQUIRED:
                filtered_now, skip_now, elig_now = _apply_eligibility(doc_now)
                if skip_now is None and filtered_now is not None:
                    doc_now = filtered_now
            ok_now, hard_now, _ = resolve_hard_parents(
                module.module_id,
                storage=self.storage,
                expected_identity=expected_identity,
            )
            parents_now = hard_now if ok_now else []
            opt_now = resolve_optional_parents(
                module.module_id,
                enrichment_mode=_module_enrichment_mode(module),
                storage=self.storage,
                expected_identity=expected_identity,
            )
            seen = {p["module_id"] for p in parents_now}
            parents_now = parents_now + [p for p in opt_now if p["module_id"] not in seen]
            payloads_now = parent_payloads(parents_now)
            llm_bits_now = dict(planned_llm_bits)
            if module.module_id in LLM_MODULES and planned_llm_bits.get("llm"):
                digest = planned_llm_bits.get("resolved_model_digest") or ""
                model = (planned_llm_bits.get("llm") or {}).get("model_name") or ""
                refreshed = _llm_fields_from_context(
                    module,
                    doc_now,
                    llm_ctx=(
                        TextLLMContext(
                            client=None,
                            model_name=model,
                            resolved_model_digest=digest,
                        )
                        if digest
                        else None
                    ),
                    question_text=question_text,
                    parent_payload_map=payloads_now,
                )
                if refreshed.get("llm") and planned_llm_bits.get("llm"):
                    llm_obj = dict(planned_llm_bits["llm"])
                    llm_obj["input_fingerprint"] = refreshed["llm"]["input_fingerprint"]
                    llm_obj["question_text"] = refreshed["llm"].get("question_text")
                    llm_bits_now = {
                        "resolved_model_digest": planned_llm_bits.get(
                            "resolved_model_digest"
                        ),
                        "llm": llm_obj,
                    }
            return cache_identity_hex(
                build_cache_identity_object(
                    **_identity_kwargs(
                        module,
                        project_id=project_now.id,
                        document=doc_now,
                        parents=parents_now,
                        eligibility_meta=elig_now,
                        llm_bits=llm_bits_now,
                    )
                )
            )
        except AnalysisDocumentError as exc:
            obj = _empty_identity_obj(
                project_id=project_id,
                module=module,
                llm_bits=planned_llm_bits,
                empty_code=exc.code,
            )
            return cache_identity_hex(obj)

    def _publish_terminal(
        self,
        *,
        module: Any,
        terminal: dict[str, Any],
        planned_identity: str,
        planned_llm_bits: dict[str, Any],
        attempt_id: str,
        question_text: str | None,
    ) -> dict[str, Any]:
        with mutation_lock(self.paths.mutation_lock):
            self.storage.write_attempt(module.module_id, terminal)
            identity_now = self._revalidate_identity(
                module=module,
                planned_llm_bits=planned_llm_bits,
                question_text=question_text,
                planned_identity=planned_identity,
                project_id=terminal.get("project_id") or "",
            )
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

    def _publish_with_revalidation(
        self,
        *,
        project_id: str,
        module: Any,
        document: AnalysisDocument | None,
        parents: list,
        result: dict[str, Any],
        eligibility_meta: dict[str, Any] | None,
        llm_ctx: TextLLMContext | None,
        question_text: str | None,
        empty_document: bool = False,
        empty_code: str | None = None,
    ) -> dict[str, Any]:
        if empty_document or document is None:
            if module.module_id in LLM_MODULES:
                llm_bits = {
                    "resolved_model_digest": (
                        llm_ctx.resolved_model_digest if llm_ctx else None
                    ),
                    "llm": build_llm_object(
                        grounding_strategy_id=(
                            GROUND_HIGHLIGHTS_SUMMARY_V1
                            if module.module_id == "narrative_summary"
                            else GROUND_DOC_CHUNKS_V1
                        ),
                        model=llm_ctx.model_name if llm_ctx else None,
                        digest=llm_ctx.resolved_model_digest if llm_ctx else None,
                        input_fingerprint=config_fingerprint({"empty": True}),
                        question_text=(
                            question_text if module.module_id == "llm_custom_qa" else None
                        ),
                    ),
                }
            else:
                llm_bits = {"llm": None, "resolved_model_digest": None}
            identity_obj = _empty_identity_obj(
                project_id=project_id,
                module=module,
                llm_bits=llm_bits,
                empty_code=empty_code or "empty",
            )
            planned_identity = cache_identity_hex(identity_obj)
            content_fp = identity_obj["content_fingerprint"]
            cfg_fp = identity_obj["config_fingerprint"]
            resolved_digest = identity_obj.get("resolved_model_digest")
            llm_obj = identity_obj.get("llm")
        else:
            llm_bits = _llm_fields_from_context(
                module,
                document,
                llm_ctx=llm_ctx,
                question_text=question_text,
                parent_payload_map=parent_payloads(parents),
            )
            planned_identity_obj = build_cache_identity_object(
                **_identity_kwargs(
                    module,
                    project_id=project_id,
                    document=document,
                    parents=parents,
                    eligibility_meta=eligibility_meta,
                    llm_bits=llm_bits,
                )
            )
            planned_identity = cache_identity_hex(planned_identity_obj)
            content_fp = planned_identity_obj["content_fingerprint"]
            cfg_fp = planned_identity_obj["config_fingerprint"]
            resolved_digest = planned_identity_obj.get("resolved_model_digest")
            llm_obj = planned_identity_obj.get("llm")

        attempt_id = self.ids.new_id()
        envelope = build_envelope(
            project_id=project_id,
            module_id=module.module_id,
            module_version=module.module_version,
            cache_identity=planned_identity,
            content_fingerprint=content_fp,
            attempt_state="succeeded",
            outcome=result["outcome"],
            payload=result.get("payload") or {},
            provenance=_module_provenance(module),
            config_fingerprint=cfg_fp,
            warnings=result.get("warnings") or [],
            partial=bool(result.get("partial")),
            capability_reason=result.get("capability_reason"),
            parents=parents_for_identity(parents),
            attempt_id=attempt_id,
            published=False,
            lexicon_or_model=_module_lexicon(module),
            resolved_model_digest=resolved_digest,
            llm=llm_obj,
        )
        return self._publish_terminal(
            module=module,
            terminal=envelope,
            planned_identity=planned_identity,
            planned_llm_bits=llm_bits,
            attempt_id=attempt_id,
            question_text=question_text,
        )


def load_published_read_model(
    storage: AnalysisStorage,
    module_id: str,
    *,
    current_cache_identity: str | None,
    current_content_fingerprint: str | None = None,
) -> dict[str, Any]:
    """UI read-model: validated published only; classify stale/unavailable.

    When ``current_cache_identity`` is None, results are classified as ``stale``
    (not safely current). Live evidence is filtered against
    ``current_content_fingerprint`` when status is ``ok``.
    """
    published = storage.read_published(module_id)
    if published is None:
        return {
            "status": "unavailable",
            "module_id": module_id,
            "envelope": None,
            "live_evidence": [],
        }
    if current_cache_identity is None:
        return {
            "status": "stale",
            "module_id": module_id,
            "envelope": published,
            "live_evidence": [],
        }
    if published.get("cache_identity") != current_cache_identity:
        return {
            "status": "stale",
            "module_id": module_id,
            "envelope": published,
            "live_evidence": [],
        }
    fp = current_content_fingerprint
    if fp is None:
        fp = published.get("content_fingerprint")
    return {
        "status": "ok",
        "module_id": module_id,
        "envelope": published,
        "capability": published.get("capability"),
        "outcome": published.get("outcome"),
        "live_evidence": filter_live_evidence(
            published.get("evidence"),
            current_content_fingerprint=fp,
        ),
    }


def module_freshness(
    runner: AnalysisRunner,
    storage: AnalysisStorage,
    module_ids: Sequence[str],
    *,
    question_text: str | None = None,
) -> list[dict[str, Any]]:
    """Authoritative UI freshness for published modules via planned cache identity.

    The UI must not construct cache identities itself — always call this (or
    ``planned_cache_identity`` + ``load_published_read_model``).
    """
    out: list[dict[str, Any]] = []
    for mid in module_ids:
        identity = runner.planned_cache_identity(mid, question_text=question_text)
        out.append(
            load_published_read_model(
                storage, mid, current_cache_identity=identity
            )
        )
    return out
