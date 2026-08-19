"""DetectionService — programmatic API facade."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from transcribe.analysis.llm_runtime import TextLLMContext, set_text_llm_client
from transcribe.detection.custom import (
    CustomDetectorDefinition,
    compile_custom_detector,
    delete_custom_detector,
    list_custom_detector_payloads,
    load_custom_detectors,
    save_custom_detector,
)
from transcribe.detection.definition import DetectorDefinition
from transcribe.detection.findings import DetectionFinding
from transcribe.detection.freshness import FreshnessStatus, detector_freshness
from transcribe.detection.registry import list_all_detectors, resolve_detector
from transcribe.detection.runner import DetectionRunner
from transcribe.detection.storage import DetectionStorage
from transcribe.providers.vision_llm import VisionLLMContext
from transcribe.services.project import ProjectService, open_project_paths


@dataclass(frozen=True)
class DetectorInfo:
    detector_id: str
    version: str
    title: str
    description: str
    finding_type: str


class DetectionService:
    def __init__(
        self,
        project_service: ProjectService,
        *,
        text_ctx: TextLLMContext | None = None,
        vision_ctx: VisionLLMContext | None = None,
    ) -> None:
        self.project_service = project_service
        self.runner = DetectionRunner(
            project_service,
            text_ctx=text_ctx,
            vision_ctx=vision_ctx,
        )
        self.storage = DetectionStorage(project_service.paths)

    @classmethod
    def open(cls, project_root: Path | str, **kwargs: Any) -> DetectionService:
        paths = open_project_paths(project_root)
        return cls(ProjectService(paths), **kwargs)

    @staticmethod
    def list_detectors() -> list[DetectorInfo]:
        return [
            DetectorInfo(
                detector_id=d.detector_id,
                version=d.version,
                title=d.title,
                description=d.description,
                finding_type=d.finding_type,
            )
            for d in list_all_detectors()
        ]

    def run_detector(
        self,
        detector_id: str,
        *,
        page_ids: list[str] | None = None,
        force: bool = False,
        cancel_check: Any | None = None,
        progress_callback: Any | None = None,
        auto_tag: bool = False,
    ) -> dict[str, Any]:
        result = self.runner.run_detector(
            detector_id,
            page_ids=page_ids,
            force=force,
            cancel_check=cancel_check,
            progress_callback=progress_callback,
        )
        if auto_tag:
            tagged = self.apply_tags_from_published(detector_id)
            result = dict(result)
            result["auto_tagged_pages"] = tagged
        return result

    def finding_tag_slug(
        self,
        detector_id: str,
        *,
        finding_type: str | None = None,
    ) -> str:
        custom = load_custom_detectors()
        detector = resolve_detector(detector_id, custom_detectors=custom)
        from transcribe.tagging.kernel import normalize_slug

        slug_source = (
            (detector.finding_type if detector is not None else finding_type) or detector_id
        )
        return normalize_slug(slug_source)

    def finding_tag_label(self, detector_id: str, *, slug: str) -> str:
        custom = load_custom_detectors()
        detector = resolve_detector(detector_id, custom_detectors=custom)
        return detector.title if detector is not None else slug

    def span_page_ids(self, finding: DetectionFinding) -> list[str]:
        return self._page_ids_between(finding.start_page_id, finding.end_page_id)

    def pages_missing_tag(self, page_ids: list[str], slug: str) -> list[str]:
        project = self.project_service.load(reconcile=False)
        tags_by_page = {p.page_id: set(p.tags) for p in project.pages}
        return [pid for pid in page_ids if slug not in tags_by_page.get(pid, set())]

    def apply_finding_tag(
        self,
        finding: DetectionFinding,
        page_ids: list[str],
        *,
        approve_finding: bool = False,
    ) -> int:
        """Union the finding tag onto ``page_ids``. Returns how many pages changed."""
        if finding.review_status == "rejected":
            return 0
        slug = self.finding_tag_slug(finding.detector_id, finding_type=finding.finding_type)
        missing = self.pages_missing_tag(page_ids, slug)
        if not missing:
            if approve_finding:
                self.set_review_status(finding.detector_id, finding.finding_id, "approved")
            return 0
        from transcribe.services.tags import TagService

        label = self.finding_tag_label(finding.detector_id, slug=slug)
        changed = TagService().union_page_tags(
            self.project_service,
            missing,
            slug,
            label=label,
        )
        if approve_finding:
            self.set_review_status(finding.detector_id, finding.finding_id, "approved")
        return changed

    def apply_tags_from_published(self, detector_id: str) -> int:
        """Union ``finding_type`` onto span pages for non-rejected published findings."""
        findings = self.list_findings(detector_id)
        if not findings:
            return 0
        changed = 0
        for finding in findings:
            if finding.review_status == "rejected":
                continue
            changed += self.apply_finding_tag(
                finding,
                self.span_page_ids(finding),
                approve_finding=False,
            )
        return changed

    def list_findings(self, detector_id: str) -> list[DetectionFinding]:
        published = self.storage.read_published(detector_id)
        if published is None:
            return []
        return [DetectionFinding.from_dict(row) for row in (published.get("findings") or [])]

    def list_all_findings(self) -> list[DetectionFinding]:
        out: list[DetectionFinding] = []
        for info in self.list_detectors():
            out.extend(self.list_findings(info.detector_id))
        return out

    def findings_for_page(self, page_id: str) -> list[DetectionFinding]:
        out: list[DetectionFinding] = []
        for info in self.list_detectors():
            for finding in self.list_findings(info.detector_id):
                page_ids_in_span = self._page_ids_between(
                    finding.start_page_id, finding.end_page_id
                )
                if page_id in page_ids_in_span:
                    out.append(finding)
        return out

    def _page_ids_between(self, start_id: str, end_id: str) -> list[str]:
        project = self.project_service.load()
        ids = [p.page_id for p in project.pages]
        if start_id not in ids or end_id not in ids:
            return [start_id] if start_id == end_id else []
        i0 = ids.index(start_id)
        i1 = ids.index(end_id)
        if i0 > i1:
            i0, i1 = i1, i0
        return ids[i0 : i1 + 1]

    def freshness(self, detector_id: str) -> FreshnessStatus:
        custom = load_custom_detectors()
        detector = resolve_detector(detector_id, custom_detectors=custom)
        if detector is None:
            return "unavailable"
        planned, _, _ = self.runner.planned_cache_identity(detector)
        published = self.storage.read_published(detector_id)
        return detector_freshness(
            published=published,
            planned_cache_identity=planned,
            detector_version=detector.version,
        )

    def latest_attempt_state(self, detector_id: str) -> str | None:
        attempt = self.storage.latest_attempt(detector_id)
        if attempt is None:
            return None
        state = attempt.get("attempt_state")
        return str(state) if state else None

    def set_review_status(
        self,
        detector_id: str,
        finding_id: str,
        status: Literal["unreviewed", "approved", "rejected"],
    ) -> bool:
        return self.storage.update_finding_review(detector_id, finding_id, status)

    @staticmethod
    def register_custom_detector(
        definition: CustomDetectorDefinition,
    ) -> DetectorDefinition | None:
        compiled = compile_custom_detector(definition)
        if compiled is None:
            return None
        save_custom_detector(definition)
        return compiled

    @staticmethod
    def delete_custom_detector(custom_id: str) -> bool:
        return delete_custom_detector(custom_id)

    @staticmethod
    def list_custom_detector_defs() -> list[dict[str, Any]]:
        return list_custom_detector_payloads()

    @staticmethod
    def use_recorded_text_client(client: Any) -> None:
        set_text_llm_client(client)
