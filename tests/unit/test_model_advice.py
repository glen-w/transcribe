from transcribe.services.model_advice import (
    advise_model,
    is_general_vlm_name,
    is_ocr_oriented_name,
)


def test_llava_is_general_vlm():
    assert is_general_vlm_name("llava:7b")
    advice = advise_model("llava:7b", role="vision")
    assert advice.kind == "general_vlm"
    assert any("hang" in w.lower() or "time out" in w.lower() for w in advice.warnings)


def test_glm_ocr_is_ocr_oriented():
    assert is_ocr_oriented_name("glm-ocr:latest")
    advice = advise_model("glm-ocr:latest", role="vision")
    assert advice.kind == "ocr_oriented"


def test_deepseek_ocr_is_ocr_oriented():
    assert is_ocr_oriented_name("deepseek-ocr:latest")
    advice = advise_model("deepseek-ocr:latest", role="vision")
    assert advice.kind == "ocr_oriented"
    assert any("free ocr" in w.lower() or "empty" in w.lower() for w in advice.warnings)


def test_text_role_mentions_cleanup_cost():
    advice = advise_model("llama3.1:8b", role="text")
    assert advice.kind == "text"
    assert any("cleanup" in w.lower() for w in advice.warnings)
