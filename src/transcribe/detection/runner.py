"""Run detection with lock-free compute and atomic publish."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.cache_identity import config_fingerprint
from transcribe.analysis.llm_runtime import TextLLMContext, bind_text_llm_context
from transcribe.config.facade import bind_operation_config, snapshot_for_operation
from transcribe.config.knobs import llm_generation_options
from transcribe.detection.aggregate import (
    merge_adjacent_spans,
    raw_from_window_response,
)
from transcribe.detection.cache_identity import (
    build_cache_identity_object,
    cache_identity_hex,
)
from transcribe.detection.candidates import select_candidates
from transcribe.detection.custom import load_custom_detectors
from transcribe.detection.definition import DetectorDefinition
from transcribe.detection.envelope import build_detection_envelope
from transcribe.detection.findings import (
    DetectionFinding,
    carry_forward_reviews,
    findings_to_dicts,
    utc_now_iso,
)
from transcribe.detection.inputs import load_render_bytes, scope_fingerprint
from transcribe.detection.registry import resolve_detector
from transcribe.detection.routing import resolve_model_route
from transcribe.detection.scope import plan_windows
from transcribe.detection.storage import DetectionStorage
from transcribe.persistence.locks import mutation_lock
from transcribe.prompt_engine.definition import InputMode
from transcribe.prompt_engine.execute import execute_prompt
from transcribe.prompt_engine.hub import resolve_for_input_mode, resolve_prompt
from transcribe.providers.vision_llm import VisionLLMContext, bind_vision_llm_context
from transcribe.ports import Clock, IdGenerator
from transcribe.services.project import ProjectService


def _detector_data_from_raw(parsed: dict[str, Any], finding_type: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if finding_type == "poetry" and parsed.get("title"):
        data["title"] = parsed["title"]
    if finding_type == "todo_lists":
        if parsed.get("items"):
            data["items"] = parsed["items"][:40]
        if parsed.get("list_style"):
            data["list_style"] = parsed["list_style"]
    if finding_type == "lists":
        for key in ("list_kind", "item_count_estimate", "sample_items"):
            if key in parsed:
                data[key] = parsed[key]
    if finding_type == "quotations":
        for key in ("quote_kind", "attribution", "excerpt"):
            if key in parsed and parsed[key] is not None:
                data[key] = parsed[key]
    if finding_type == "beer_labels":
        for key in (
            "label_kind",
            "beer_name",
            "brewery_or_brand",
            "style_hint",
            "sample_text",
        ):
            if key in parsed and parsed[key] is not None:
                data[key] = parsed[key]
    if parsed.get("title") and "title" not in data:
        data["title"] = parsed["title"]
    return data


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
        # Vision/text model authority is project OCR settings; workspace ocr.* only
        # supplies defaults for new projects (no vision model_name field).
        project = self.project_service.load(reconcile=False)
        base_url = (project.settings.base_url or cfg.ocr.base_url or "").strip()
        text_name = (
            (project.settings.text_model_name or "").strip()
            or (cfg.ocr.text_model_name or "").strip()
            or (cfg.llm.text_model_preference or "").strip()
        )
        vision_name = (project.settings.model_name or "").strip()
        text = bind_text_llm_context(
            text_model_name=text_name,
            base_url=base_url,
        )
        vision = bind_vision_llm_context(
            model_name=vision_name,
            base_url=base_url,
        )
        return text, vision

    def planned_cache_identity(
        self,
        detector: DetectorDefinition,
        *,
        page_ids: list[str] | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        # Mid-run loads must not reconcile: that would mark this attempt interrupted.
        project = self.project_service.load(reconcile=False)
        page_inputs, _ = select_candidates(
            detector,
            project,
            self.project_service,
            self.paths,
            page_ids=page_ids,
        )
        prompt = resolve_prompt(
            detector.prompt_ref.prompt_id,
            version=detector.prompt_ref.version,
            project_prompts_dir=self.paths.prompts_dir,
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
        # Re-resolve prompt for vision twin when route is vision
        if route is not None and route.input_mode == InputMode.VISION:
            vision_prompt = resolve_for_input_mode(
                detector.prompt_ref.prompt_id,
                want_vision=True,
                project_prompts_dir=self.paths.prompts_dir,
            )
            if vision_prompt is not None:
                prompt = vision_prompt
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
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        custom = load_custom_detectors()
        detector = resolve_detector(detector_id, custom_detectors=custom)
        if detector is None:
            raise ValueError(f"unknown detector: {detector_id}")

        planned_id, scope_fp, _ = self.planned_cache_identity(detector, page_ids=page_ids)
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
                progress_callback=progress_callback,
            )

        # Snapshot custom detector definition into project on first successful path
        if detector_id.startswith("custom/"):
            self._snapshot_custom_detector(detector)

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

    def _snapshot_custom_detector(self, detector: DetectorDefinition) -> None:
        from transcribe.persistence.atomic import write_json_atomic

        dest_dir = self.paths.detection_dir / "custom"
        dest_dir.mkdir(parents=True, exist_ok=True)
        slug = detector.detector_id.split("/", 1)[-1]
        path = dest_dir / f"{slug}.json"
        payload = {
            "format": "transcribe.custom-detector",
            "schema_version": 1,
            "detector_id": detector.detector_id,
            "version": detector.version,
            "title": detector.title,
            "description": detector.description,
            "prompt_ref": detector.prompt_ref.as_dict(),
            "scope": detector.scope.value,
            "input_mode": detector.input_mode.value,
            "window_size": detector.window_size,
            "window_overlap": detector.window_overlap,
            "confidence_threshold": detector.confidence_threshold,
            "finding_type": detector.finding_type,
            "extra_config": detector.extra_config,
        }
        write_json_atomic(path, payload)

    def _execute_run(
        self,
        detector: DetectorDefinition,
        *,
        attempt_id: str,
        planned_cache_identity: str,
        page_ids: list[str] | None,
        cancel_check: Any | None,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        # Active attempt is on disk as running; reconcile would mark it interrupted.
        project = self.project_service.load(reconcile=False)
        page_inputs, warnings = select_candidates(
            detector,
            project,
            self.project_service,
            self.paths,
            page_ids=page_ids,
        )
        scope_fp = scope_fingerprint(page_inputs)
        prompt = resolve_prompt(
            detector.prompt_ref.prompt_id,
            version=detector.prompt_ref.version,
            project_prompts_dir=self.paths.prompts_dir,
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

        if route.input_mode == InputMode.VISION:
            vision_prompt = resolve_for_input_mode(
                detector.prompt_ref.prompt_id,
                want_vision=True,
                project_prompts_dir=self.paths.prompts_dir,
            )
            if vision_prompt is not None:
                prompt = vision_prompt

        gen = llm_generation_options(snapshot_for_operation())
        windows = plan_windows(detector, page_inputs)
        ordered_page_ids = [
            p.page_id for p in sorted(page_inputs, key=lambda x: x.page_order_index)
        ]
        raw_hits = []
        window_failures = 0

        for wi, window in enumerate(windows):
            if progress_callback:
                try:
                    progress_callback(wi + 1, len(windows))
                except Exception:  # noqa: BLE001
                    pass
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
                slots: dict[str, str] = {
                    "content": window.combined_text,
                    "page_labels": window.page_labels,
                }
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
                    vision_ctx.client
                    if route.input_mode == InputMode.VISION and vision_ctx
                    else text_ctx.client if text_ctx else None
                )
                if executor is None:
                    window_failures += 1
                    warnings.append(
                        {
                            "code": "window_failed",
                            "message": f"window {window.window_id}: no executor",
                        }
                    )
                    continue
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
        prompt_prov = {"prompt_id": prompt.prompt_id, "version": prompt.version}
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
                        "window_raw": {
                            k: v for k, v in (raw.raw or {}).items() if k != "items" or True
                        },
                    },
                    prompt_provenance=prompt_prov,
                    model_provenance=model_prov,
                    input_fingerprint=raw.input_fingerprint,
                    created_at=now,
                    updated_at=now,
                    detector_data=_detector_data_from_raw(raw.raw or {}, raw.finding_type),
                )
            )
        findings = carry_forward_reviews(
            findings, self.storage.read_published(detector.detector_id)
        )

        partial = window_failures > 0
        outcome = "success"
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
