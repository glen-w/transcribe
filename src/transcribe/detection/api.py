"""DetectionService — programmatic API facade."""

from __future__ import annotations

from dataclasses import dataclass, replace
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
from transcribe.detection.definition import DetectorDefinition, DetectorEngine
from transcribe.detection.findings import DetectionFinding, derive_review_status
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
    engine: DetectorEngine = DetectorEngine.PROMPT


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
                engine=d.engine,
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
        finding: DetectionFinding | None = None,
    ) -> str:
        from transcribe.tagging.kernel import normalize_slug

        if finding is not None:
            data = finding.detector_data or {}
            named = data.get("tag_slug") or data.get("name")
            if isinstance(named, str) and named.strip():
                return normalize_slug(named)
        custom = load_custom_detectors()
        detector = resolve_detector(detector_id, custom_detectors=custom)
        slug_source = (
            (detector.finding_type if detector is not None else finding_type) or detector_id
        )
        return normalize_slug(slug_source)

    def finding_tag_label(
        self,
        detector_id: str,
        *,
        slug: str,
        finding: DetectionFinding | None = None,
    ) -> str:
        if finding is not None:
            name = (finding.detector_data or {}).get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
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
        eligible = self._eligible_tag_page_ids(finding, page_ids)
        slug = self.finding_tag_slug(
            finding.detector_id,
            finding_type=finding.finding_type,
            finding=finding,
        )
        missing = self.pages_missing_tag(eligible, slug)
        if not missing:
            if approve_finding:
                self._persist_review(finding, "approved")
            return 0
        from transcribe.services.tags import TagService

        label = self.finding_tag_label(finding.detector_id, slug=slug, finding=finding)
        changed = TagService().union_page_tags(
            self.project_service,
            missing,
            slug,
            label=label,
        )
        if approve_finding:
            self._persist_review(finding, "approved")
        return changed

    def _eligible_tag_page_ids(
        self, finding: DetectionFinding, page_ids: list[str]
    ) -> list[str]:
        rejected = {
            pid for pid, status in finding.page_reviews.items() if status == "rejected"
        }
        return [pid for pid in page_ids if pid not in rejected]

    def drop_finding_tag(self, finding: DetectionFinding, page_ids: list[str]) -> int:
        slug = self.finding_tag_slug(
            finding.detector_id,
            finding_type=finding.finding_type,
            finding=finding,
        )
        from transcribe.services.tags import TagService

        return TagService().drop_page_tags(self.project_service, page_ids, slug)

    def _persist_review(
        self,
        finding: DetectionFinding,
        status: str,
        *,
        page_reviews: dict[str, str] | None = None,
    ) -> bool:
        return self.storage.update_finding_review(
            finding.detector_id,
            finding.finding_id,
            status,
            page_reviews=page_reviews,
        )

    def accept_finding(self, finding: DetectionFinding) -> int:
        """Approve remaining (non-rejected) span pages and apply their tags."""
        span_ids = self.span_page_ids(finding)
        reviews = dict(finding.page_reviews)
        fully_rejected = finding.review_status == "rejected" and (
            not reviews or all(reviews.get(pid) == "rejected" for pid in span_ids)
        )
        if fully_rejected:
            targets = list(span_ids)
        else:
            targets = [pid for pid in span_ids if reviews.get(pid) != "rejected"]
        for page_id in targets:
            reviews[page_id] = "approved"
        overall = derive_review_status(span_ids, reviews)
        working = replace(finding, review_status=overall, page_reviews=reviews)
        self._persist_review(working, overall, page_reviews=reviews)
        return self.apply_finding_tag(working, targets, approve_finding=False)

    def reject_finding(self, finding: DetectionFinding) -> int:
        """Reject every span page and drop the finding tag from them."""
        span_ids = self.span_page_ids(finding)
        reviews = {pid: "rejected" for pid in span_ids}
        self._persist_review(finding, "rejected", page_reviews=reviews)
        return self.drop_finding_tag(finding, span_ids)

    def set_page_review(
        self,
        finding: DetectionFinding,
        page_id: str,
        status: str,
    ) -> int:
        """Accept or reject one page in a span finding. Returns pages whose tags changed."""
        if status not in ("approved", "rejected"):
            return 0
        span_ids = self.span_page_ids(finding)
        if page_id not in span_ids:
            return 0
        reviews = dict(finding.page_reviews)
        reviews[page_id] = status
        overall = derive_review_status(span_ids, reviews)
        working = replace(finding, review_status=overall, page_reviews=reviews)
        self._persist_review(working, overall, page_reviews=reviews)
        if status == "approved":
            return self.apply_finding_tag(working, [page_id], approve_finding=False)
        return self.drop_finding_tag(working, [page_id])

    def apply_tags_from_published(self, detector_id: str) -> int:
        """Union finding tags onto span pages for non-rejected published findings.

        Most detectors tag ``finding_type``. The names detector tags each
        detected person name (``detector_data.tag_slug``).
        """
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
