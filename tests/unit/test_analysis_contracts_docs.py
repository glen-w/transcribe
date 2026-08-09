"""Offline smoke: core analysis contracts landed and indexed (docs-only plan)."""

from __future__ import annotations

from pathlib import Path

from transcribe.persistence.schema import SUPPORTED


DOCS = Path(__file__).resolve().parents[2] / "docs"
CONTRACTS = DOCS / "contracts"


def test_analysis_contract_files_exist():
    required = [
        CONTRACTS / "analysis-document.md",
        CONTRACTS / "analysis-result.md",
        CONTRACTS / "analysis-run-storage.md",
        CONTRACTS / "notebook-eligibility.md",
        CONTRACTS / "project-on-disk.md",
        DOCS / "dev" / "analysis_port_pins.md",
        DOCS / "analysis_wave1_plan.md",
        DOCS / "analysis_wave1_hardening_plan.md",
    ]
    missing = [str(p.relative_to(DOCS.parent)) for p in required if not p.is_file()]
    assert not missing, f"missing contract/plan docs: {missing}"


def test_contract_index_lists_analysis_formats():
    index = (DOCS / "CONTRACT_INDEX.md").read_text(encoding="utf-8")
    for needle in (
        "analysis-document.md",
        "analysis-result.md",
        "analysis-run-storage.md",
        "notebook-eligibility.md",
        "transcribe.analysis-document",
        "transcribe.analysis-result",
        "notebook_eligibility_v1",
    ):
        assert needle in index, f"CONTRACT_INDEX missing {needle!r}"


def test_project_on_disk_optional_analysis_and_rejects_inplace_layout():
    text = (CONTRACTS / "project-on-disk.md").read_text(encoding="utf-8")
    assert "analysis/" in text
    assert "optional until the first analysis artifact" in text
    assert "project-layout migration" in text
    assert "Do **not** require user JPEGs" in text or "Do **not** operate in-place" in text
    assert ".transcribe/" in text


def test_analysis_document_defines_normative_fingerprint():
    text = (CONTRACTS / "analysis-document.md").read_text(encoding="utf-8")
    assert "content_fingerprint_version" in text
    assert "sha256" in text.lower() or "SHA-256" in text
    assert '{"kind": "page"' in text or '"kind": "page"' in text
    assert "half-open" in text


def test_analysis_result_separates_attempt_and_outcome():
    text = (CONTRACTS / "analysis-result.md").read_text(encoding="utf-8")
    assert "attempt_state" in text
    assert "skipped_not_applicable" in text
    assert "unavailable_dependency" in text
    assert "insufficient_data" in text
    assert "must never" in text.lower() or "must never" in text


def test_run_storage_binds_project_id_and_owns_dependency_table():
    text = (CONTRACTS / "analysis-run-storage.md").read_text(encoding="utf-8")
    assert "project_id" in text
    assert "(project_id, module_id, cache_identity)" in text
    assert "entity_sentiment" in text
    assert "affect_tension" in text
    assert "does not redefine" in text.lower() or "Reference only" in text or "reference only" in text


def test_analysis_formats_registered_in_supported():
    assert SUPPORTED.get("transcribe.analysis-document") == 1
    assert SUPPORTED.get("transcribe.analysis-result") == 1


def test_analysis_result_wordclouds_zero_token_contract():
    text = (CONTRACTS / "analysis-result.md").read_text(encoding="utf-8")
    assert "wordclouds_tokens_v1" in text
    assert "wordclouds_payload_v1" in text
    assert "zero eligible tokens" in text
    assert "insufficient_input" not in text


def test_pin_registry_includes_wordclouds():
    text = (DOCS / "dev" / "analysis_port_pins.md").read_text(encoding="utf-8")
    assert "`wordclouds`" in text
    assert "wordclouds_stopwords_v1" in text
