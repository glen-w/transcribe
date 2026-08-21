"""Unit tests for lexical first-person and swear-word counters."""

from __future__ import annotations

from transcribe.detection.lexical import (
    count_first_person,
    count_swear_words,
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
