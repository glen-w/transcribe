from transcribe.providers.base import ModelInfo
from transcribe.services.model_advice import is_ocr_oriented_name
from transcribe.services.model_selection import (
    is_suitable_ocr_vision_model_info,
    is_unsuitable_ocr_vision_model_name,
    suitable_ocr_vision_model_names,
)
from tests.fakes import FakeVisionOCRProvider


def _info(name: str, *, caps: list[str], capability_known: bool = True) -> ModelInfo:
    return ModelInfo(
        name=name,
        digest="d",
        capabilities=caps,
        capability_known=capability_known,
    )


def test_excludes_thinking_and_text_only_from_ocr_picker() -> None:
    models = [
        _info("gemma4:26b", caps=["completion", "vision"]),
        _info("glm-ocr:latest", caps=["vision", "completion"]),
        _info("gpt-oss:20b", caps=["completion", "tools"]),
        _info("granite3.2-vision:latest", caps=["vision", "completion"]),
        _info("llama3.2-vision:11b", caps=["vision", "completion"]),
    ]
    names = suitable_ocr_vision_model_names(models)
    assert "glm-ocr:latest" in names
    assert "granite3.2-vision:latest" in names
    assert "gemma4:26b" not in names
    assert "gpt-oss:20b" not in names
    assert "llama3.2-vision:11b" not in names


def test_ocr_oriented_without_vision_capability_still_listed() -> None:
    models = [_info("deepseek-ocr:latest", caps=["completion"], capability_known=True)]
    assert is_suitable_ocr_vision_model_info(models[0])
    assert suitable_ocr_vision_model_names(models) == ["deepseek-ocr:latest"]


def test_ocr_picker_sorts_ocr_oriented_first() -> None:
    models = [
        _info("llava:7b", caps=["vision", "completion"]),
        _info("glm-ocr:latest", caps=["vision", "completion"]),
        _info("granite3.2-vision:latest", caps=["vision", "completion"]),
    ]
    assert suitable_ocr_vision_model_names(models)[0] == "glm-ocr:latest"


def test_unsuitable_ocr_vision_name_guard() -> None:
    assert is_unsuitable_ocr_vision_model_name("gemma4:26b")
    assert not is_unsuitable_ocr_vision_model_name("glm-ocr:latest")
    assert is_ocr_oriented_name("glm-ocr:latest")


def test_validate_ocr_vision_model_rejects_thinking_tag() -> None:
    from transcribe.errors import ProviderError
    from transcribe.services.model_selection import validate_ocr_vision_model

    provider = FakeVisionOCRProvider(
        models=[
            ModelInfo(
                name="gemma4:26b",
                digest="d",
                capabilities=["vision", "completion", "thinking"],
                capability_known=True,
            )
        ]
    )
    try:
        validate_ocr_vision_model(provider, "gemma4:26b")
    except ProviderError as exc:
        assert exc.code == "model_unsuitable"
    else:
        raise AssertionError("expected model_unsuitable")


def test_validate_ocr_vision_model_allows_unknown_tag_when_not_in_discovery() -> None:
    from transcribe.services.model_selection import validate_ocr_vision_model

    provider = FakeVisionOCRProvider(models=[])
    validate_ocr_vision_model(provider, "manual-override")
