"""Workspace tag-catalog.json persistence (Transcribe host — not part of the TX copy-boundary)."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import mutation_lock
from transcribe.persistence.schema import SchemaError, require_format
from transcribe.ports import Clock, IdGenerator, SystemClock, UuidGenerator, to_iso
from transcribe.runtime_paths import RuntimePaths, build_runtime_paths
from transcribe.tagging.kernel import (
    FORMAT,
    TagCatalog,
    TagDef,
    catalog_from_payload,
)
from transcribe.tagging.kernel import (
    ensure_slugs as kernel_ensure_slugs,
)

logger = logging.getLogger(__name__)

CATALOG_FILENAME = "tag-catalog.json"
LOCK_FILENAME = ".transcribe.tag-catalog.lock"
_MAX_DIAG_LEN = 240


def _bound_diag(message: str) -> str:
    text = " ".join(message.split())
    if len(text) <= _MAX_DIAG_LEN:
        return text
    return text[: _MAX_DIAG_LEN - 3] + "..."


def tag_catalog_path(runtime: RuntimePaths | None = None) -> Path:
    rt = runtime or build_runtime_paths()
    return rt.data_dir / "config" / CATALOG_FILENAME


def tag_catalog_lock_path(runtime: RuntimePaths | None = None) -> Path:
    rt = runtime or build_runtime_paths()
    return rt.data_dir / "config" / LOCK_FILENAME


@dataclass
class CatalogLoad:
    catalog: TagCatalog
    recovery: bool = False
    recovery_message: str = ""
    path: Path | None = None


class TagCatalogStore:
    """Load/save ``personal_corpus.tag-catalog`` with fail-closed recovery."""

    def __init__(
        self,
        runtime: RuntimePaths | None = None,
        *,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.runtime = runtime or build_runtime_paths()
        self.clock = clock or SystemClock()
        self.ids = ids or UuidGenerator()
        self.path = tag_catalog_path(self.runtime)
        self.lock_path = tag_catalog_lock_path(self.runtime)

    def now_iso(self) -> str:
        return to_iso(self.clock.now())

    def load(self) -> CatalogLoad:
        path = self.path
        if not path.exists():
            return CatalogLoad(catalog=TagCatalog(), path=path)
        try:
            payload = read_json(path)
        except (OSError, ValueError, TypeError) as exc:
            return self._recovery(f"tag catalog unreadable: {exc}", path)
        if not isinstance(payload, dict):
            return self._recovery("tag catalog is not a JSON object", path)
        try:
            require_format(payload, FORMAT)
        except SchemaError as exc:
            return self._recovery(str(exc), path)
        catalog = catalog_from_payload(payload)
        return CatalogLoad(catalog=catalog, path=path)

    def _recovery(self, message: str, path: Path) -> CatalogLoad:
        msg = _bound_diag(message)
        logger.warning("tag-catalog recovery: %s", msg)
        return CatalogLoad(
            catalog=TagCatalog(),
            recovery=True,
            recovery_message=msg,
            path=path,
        )

    def save(self, catalog: TagCatalog) -> TagCatalog:
        """Atomic replace. Refuses to overwrite a file that is in recovery."""
        loaded = self.load()
        if loaded.recovery:
            raise SchemaError(
                loaded.recovery_message or "tag catalog is in recovery; file preserved"
            )
        now = self.now_iso()
        to_write = TagCatalog(tags=list(catalog.tags), updated_at=now)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with mutation_lock(self.lock_path):
            write_json_atomic(self.path, to_write.as_dict())
        return to_write

    def ensure_slugs(
        self,
        slugs: Sequence[str],
        *,
        labels: Mapping[str, str] | None = None,
        colors: Mapping[str, str] | None = None,
    ) -> TagCatalog:
        """Create catalog rows for new slugs. No-op when recovery or empty."""
        wanted = [s for s in slugs if str(s).strip()]
        if not wanted:
            return self.load().catalog
        loaded = self.load()
        if loaded.recovery:
            return loaded.catalog
        now = self.now_iso()
        updated, _ = kernel_ensure_slugs(
            loaded.catalog,
            wanted,
            new_id=self.ids.new_id,
            now_iso=now,
            labels=labels,
            colors=colors,
        )
        if [t.tag_id for t in updated.tags] == [t.tag_id for t in loaded.catalog.tags] and [
            t.slug for t in updated.tags
        ] == [t.slug for t in loaded.catalog.tags]:
            return loaded.catalog
        try:
            return self.save(updated)
        except SchemaError:
            return loaded.catalog

    def mutate(self, catalog: TagCatalog) -> TagCatalog:
        return self.save(catalog)


def catalog_snapshot_payload(
    catalog: TagCatalog,
    slugs: Sequence[str],
) -> list[dict[str, Any]]:
    from transcribe.tagging.kernel import snapshot_for_slugs

    return snapshot_for_slugs(catalog, slugs)


def resolve_display(catalog: TagCatalog, slug: str) -> TagDef:
    from transcribe.tagging.kernel import display_tag

    return display_tag(catalog, slug)
