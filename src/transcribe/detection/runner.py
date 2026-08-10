"""Run detection with lock-free compute and atomic publish."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.cache_identity import config_fingerprint
from transcribe.analysis.llm_runtime import TextLLMContext, bind_text_llm_context
from transcribe.config.facade import bind_operation_config, snapshot_for_operation
from transcribe.config.knobs import llm_generation_options
from transcribe.detection.aggregate import merge_adjacent_spans, raw_from_window_response
from transcribe.detection.cache_identity import build_cache_identity_object, cache_identity_hex
from transcribe.detection.candidates import select_candidates
from transcribe.detection.custom import load_custom_detectors
from transcribe.detection.definition import DetectorDefinition
from transcribe.detection.envelope import build_detection_envelope
from transcribe.detection.findings import DetectionFinding, findings_to_dicts, utc_now_iso
from transcribe.detection.inputs import load_render_bytes, scope_fingerprint
from transcribe.detection.registry import resolve_detector
from transcribe.detection.routing import resolve_model_route
from transcribe.detection.scope import plan_windows
from transcribe.detection.storage import DetectionStorage
from transcribe.persistence.locks import mutation_lock
from transcribe.prompt_engine.definition import InputMode
from transcribe.prompt_engine.execute import execute_prompt
from transcribe.prompt_engine.registry import get_prompt
from transcribe.providers.vision_llm import VisionLLMContext, bind_vision_llm_context
from transcribe.ports import Clock, IdGenerator
from transcribe.services.project import ProjectService


class DetectionRunner:
    def __init__(
        self,
        project_service: ProjectService,
        *,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
        text_ctx: TextLLMContext | None = None,
        vision_ctx: VisionLLMContext | None = None,
    ) -> None:
        from transcribe.ports import SystemClock, UuidGenerator

        self.project_service = project_service
        self.paths = project_service.paths
        self.storage = DetectionStorage(self.paths)
        self.clock = clock or SystemClock()
        self.ids = ids or UuidGenerator()
        self._text_ctx = text_ctx
        self._vision_ctx = vision_ctx

    def _bind_contexts(self) -> tuple[TextLLMContext | None, VisionLLMContext | None]:
        if self._text_ctx is not None or self._vision_ctx is not None:
            return self._text_ctx, self._vision_ctx
        from transcribe.config.facade import get_config

        cfg = get_config()
        text = bind_text_llm_context(
            text_model_name=cfg.ocr.text_model_name or cfg.llm.text_model_preference,
            base_url=cfg.ocr.base_url,
        )
        vision = bind_vision_llm_context(
            model_name=cfg.ocr.model_name,
            base_url=cfg.ocr.base_url,
        )
        return text, vision

    def planned_cache_identity(
        self,
        detector: DetectorDefinition,
        *,
        page_ids: list[str] | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        project = self.project_service.load(reconcile=False)
        page_inputs, _ = select_candidates(
            detector,
            project,
            self.project_service,
            self.paths,
            page_ids=page_ids,
        )
        prompt = get_prompt(
            detector.prompt_ref.prompt_id,
            version=detector.prompt_ref.version,
        )
        if prompt is None:
            raise ValueError(f"unknown prompt: {detector.prompt_ref}")
        text_ctx, vision_ctx = self._bind_contexts()
        route = resolve_model_route(
            detector,
            prompt,
            text_ctx=text_ctx,
            vision_ctx=vision_ctx,
            page_has_text=bool(page_inputs),
        )
        gen = llm_generation_options(snapshot_for_operation())
        identity_obj = build_cache_identity_object(
            notebook_id=project.id,
            detector=detector,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            page_inputs=page_inputs,
            model_digest=route.model_digest if route else None,
            generation_settings=gen,
        )
        sf = scope_fingerprint(page_inputs)
        return cache_identity_hex(identity_obj), sf, identity_obj

    def run_detector(
        self,
        detector_id: str,
        *,
        page_ids: list[str] | None = None,
        force: bool = False,
        cancel_check: Any | None = None,
    ) -> dict[str, Any]:
        custom = load_custom_detectors()
        detector = resolve_detector(detector_id, custom_detectors=custom)
        if detector is None:
            raise ValueError(f"unknown detector: {detector_id}")

        planned_id, scope_fp, _ = self.planned_cache_identity(
            detector, page_ids=page_ids
        )
        if not force:
            cached = self.storage.validate_cache_hit(
                detector_id=detector_id,
                expected_cache_identity=planned_id,
                expected_detector_version=detector.version,
            )
            if cached is not None:
                return cached

        attempt_id = self.ids.new_id()
        project = self.project_service.load(reconcile=False)
        running = build_detection_envelope(
            notebook_id=project.id,
            detector_id=detector_id,
            detector_version=detector.version,
            cache_identity=planned_id,
            scope_fingerprint=scope_fp,
            attempt_state="running",
            outcome="success",
            findings=[],
            pages_scanned=[],
            windows_scanned=0,
            config_fingerprint=config_fingerprint(detector.cache_config()),
            attempt_id=attempt_id,
            published=False,
        )
        with mutation_lock(self.paths.mutation_lock):
            self.storage.write_attempt(detector_id, running)

        with bind_operation_config(snapshot_for_operation()):
            terminal = self._execute_run(
                detector,
                attempt_id=attempt_id,
                planned_cache_identity=planned_id,
                page_ids=page_ids,
                cancel_check=cancel_check,
            )

        current_id, _, _ = self.planned_cache_identity(detector, page_ids=page_ids)
        with mutation_lock(self.paths.mutation_lock):
            self.storage.write_attempt(detector_id, terminal)
            self.storage.publish_if_current(
                detector_id=detector_id,
                envelope=terminal,
                expected_cache_identity=planned_id,
                current_cache_identity=current_id,
            )
        return terminal

    def _execute_run(
        self,
        detector: DetectorDefinition,
        *,
        attempt_id: str,
        planned_cache_identity: str,
        page_ids: list[str] | None,
        cancel_check: Any | None,
    ) -> dict[str, Any]:
        project = self.project_service.load(reconcile=False)
        page_inputs, warnings = select_candidates(
            detector,
            project,
            self.project_service,
            self.paths,
            page_ids=page_ids,
        )
        scope_fp = scope_fingerprint(page_inputs)
        prompt = get_prompt(
            detector.prompt_ref.prompt_id,
            version=detector.prompt_ref.version,
        )
        if prompt is None:
            return build_detection_envelope(
                notebook_id=project.id,
                detector_id=detector.detector_id,
                detector_version=detector.version,
                cache_identity=planned_cache_identity,
                scope_fingerprint=scope_fp,
                attempt_state="failed",
                outcome="failed",
                findings=[],
                pages_scanned=[],
                windows_scanned=0,
                config_fingerprint=config_fingerprint(detector.cache_config()),
                warnings=[{"code": "missing_prompt", "message": "prompt not found"}],
                attempt_id=attempt_id,
            )

        if not page_inputs:
            return build_detection_envelope(
                notebook_id=project.id,
                detector_id=detector.detector_id,
                detector_version=detector.version,
                cache_identity=planned_cache_identity,
                scope_fingerprint=scope_fp,
                attempt_state="succeeded",
                outcome="insufficient_data",
                findings=[],
                pages_scanned=[],
                windows_scanned=0,
                config_fingerprint=config_fingerprint(detector.cache_config()),
                warnings=warnings
                + [{"code": "no_pages", "message": "no candidate pages with text"}],
                attempt_id=attempt_id,
            )

        text_ctx, vision_ctx = self._bind_contexts()
        route = resolve_model_route(
            detector,
            prompt,
            text_ctx=text_ctx,
            vision_ctx=vision_ctx,
            page_has_text=True,
        )
        if route is None:
            return build_detection_envelope(
                notebook_id=project.id,
                detector_id=detector.detector_id,
                detector_version=detector.version,
                cache_identity=planned_cache_identity,
                scope_fingerprint=scope_fp,
                attempt_state="succeeded",
                outcome="skipped_not_applicable",
                findings=[],
                pages_scanned=[p.page_id for p in page_inputs],
                windows_scanned=0,
                config_fingerprint=config_fingerprint(detector.cache_config()),
                warnings=[{"code": "unavailable_model", "message": "no suitable model"}],
                capability_reason="unavailable_model",
                attempt_id=attempt_id,
            )

        gen = llm_generation_options(snapshot_for_operation())
        windows = plan_windows(detector, page_inputs)
        ordered_page_ids = [p.page_id for p in sorted(page_inputs, key=lambda x: x.page_order_index)]
        raw_hits = []
        window_failures = 0

        for window in windows:
            if cancel_check and cancel_check():
                return build_detection_envelope(
                    notebook_id=project.id,
                    detector_id=detector.detector_id,
                    detector_version=detector.version,
                    cache_identity=planned_cache_identity,
                    scope_fingerprint=scope_fp,
                    attempt_state="cancelled",
                    outcome="failed",
                    findings=[],
                    pages_scanned=ordered_page_ids,
                    windows_scanned=len(windows),
                    config_fingerprint=config_fingerprint(detector.cache_config()),
                    warnings=warnings,
                    attempt_id=attempt_id,
                )
            try:
                slots: dict[str, str] = {"content": window.combined_text, "page_labels": window.page_labels}
                if detector.extra_config.get("instruction"):
                    slots["instruction"] = str(detector.extra_config["instruction"])
                image_bytes: list[bytes] = []
                if route.input_mode == InputMode.VISION:
                    for pid in window.page_ids:
                        page = next(p for p in project.pages if p.page_id == pid)
                        data = load_render_bytes(project, self.paths, page)
                        if data:
                            image_bytes.append(data)
                executor = (
                    vision_ctx.client if route.input_mode == InputMode.VISION else text_ctx.client
                )
                result = execute_prompt(
                    prompt,
                    slots=slots,
                    model=route.model_name,
                    executor=executor,
                    input_mode=route.input_mode,
                    generation_options=gen,
                    image_bytes_list=image_bytes or None,
                )
                if result.warning:
                    warnings.append(result.warning)
                if result.parsed:
                    raw = raw_from_window_response(
                        parsed=result.parsed,
                        window_page_ids=window.page_ids,
                        ordered_page_ids=ordered_page_ids,
                        finding_type=detector.finding_type,
                        input_fingerprint=window.input_fingerprint(),
                        window_id=window.window_id,
                    )
                    if raw is not None:
                        raw_hits.append(raw)
            except Exception as exc:  # noqa: BLE001
                window_failures += 1
                warnings.append(
                    {
                        "code": "window_failed",
                        "message": f"window {window.window_id}: {exc}",
                    }
                )

        merged = merge_adjacent_spans(
            raw_hits,
            ordered_page_ids=ordered_page_ids,
            confidence_threshold=detector.confidence_threshold,
        )
        now = utc_now_iso()
        findings: list[DetectionFinding] = []
        prompt_prov = detector.prompt_ref.as_dict()
        model_prov = {
            "model_name": route.model_name,
            "model_digest": route.model_digest,
            "input_mode": route.input_mode.value,
        }
        for raw in merged:
            findings.append(
                DetectionFinding(
                    finding_id=self.ids.new_id(),
                    detector_id=detector.detector_id,
                    detector_version=detector.version,
                    notebook_id=project.id,
                    start_page_id=raw.page_ids[0],
                    end_page_id=raw.page_ids[-1],
                    finding_type=raw.finding_type,
                    confidence=raw.confidence,
                    evidence={
                        "reason": raw.reason,
                        "snippets": [raw.reason[:500]] if raw.reason else [],
                        "window_raw": raw.raw,
                    },
                    prompt_provenance=prompt_prov,
                    model_provenance=model_prov,
                    input_fingerprint=raw.input_fingerprint,
                    created_at=now,
                    updated_at=now,
                    detector_data={"title": raw.title} if raw.title else {},
                )
            )

        partial = window_failures > 0
        outcome = "success" if findings or not window_failures else "success"
        if window_failures and not findings:
            outcome = "failed" if window_failures == len(windows) else "success"

        return build_detection_envelope(
            notebook_id=project.id,
            detector_id=detector.detector_id,
            detector_version=detector.version,
            cache_identity=planned_cache_identity,
            scope_fingerprint=scope_fp,
            attempt_state="succeeded",
            outcome=outcome,
            findings=findings_to_dicts(findings),
            pages_scanned=ordered_page_ids,
            windows_scanned=len(windows),
            config_fingerprint=config_fingerprint(detector.cache_config()),
            warnings=warnings,
            partial=partial,
            attempt_id=attempt_id,
            prompt_provenance=prompt_prov,
            model_provenance=model_prov,
            generation_settings=gen,
        )
