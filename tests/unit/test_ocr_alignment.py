"""Source-only OCR alignment: wrapping, composite-as-recommendation, re-anchor."""

from __future__ import annotations

from transcribe.services.ocr_alignment import (
    align_ocr,
    apply_region_variant,
    first_unresolved_index,
    grouped_source_variants,
    is_whitespace_only_change,
    normalize_span,
)


def test_different_line_wrapping_is_agreement() -> None:
    a = "Word counts for scans conversion for phone calls"
    b = "Word counts for\nscans conversion for\nphone calls"
    result = align_ocr({"a": a, "b": b})
    assert result.source_disagreement_count == 0
    assert result.agreement_ratio == 1.0


def test_whitespace_and_bullet_equivalence() -> None:
    a = "- foo bar\n- baz"
    b = "* foo   bar\n• baz"
    result = align_ocr({"a": a, "b": b})
    assert result.source_disagreement_count == 0
    assert result.agreement_ratio == 1.0
    assert not is_whitespace_only_change(a, a + " extra")
    assert is_whitespace_only_change("foo   bar", "foo bar")


def test_punctuation_and_word_disagreement() -> None:
    a = "Word counts for scans - conversion."
    b = "Word counts for scans - conversation"
    result = align_ocr({"a": a, "b": b})
    assert result.source_disagreement_count >= 1
    texts = []
    for region in result.regions:
        if region.kind == "source":
            texts.extend(region.variants.values())
    blob = " ".join(texts)
    assert "conversion" in blob
    assert "conversation" in blob


def test_punctuation_only_disagreement_is_not_navigable() -> None:
    """`.` vs pipes must lower agreement but not emit a Review step."""
    from transcribe.services.ocr_alignment import region_variants_non_reviewable

    result = align_ocr({"a": ".\n- Use proper punctuation and spacing.", "b": "| | | |\nhello world"})
    assert result.agreement_ratio < 1.0
    for region in result.regions:
        if region.kind != "source":
            continue
        assert not region_variants_non_reviewable(region.variants)
    junk = align_ocr({"a": ".", "b": "| | | |"})
    assert junk.source_disagreement_count == 0
    assert junk.regions == ()
    assert junk.agreement_ratio < 1.0


def test_prompt_instruction_span_is_non_reviewable() -> None:
    from transcribe.services.ocr_alignment import is_non_reviewable_span

    assert is_non_reviewable_span("Use proper punctuation and spacing.")
    assert is_non_reviewable_span("| | | |")
    assert is_non_reviewable_span(".")
    assert not is_non_reviewable_span("hello notebook page")


def test_insertion_and_omitted_text_are_subsequence_not_line_count() -> None:
    shared = "Sheets Account for end matter Word counts for scans"
    extra = "Sheets Account for end matter extra omitted sentence here Word counts for scans"
    wrapped = "Sheets Account for\nend matter Word counts for\nscans"
    wrap_result = align_ocr({"a": shared, "b": wrapped})
    assert wrap_result.omitted_span_count == 0
    omit_result = align_ocr({"a": shared, "b": extra})
    assert omit_result.source_disagreement_count >= 1
    assert omit_result.omitted_span_count >= 1


def test_composite_cannot_change_source_agreement() -> None:
    sources = {
        "phi4": "conversion for phone calls",
        "qwen": "conversation for phone calls",
        "deepseek": "conversion for phone calls",
    }
    without = align_ocr(sources)
    with_comp = align_ocr(
        sources,
        composite_candidate="conversion for phone calls",
        canonical_buffer="conversation for phone calls",
    )
    assert with_comp.agreement_ratio == without.agreement_ratio
    assert with_comp.source_disagreement_count == without.source_disagreement_count
    assert with_comp.source_disagreement_count >= 1
    decisions = [r for r in with_comp.regions if r.kind == "source"]
    assert decisions
    assert any(r.composite_matches_attempt_ids for r in decisions)
    assert not any(r.composite_departure for r in decisions if r.kind == "source")


def test_composite_departure_when_sources_agree() -> None:
    sources = {
        "a": "the cat sat on the mat",
        "b": "the cat sat on the mat",
    }
    result = align_ocr(
        sources,
        composite_candidate="the cat sat on the carpet",
    )
    assert result.source_disagreement_count == 0
    assert result.departure_count >= 1
    deps = [r for r in result.regions if r.kind == "departure" or r.composite_departure]
    assert deps
    assert any("carpet" in (r.composite_variant or "") for r in deps)


def test_editing_canonical_cannot_change_source_disagreement_count() -> None:
    sources = {
        "a": "alpha beta conversion gamma",
        "b": "alpha beta conversation gamma",
    }
    first = align_ocr(sources, canonical_buffer="alpha beta conversion gamma")
    second = align_ocr(sources, canonical_buffer="alpha beta HUMAN gamma")
    assert first.source_disagreement_count == second.source_disagreement_count
    assert first.agreement_ratio == second.agreement_ratio


def test_apply_variant_reanchors_and_continues() -> None:
    sources = {
        "a": "one conversion two foo three",
        "b": "one conversation two bar three",
    }
    aligned = align_ocr(sources, canonical_buffer=sources["a"])
    source_regions = [r for r in aligned.regions if r.kind == "source"]
    assert len(source_regions) >= 2
    first = source_regions[0]
    groups = grouped_source_variants(first)
    chosen = groups[0][1] if groups else first.variants["b"]
    patched = apply_region_variant(sources["a"], aligned, first, first.variants["b"])
    assert "conversation" in patched or chosen in patched
    resolved = {first.key}
    realigned = align_ocr(sources, canonical_buffer=patched)
    assert realigned.source_disagreement_count == aligned.source_disagreement_count
    nxt = first_unresolved_index(
        realigned.regions, resolved, after_base_i1=first.base_i1
    )
    assert realigned.regions[nxt].key != first.key or len(source_regions) == 1


def test_displayed_variants_preserve_exact_raw_substrings() -> None:
    sources = {
        "a": "counts – conversion",
        "b": "counts - conversation",
    }
    result = align_ocr(sources)
    found_dash = False
    for region in result.regions:
        if "–" in region.variants.get("a", ""):
            found_dash = True
    # En-dash must survive as the displayed alternative, not be normalised away.
    assert found_dash or any("–" in r.variants.get("a", "") for r in result.regions)
    assert normalize_span("counts – conversion") != normalize_span("counts - conversation")
