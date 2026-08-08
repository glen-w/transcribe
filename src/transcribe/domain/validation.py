"""Strict domain validation at the persistence boundary."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from transcribe.domain.fingerprint import sha256_bytes
from transcribe.domain.models import (
    ATTEMPT_STATUSES,
    PageResult,
    Project,
)
from transcribe.errors import ValidationError
from transcribe.persistence.schema import SUPPORTED

if TYPE_CHECKING:
    from transcribe.paths import ProjectPaths

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_nonempty_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty string")
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_nonempty_str(value, field)
    if not _SHA256_RE.match(text):
        raise ValidationError(f"{field} must be a lowercase hex SHA-256 digest")
    return text


def _require_positive_int(value: object, field: str, *, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValidationError(f"{field} must be an integer >= {minimum}")
    return value


def validate_settings(settings: object) -> None:
    from transcribe.domain.models import OCRSettings

    if not isinstance(settings, OCRSettings):
        raise ValidationError("settings must be OCRSettings")
    if settings.max_workers not in (1, 2):
        raise ValidationError("settings.max_workers must be 1 or 2")
    if settings.preprocess_profile not in ("none", "gentle_contrast"):
        raise ValidationError(
            f"unsupported preprocess_profile: {settings.preprocess_profile!r}"
        )
    if not isinstance(settings.base_url, str) or not settings.base_url.strip():
        raise ValidationError("settings.base_url must be a non-empty string")
    parsed = urlparse(settings.base_url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValidationError(
            "settings.base_url must be an http(s) root URL, e.g. http://localhost:11434"
        )
    path = (parsed.path or "").rstrip("/")
    if path:
        raise ValidationError(
            "settings.base_url must be the server root without a path"
        )
    temp = settings.generation_options.temperature
    if not isinstance(temp, (int, float)) or isinstance(temp, bool):
        raise ValidationError("generation_options.temperature must be a number")
    if temp != temp or temp < 0.0 or temp > 2.0:  # noqa: PLR0124 — NaN check
        raise ValidationError("generation_options.temperature out of range")


def validate_project(
    project: Project,
    *,
    paths: ProjectPaths | None = None,
    deep: bool = False,
) -> None:
    """Validate structural invariants. When paths is set, check containment/existence."""
    if project.format != "transcribe.project":
        raise ValidationError(f"unexpected project format: {project.format!r}")
    expected_version = SUPPORTED.get("transcribe.project")
    if project.schema_version != expected_version:
        raise ValidationError(
            f"unsupported project schema_version {project.schema_version}; "
            f"supported={expected_version}"
        )
    _require_nonempty_str(project.id, "id")
    _require_nonempty_str(project.created_at, "created_at")
    _require_nonempty_str(project.updated_at, "updated_at")
    validate_settings(project.settings)

    source_ids: set[str] = set()
    for source in project.sources:
        sid = _require_nonempty_str(source.source_id, "source.source_id")
        if sid in source_ids:
            raise ValidationError(f"duplicate source_id: {sid}")
        source_ids.add(sid)
        _require_nonempty_str(source.original_filename, "source.original_filename")
        _require_nonempty_str(source.stored_relpath, "source.stored_relpath")
        _require_nonempty_str(source.media_type, "source.media_type")
        _require_sha256(source.sha256, "source.sha256")
        _require_positive_int(source.page_count, "source.page_count", minimum=0)
        _require_positive_int(source.render_dpi, "source.render_dpi", minimum=1)
        if source.render_dpi < 72 or source.render_dpi > 600:
            raise ValidationError("source.render_dpi must be between 72 and 600")

    render_ids: set[str] = set()
    for rid, render in project.renders.items():
        if rid != render.render_id:
            raise ValidationError(
                f"renders map key {rid!r} != render_id {render.render_id!r}"
            )
        if rid in render_ids:
            raise ValidationError(f"duplicate render_id: {rid}")
        render_ids.add(rid)
        _require_sha256(render.source_sha256, "render.source_sha256")
        _require_sha256(render.rendered_image_sha256, "render.rendered_image_sha256")
        _require_positive_int(render.width, "render.width")
        _require_positive_int(render.height, "render.height")
        _require_positive_int(render.render_dpi, "render.render_dpi")
        _require_nonempty_str(render.image_relpath, "render.image_relpath")
        _require_nonempty_str(render.renderer, "render.renderer")

    page_ids: set[str] = set()
    pages_per_source: dict[str, int] = {}
    for page in project.pages:
        pid = _require_nonempty_str(page.page_id, "page.page_id")
        if pid in page_ids:
            raise ValidationError(f"duplicate page_id: {pid}")
        page_ids.add(pid)
        if page.source_id not in source_ids:
            raise ValidationError(
                f"page {pid} references missing source {page.source_id}"
            )
        if page.active_render_id not in project.renders:
            raise ValidationError(
                f"page {pid} missing render {page.active_render_id}"
            )
        if page.page_index < 0:
            raise ValidationError(f"page {pid} has negative page_index")
        _require_positive_int(page.width, "page.width")
        _require_positive_int(page.height, "page.height")
        pages_per_source[page.source_id] = pages_per_source.get(page.source_id, 0) + 1

    for source in project.sources:
        counted = pages_per_source.get(source.source_id, 0)
        if counted != source.page_count:
            raise ValidationError(
                f"source {source.source_id} page_count={source.page_count} "
                f"but {counted} page(s) reference it"
            )

    if project.cover_page_id is not None and project.cover_page_id not in page_ids:
        raise ValidationError(f"cover_page_id not in pages: {project.cover_page_id}")

    if paths is not None:
        for source in project.sources:
            abs_path = paths.resolve_contained(source.stored_relpath)
            if not abs_path.is_file():
                raise ValidationError(f"missing source file: {source.stored_relpath}")
            if deep:
                digest = sha256_bytes(abs_path.read_bytes())
                if digest != source.sha256:
                    raise ValidationError(
                        f"source sha256 mismatch for {source.source_id}"
                    )
        for render in project.renders.values():
            abs_path = paths.resolve_contained(render.image_relpath)
            if not abs_path.is_file():
                raise ValidationError(f"missing render file: {render.image_relpath}")
            if deep:
                digest = sha256_bytes(abs_path.read_bytes())
                if digest != render.rendered_image_sha256:
                    raise ValidationError(
                        f"render sha256 mismatch for {render.render_id}"
                    )


def validate_page_result(result: PageResult, *, expected_page_id: str | None = None) -> None:
    if result.format != "transcribe.page-result":
        raise ValidationError(f"unexpected page-result format: {result.format!r}")
    expected_version = SUPPORTED.get("transcribe.page-result")
    if result.schema_version != expected_version:
        raise ValidationError(
            f"unsupported page-result schema_version {result.schema_version}; "
            f"supported={expected_version}"
        )
    page_id = _require_nonempty_str(result.page_id, "page_id")
    if expected_page_id is not None and page_id != expected_page_id:
        raise ValidationError(
            f"page-result page_id {page_id!r} != expected {expected_page_id!r}"
        )
    attempt_ids: set[str] = set()
    for attempt in result.attempts:
        aid = _require_nonempty_str(attempt.attempt_id, "attempt.attempt_id")
        if aid in attempt_ids:
            raise ValidationError(f"duplicate attempt_id: {aid}")
        attempt_ids.add(aid)
        if attempt.status not in ATTEMPT_STATUSES:
            raise ValidationError(f"illegal attempt status: {attempt.status!r}")
        _require_nonempty_str(attempt.started_at, "attempt.started_at")
    if result.active_attempt_id is not None:
        if result.active_attempt_id not in attempt_ids:
            raise ValidationError(
                f"active_attempt_id {result.active_attempt_id!r} not in attempts"
            )


def collect_unexplained_files(paths: ProjectPaths, project: Project) -> list[str]:
    """Return durable relative paths under sources/pages/results not explained by project."""
    explained: set[str] = set()
    for source in project.sources:
        explained.add(source.stored_relpath)
    for render in project.renders.values():
        explained.add(render.image_relpath)
    for page in project.pages:
        explained.add(paths.relativize(paths.result_path(page.page_id)))

    unexpected: list[str] = []
    for base in (paths.sources_dir, paths.pages_dir, paths.results_dir):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            try:
                rel = paths.relativize(path)
            except ValueError:
                continue
            if rel not in explained:
                unexpected.append(rel)
    return sorted(unexpected)
