"""Page and window input models with fingerprints."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from transcribe.domain.fingerprint import canonical_json_bytes
from transcribe.domain.models import PageIndex, Project, RenderProvenance
from transcribe.paths import ProjectPaths
from transcribe.services.project import ProjectService


@dataclass(frozen=True)
class PageInput:
    page_id: str
    page_order_index: int
    effective_text: str
    active_render_id: str
    rendered_image_sha256: str
    effective_text_sha256: str

    def fingerprint_dict(self) -> dict:
        return {
            "page_id": self.page_id,
            "page_order_index": self.page_order_index,
            "effective_text_sha256": self.effective_text_sha256,
            "active_render_id": self.active_render_id,
            "rendered_image_sha256": self.rendered_image_sha256,
        }


@dataclass(frozen=True)
class WindowInput:
    window_id: str
    page_ids: tuple[str, ...]
    pages: tuple[PageInput, ...]
    combined_text: str
    page_labels: str

    def input_fingerprint(self) -> str:
        payload = {
            "page_ids": list(self.page_ids),
            "pages": [p.fingerprint_dict() for p in self.pages],
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_page_input(
    *,
    page: PageIndex,
    page_order_index: int,
    project: Project,
    project_service: ProjectService,
    paths: ProjectPaths,
) -> PageInput | None:
    result = project_service.load_page_result(page.page_id)
    text = result.effective_text() if result else None
    if text is None or not text.strip():
        return None
    render: RenderProvenance | None = project.renders.get(page.active_render_id)
    render_sha = render.rendered_image_sha256 if render else ""
    return PageInput(
        page_id=page.page_id,
        page_order_index=page_order_index,
        effective_text=text,
        active_render_id=page.active_render_id,
        rendered_image_sha256=render_sha,
        effective_text_sha256=_text_sha256(text),
    )


def load_render_bytes(
    project: Project,
    paths: ProjectPaths,
    page: PageIndex,
) -> bytes | None:
    render = project.renders.get(page.active_render_id)
    if render is None:
        return None
    try:
        image_path = paths.resolve_contained(render.image_relpath)
        return image_path.read_bytes()
    except (OSError, ValueError):
        return None


def scope_fingerprint(page_inputs: list[PageInput]) -> str:
    payload = {
        "pages": [p.fingerprint_dict() for p in sorted(page_inputs, key=lambda x: x.page_order_index)],
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
