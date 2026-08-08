"""Project-local analysis attempt/publish storage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from transcribe.analysis.envelope import CACHEABLE_OUTCOMES
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import job_lock_held, mutation_lock
from transcribe.persistence.schema import SchemaError, require_format


class AnalysisStorage:
    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    def module_dir(self, module_id: str) -> Path:
        return self.paths.analysis_dir / module_id

    def attempts_dir(self, module_id: str) -> Path:
        return self.module_dir(module_id) / "attempts"

    def attempt_path(self, module_id: str, attempt_id: str) -> Path:
        return self.attempts_dir(module_id) / f"{attempt_id}.json"

    def published_path(self, module_id: str) -> Path:
        return self.module_dir(module_id) / "published.json"

    def write_attempt(self, module_id: str, envelope: dict[str, Any]) -> Path:
        attempt_id = envelope.get("attempt_id")
        if not attempt_id:
            raise ValueError("attempt envelope requires attempt_id")
        path = self.attempt_path(module_id, str(attempt_id))
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = read_json(path)
            old_state = existing.get("attempt_state")
            new_state = envelope.get("attempt_state")
            # Allow running → terminal, and published-flag updates on succeeded attempts.
            if old_state not in (None, "running") and not (
                old_state == "succeeded"
                and new_state == "succeeded"
                and "published" in envelope
            ):
                raise ValueError(f"attempt already terminal: {attempt_id}")
        write_json_atomic(path, envelope)
        return path

    def read_attempt(self, module_id: str, attempt_id: str) -> dict[str, Any] | None:
        path = self.attempt_path(module_id, attempt_id)
        if not path.exists():
            return None
        return read_json(path)

    def read_published(self, module_id: str) -> dict[str, Any] | None:
        path = self.published_path(module_id)
        if not path.exists():
            return None
        try:
            return require_format(read_json(path), "transcribe.analysis-result")
        except (SchemaError, OSError, ValueError, TypeError):
            return None

    def publish_if_current(
        self,
        *,
        module_id: str,
        envelope: dict[str, Any],
        expected_cache_identity: str,
        current_cache_identity: str,
    ) -> bool:
        """Atomically publish under caller-held mutation_lock. Returns True if published."""
        if envelope.get("attempt_state") != "succeeded":
            return False
        if envelope.get("outcome") not in CACHEABLE_OUTCOMES:
            return False
        if expected_cache_identity != current_cache_identity:
            # Stale input: keep attempt, do not publish.
            envelope = dict(envelope)
            envelope["published"] = False
            envelope["stale_at_publish"] = True
            self.write_attempt(module_id, envelope)
            return False
        to_write = dict(envelope)
        to_write["published"] = True
        path = self.published_path(module_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, to_write)
        # Mirror published flag onto attempt
        attempt_id = envelope.get("attempt_id")
        if attempt_id:
            ap = self.attempt_path(module_id, str(attempt_id))
            if ap.exists():
                write_json_atomic(ap, to_write)
        return True

    def validate_cache_hit(
        self,
        *,
        module_id: str,
        expected_cache_identity: str,
        expected_module_version: str,
    ) -> dict[str, Any] | None:
        published = self.read_published(module_id)
        if published is None:
            return None
        if published.get("cache_identity") != expected_cache_identity:
            return None
        if published.get("module_version") != expected_module_version:
            return None
        if published.get("outcome") not in CACHEABLE_OUTCOMES:
            return None
        attempt_id = published.get("attempt_id")
        if attempt_id:
            attempt = self.read_attempt(module_id, str(attempt_id))
            if attempt is None:
                return None
        return published

    def reconcile_interrupted(self) -> list[str]:
        """Convert orphaned running attempts to interrupted. Never touches published."""
        changed: list[str] = []
        root = self.paths.analysis_dir
        if not root.exists():
            return changed
        # Only reconcile when job lock is free (OCR not mid-flight is fine;
        # analysis uses mutation_lock for writes — job lock free is sufficient signal).
        if job_lock_held(self.paths.job_lock):
            return changed
        with mutation_lock(self.paths.mutation_lock):
            for module_dir in sorted(root.iterdir()):
                if not module_dir.is_dir():
                    continue
                attempts = module_dir / "attempts"
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
