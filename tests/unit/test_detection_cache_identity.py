"""Detection cache identity tests."""

from __future__ import annotations

from transcribe.detection.cache_identity import (
    build_cache_identity_object,
    cache_identity_hex,
)
from transcribe.detection.definition import (
    CandidateStrategy,
    DetectorDefinition,
    DetectorScope,
    ModelMode,
    PromptRef,
)
from transcribe.detection.inputs import PageInput


def _detector() -> DetectorDefinition:
    return DetectorDefinition(
        detector_id="poetry",
        version="1",
        title="Poetry",
        description="",
        prompt_ref=PromptRef("poetry_detect_text_v1", "1"),
        scope=DetectorScope.PAGE_WINDOW,
        input_mode=ModelMode.AUTO,
        candidate_strategy=CandidateStrategy.ALL_PAGES,
    )


def _page(page_id: str, text: str, order: int) -> PageInput:
    import hashlib

    sha = hashlib.sha256(text.encode()).hexdigest()
    return PageInput(
        page_id=page_id,
        page_order_index=order,
        effective_text=text,
        active_render_id="r1",
        rendered_image_sha256="imgsha",
        effective_text_sha256=sha,
    )


def test_edit_changes_identity():
    det = _detector()
    gen = {"temperature": 0.0}
    p1 = [_page("p1", "hello", 0)]
    p2 = [_page("p1", "hello world", 0)]
    id1 = cache_identity_hex(
        build_cache_identity_object(
            notebook_id="nb",
            detector=det,
            prompt_id="poetry_detect_text_v1",
            prompt_version="1",
            page_inputs=p1,
            model_digest="digest",
            generation_settings=gen,
        )
    )
    id2 = cache_identity_hex(
        build_cache_identity_object(
            notebook_id="nb",
            detector=det,
            prompt_id="poetry_detect_text_v1",
            prompt_version="1",
            page_inputs=p2,
            model_digest="digest",
            generation_settings=gen,
        )
    )
    assert id1 != id2


def test_detector_version_changes_identity():
    det_v1 = _detector()
    det_v2 = DetectorDefinition(
        detector_id="poetry",
        version="2",
        title="Poetry",
        description="",
        prompt_ref=PromptRef("poetry_detect_text_v1", "1"),
        scope=DetectorScope.PAGE_WINDOW,
        input_mode=ModelMode.AUTO,
    )
    pages = [_page("p1", "x", 0)]
    gen = {"temperature": 0.0}
    id1 = cache_identity_hex(
        build_cache_identity_object(
            notebook_id="nb",
            detector=det_v1,
            prompt_id="poetry_detect_text_v1",
            prompt_version="1",
            page_inputs=pages,
            model_digest="d",
            generation_settings=gen,
        )
    )
    id2 = cache_identity_hex(
        build_cache_identity_object(
            notebook_id="nb",
            detector=det_v2,
            prompt_id="poetry_detect_text_v1",
            prompt_version="1",
            page_inputs=pages,
            model_digest="d",
            generation_settings=gen,
        )
    )
    assert id1 != id2
