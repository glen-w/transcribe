"""Contract tests for detection storage."""

from __future__ import annotations

from pathlib import Path

from transcribe.detection.envelope import build_detection_envelope
from transcribe.detection.storage import DetectionStorage
from transcribe.persistence.locks import mutation_lock
from transcribe.services.project import open_project_paths


def _envelope(**kwargs):
    base = dict(
        notebook_id="nb001",
        detector_id="poetry",
        detector_version="1",
        cache_identity="abc123",
        scope_fingerprint="scope1",
        attempt_state="succeeded",
        outcome="success",
        findings=[],
        pages_scanned=["p1"],
        windows_scanned=1,
        config_fingerprint="cfg1",
        attempt_id="att001",
    )
    base.update(kwargs)
    return build_detection_envelope(**base)


def test_publish_if_current_stale(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    storage = DetectionStorage(paths)
    env = _envelope(cache_identity="planned")
    with mutation_lock(paths.mutation_lock):
        storage.write_attempt("poetry", env)
        published = storage.publish_if_current(
            detector_id="poetry",
            envelope=env,
            expected_cache_identity="planned",
            current_cache_identity="different",
        )
    assert published is False
    attempt = storage.read_attempt("poetry", "att001")
    assert attempt is not None
    assert attempt.get("stale_at_publish") is True
    assert storage.read_published("poetry") is None


def test_publish_if_current_success(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    storage = DetectionStorage(paths)
    env = _envelope(cache_identity="same")
    with mutation_lock(paths.mutation_lock):
        storage.write_attempt("poetry", env)
        published = storage.publish_if_current(
            detector_id="poetry",
            envelope=env,
            expected_cache_identity="same",
            current_cache_identity="same",
        )
    assert published is True
    pub = storage.read_published("poetry")
    assert pub is not None
    assert pub.get("published") is True


def test_reconcile_interrupted(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    storage = DetectionStorage(paths)
    running = _envelope(attempt_state="running", outcome="success")
    storage.write_attempt("poetry", running)
    changed = storage.reconcile_interrupted()
    assert len(changed) == 1
    attempt = storage.read_attempt("poetry", "att001")
    assert attempt is not None
    assert attempt.get("attempt_state") == "interrupted"
