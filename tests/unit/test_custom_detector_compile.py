"""Custom detector compilation tests."""

from __future__ import annotations

from transcribe.detection.custom import CustomDetectorDefinition, compile_custom_detector
from transcribe.detection.definition import DetectorScope


def test_compile_dreams_detector():
    custom = CustomDetectorDefinition(
        name="Dreams",
        instruction='Find pages describing dreams. Ignore metaphorical "dream".',
        scope="notebook",
        adjacent_page_detection=True,
        model_mode="auto",
        confidence_threshold=0.6,
    )
    det = compile_custom_detector(custom)
    assert det is not None
    assert det.detector_id.startswith("custom/")
    assert det.scope == DetectorScope.PAGE_WINDOW
    assert det.extra_config.get("instruction")


def test_empty_instruction_rejected():
    assert compile_custom_detector({"name": "X", "instruction": ""}) is None
