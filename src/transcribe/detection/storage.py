"""Project-local detection attempt/publish storage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from transcribe.detection.envelope import CACHEABLE_DETECTION_OUTCOMES
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import job_lock_held, mutation_lock
from transcribe.persistence.schema import SchemaError, require_format


class DetectionStorage:
    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    def detector_dir(self, detector_id: str) -> Path:
        return self.paths.detection_dir / detector_id

    def attempts_dir(self, detector_id: str) -> Path:
        return self.detector_dir(detector_id) / "attempts"

    def attempt_path(self, detector_id: str, attempt_id: str) -> Path:
        return self.attempts_dir(detector_id) / f"{attempt_id}.json"

    def published_path(self, detector_id: str) -> Path:
        return self.detector_dir(detector_id) / "published.json"

    def write_attempt(self, detector_id: str, envelope: dict[str, Any]) -> Path:
        attempt_id = envelope.get("attempt_id")
        if not attempt_id:
            raise ValueError("attempt envelope requires attempt_id")
        path = self.attempt_path(detector_id, str(attempt_id))
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = read_json(path)
            old_state = existing.get("attempt_state")
            new_state = envelope.get("attempt_state")
            if old_state not in (None, "running") and not (
                old_state == "succeeded" and new_state == "succeeded" and "published" in envelope
            ):
                raise ValueError(f"attempt already terminal: {attempt_id}")
        write_json_atomic(path, envelope)
        return path

    def read_attempt(self, detector_id: str, attempt_id: str) -> dict[str, Any] | None:
        path = self.attempt_path(detector_id, attempt_id)
        if not path.exists():
            return None
        return read_json(path)

    def read_published(self, detector_id: str) -> dict[str, Any] | None:
        path = self.published_path(detector_id)
        if not path.exists():
            return None
        try:
            return require_format(read_json(path), "transcribe.detection-result")
        except (SchemaError, OSError, ValueError, TypeError):
            return None

    def publish_if_current(
        self,
        *,
        detector_id: str,
        envelope: dict[str, Any],
        expected_cache_identity: str,
        current_cache_identity: str,
    ) -> bool:
        if envelope.get("attempt_state") != "succeeded":
            return False
        if envelope.get("outcome") not in CACHEABLE_DETECTION_OUTCOMES:
            return False
        if expected_cache_identity != current_cache_identity:
            envelope = dict(envelope)
            envelope["published"] = False
            envelope["stale_at_publish"] = True
            self.write_attempt(detector_id, envelope)
            return False
        to_write = dict(envelope)
        to_write["published"] = True
        path = self.published_path(detector_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, to_write)
        attempt_id = envelope.get("attempt_id")
        if attempt_id:
            ap = self.attempt_path(detector_id, str(attempt_id))
            if ap.exists():
                write_json_atomic(ap, to_write)
        return True

    def validate_cache_hit(
        self,
        *,
        detector_id: str,
        expected_cache_identity: str,
        expected_detector_version: str,
    ) -> dict[str, Any] | None:
        published = self.read_published(detector_id)
        if published is None:
            return None
        if published.get("cache_identity") != expected_cache_identity:
            return None
        if published.get("detector_version") != expected_detector_version:
            return None
        if published.get("outcome") not in CACHEABLE_DETECTION_OUTCOMES:
            return None
        return published

    def reconcile_interrupted(self) -> list[str]:
        changed: list[str] = []
        root = self.paths.detection_dir
        if not root.exists():
            return changed
        if job_lock_held(self.paths.job_lock):
            return changed
        with mutation_lock(self.paths.mutation_lock):
            for detector_dir in sorted(root.iterdir()):
                if not detector_dir.is_dir():
                    continue
                attempts = detector_dir / "attempts"
                if not attempts.exists():
                    continue
                for path in sorted(attempts.glob("*.json")):
                    try:
                        payload = read_json(path)
                    except (OSError, ValueError, TypeError):
                        continue
                    if payload.get("attempt_state") != "running":
                        continue
                    payload = dict(payload)
                    payload["attempt_state"] = "interrupted"
                    payload["outcome"] = payload.get("outcome") or "failed"
                    payload["capability"] = "failed"
                    payload["published"] = False
                    write_json_atomic(path, payload)
                    changed.append(str(path))
        return changed

    def latest_attempt(self, detector_id: str) -> dict[str, Any] | None:
        """Most recently written attempt for a detector (by mtime), or None."""
        attempts = self.attempts_dir(detector_id)
        if not attempts.exists():
            return None
        paths = sorted(
            attempts.glob("*.json"),
            key=lambda p: p.stat().st_mtime_ns,
            reverse=True,
        )
        for path in paths:
            try:
                return read_json(path)
            except (OSError, ValueError, TypeError):
                continue
        return None

    def update_finding_review(
        self,
        detector_id: str,
        finding_id: str,
        review_status: str,
    ) -> bool:
        published = self.read_published(detector_id)
        if published is None:
            return False
        findings = published.get("findings") or []
        updated = False
        new_findings = []
        for row in findings:
            if row.get("finding_id") == finding_id:
                row = dict(row)
                row["review_status"] = review_status
                from transcribe.detection.findings import utc_now_iso

                row["updated_at"] = utc_now_iso()
                updated = True
            new_findings.append(row)
        if not updated:
            return False
        published = dict(published)
        published["findings"] = new_findings
        write_json_atomic(self.published_path(detector_id), published)
        return True
