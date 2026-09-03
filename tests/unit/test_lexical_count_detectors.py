"""Unit tests for lexical first-person and swear-word counters."""

from __future__ import annotations

from transcribe.detection.lexical import (
    count_first_person,
    count_swear_words,
    lexical_page_count_rows,
    run_lexical_matcher,
    validate_swear_lexicon_file,
)
from transcribe.detection.registry import get_builtin_detector


def test_first_person_counts_i_case_insensitive():
    result = count_first_person("I think i know what I mean.")
    assert result.count == 3
    assert set(result.samples) <= {"I", "i"}


def test_first_person_skips_inside_words():
    result = count_first_person("This is big idea without pronouns.")
    assert result.count == 0


def test_first_person_counts_contraction_prefix():
    # Word-boundary match: I in I'm / I've
    result = count_first_person("I'm sure I've said it.")
    assert result.count == 2


def test_names_detector_is_ner_people_engine():
    names = get_builtin_detector("names")
    assert names is not None
    assert names.engine.value == "ner_people"
    assert names.extra_config["source_module"] == "ner"
    assert names.extra_config["entity_label"] == "PERSON"


def test_swear_words_counts_and_categorizes():
    result = count_swear_words("What the hell? This is fucking bullshit.")
    assert result.count == 3
    assert result.category_counts.get("mild", 0) >= 1
    assert result.category_counts.get("strong", 0) >= 1
    assert "hell" in {s.casefold() for s in result.samples}


def test_swear_words_word_boundaries():
    result = count_swear_words("The class assignment was classic.")
    assert result.count == 0


def test_run_lexical_matcher_dispatch():
    assert run_lexical_matcher("first_person_i", "I am").count == 1
    assert run_lexical_matcher("swear_words", "damn it").count == 1


def test_swear_lexicon_loads():
    meta = validate_swear_lexicon_file()
    assert meta["phrase_count"] >= 20
    assert meta["digest"]


def test_builtin_lexical_detectors_registered():
    first = get_builtin_detector("first_person")
    swear = get_builtin_detector("swear_words")
    assert first is not None
    assert swear is not None
    assert first.engine.value == "lexical_count"
    assert swear.engine.value == "lexical_count"
    assert first.extra_config["lexical_matcher"] == "first_person_i"
    assert swear.extra_config["lexicon_id"] == "swear_words_en_v1"


def test_lexical_page_count_rows_prefers_published_series():
    rows = lexical_page_count_rows(
        page_order={"a": 0, "b": 1, "c": 2},
        page_counts=[
            {"page_id": "b", "count": 0},
            {"page_id": "a", "count": 4},
        ],
        findings=[{"start_page_id": "a", "detector_data": {"count": 99}}],
    )
    assert rows == [
        {"order": 1, "page_id": "a", "count": 4},
        {"order": 2, "page_id": "b", "count": 0},
    ]


def test_lexical_page_count_rows_falls_back_to_findings_and_scanned():
    rows = lexical_page_count_rows(
        page_order={"p0": 0, "p1": 1},
        findings=[{"start_page_id": "p0", "detector_data": {"count": 3}}],
        pages_scanned=["p0", "p1"],
    )
    assert rows == [
        {"order": 1, "page_id": "p0", "count": 3},
        {"order": 2, "page_id": "p1", "count": 0},
    ]
