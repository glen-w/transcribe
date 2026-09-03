"""Names / people detector (NER PERSON → per-page findings and tags)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from tests.conftest import FakeClock, SequentialIds
from transcribe.analysis.modules.ner import NERModule
from transcribe.analysis.runner import AnalysisRunner
from transcribe.detection.api import DetectionService
from transcribe.detection.definition import DetectorEngine
from transcribe.detection.findings import DetectionFinding, carry_forward_reviews
from transcribe.detection.ner_people import page_person_names
from transcribe.detection.registry import get_builtin_detector
from transcribe.ingest import IngestService
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.tags import TagService


def _png() -> bytes:
    img = Image.new("RGB", (32, 32), (10, 20, 30))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _fake_ner_extract(text: str):
    out = []
    for name, label in (
        ("Alice", "PERSON"),
        ("Bob", "PERSON"),
        ("Paris", "GPE"),
    ):
        if name in text:
            i = text.index(name)
            out.append((name, label, i, i + len(name)))
    return out


def _inject_ner(monkeypatch):
    import transcribe.analysis.runner as runner_mod

    original = runner_mod.get_registered_modules

    def patched(*, through: str | None = None):
        mods = original(through=through)
        mods["ner"] = NERModule(extract_fn=_fake_ner_extract)
        return mods

    monkeypatch.setattr(runner_mod, "get_registered_modules", patched)


def _runtime(tmp_path: Path) -> RuntimePaths:
    data = tmp_path / "data"
    projects = tmp_path / "projects"
    for path in (data, projects, tmp_path / "inbox", tmp_path / "exports", data / "config"):
        path.mkdir(parents=True, exist_ok=True)
    return RuntimePaths(
        repo_root=tmp_path,
        data_dir=data,
        projects_dir=projects,
        inbox_dir=tmp_path / "inbox",
        export_dir=tmp_path / "exports",
    )


def _notebook(tmp_path: Path, monkeypatch, texts: list[str]):
    runtime = _runtime(tmp_path)
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(runtime.data_dir))
    monkeypatch.setenv("TRANSCRIBE_PROJECTS_DIR", str(runtime.projects_dir))
    paths = open_project_paths(runtime.projects_dir / "nb")
    clock, ids = FakeClock(), SequentialIds("nm")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("names-nb")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, _ in enumerate(texts):
        ingest.import_bytes(f"p{i}.png", _png())
    project = projects.load()
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    return projects, clock, ids, runtime


def test_names_detector_registered():
    det = get_builtin_detector("names")
    assert det is not None
    assert det.engine == DetectorEngine.NER_PEOPLE
    assert det.finding_type == "names"
    assert "auto_tag" not in det.cache_config()


def test_page_person_names_groups_by_page_and_skips_places():
    hits = page_person_names(
        {
            "entities": [
                {
                    "surface": "Alice",
                    "label": "PERSON",
                    "unit_id": "p1",
                    "source_ref": {"page_id": "p1"},
                },
                {
                    "surface": "alice",
                    "label": "PERSON",
                    "unit_id": "p1",
                    "source_ref": {"page_id": "p1"},
                },
                {
                    "surface": "Paris",
                    "label": "GPE",
                    "unit_id": "p1",
                    "source_ref": {"page_id": "p1"},
                },
                {
                    "surface": "Bob",
                    "label": "PERSON",
                    "unit_id": "p2",
                    "source_ref": {"page_id": "p2"},
                },
            ]
        }
    )
    by_page = {(h.page_id, h.slug): h for h in hits}
    assert ("p1", "alice") in by_page
    assert by_page[("p1", "alice")].count == 2
    assert by_page[("p1", "alice")].surface == "Alice"
    assert ("p2", "bob") in by_page
    assert all(h.slug != "paris" for h in hits)


def test_names_detector_runs_ner_when_missing(tmp_path: Path, monkeypatch):
    _inject_ner(monkeypatch)
    projects, clock, ids, _runtime = _notebook(
        tmp_path,
        monkeypatch,
        ["Alice met Bob in the garden.", "No people here, only weather."],
    )
    svc = DetectionService(projects)
    result = svc.run_detector("names", force=True)
    assert result["outcome"] == "success"
    findings = result.get("findings") or []
    names = sorted(f["detector_data"]["name"] for f in findings)
    assert names == ["Alice", "Bob"]
    page0 = projects.load().pages[0].page_id
    assert all(f["start_page_id"] == page0 for f in findings)
    assert all(f["finding_type"] == "names" for f in findings)
    published_ner = (projects.paths.analysis_dir / "ner" / "published.json").exists()
    assert published_ner


def test_names_detector_reuses_published_ner(tmp_path: Path, monkeypatch):
    _inject_ner(monkeypatch)
    projects, clock, ids, _runtime = _notebook(
        tmp_path,
        monkeypatch,
        ["Alice visited Paris."],
    )
    runner = AnalysisRunner(projects, clock=clock, ids=ids)
    assert runner.run_module("ner")["outcome"] == "success"
    calls = {"n": 0}
    orig = AnalysisRunner.run_module

    def wrapped(self, module_id, *args, **kwargs):
        calls["n"] += 1
        return orig(self, module_id, *args, **kwargs)

    monkeypatch.setattr(AnalysisRunner, "run_module", wrapped)
    svc = DetectionService(projects)
    result = svc.run_detector("names", force=True)
    assert result["outcome"] == "success"
    assert calls["n"] == 0
    findings = result.get("findings") or []
    assert [f["detector_data"]["name"] for f in findings] == ["Alice"]


def test_names_auto_tag_uses_person_names(tmp_path: Path, monkeypatch):
    _inject_ner(monkeypatch)
    projects, clock, ids, runtime = _notebook(
        tmp_path,
        monkeypatch,
        ["Alice met Bob."],
    )
    svc = DetectionService(projects)
    result = svc.run_detector("names", force=True, auto_tag=True)
    assert result["outcome"] == "success"
    tagged = result.get("auto_tagged_pages")
    assert tagged and tagged >= 2
    page = projects.load().pages[0]
    assert "alice" in page.tags
    assert "bob" in page.tags
    assert "names" not in page.tags
    catalog = TagService(runtime, clock=clock, ids=SequentialIds("tag")).load_catalog()
    assert catalog.get_by_slug("alice") is not None
    assert catalog.get_by_slug("bob") is not None


def test_names_auto_tag_skips_rejected(tmp_path: Path, monkeypatch):
    _inject_ner(monkeypatch)
    projects, clock, ids, _runtime = _notebook(
        tmp_path,
        monkeypatch,
        ["Alice met Bob."],
    )
    svc = DetectionService(projects)
    result = svc.run_detector("names", force=True, auto_tag=False)
    assert result["outcome"] == "success"
    findings = svc.list_findings("names")
    bob = next(f for f in findings if f.detector_data.get("name") == "Bob")
    svc.set_review_status("names", bob.finding_id, "rejected")
    n = svc.apply_tags_from_published("names")
    assert n == 1
    page = projects.load().pages[0]
    assert "alice" in page.tags
    assert "bob" not in page.tags


def test_names_unavailable_when_ner_skipped(tmp_path: Path, monkeypatch):
    import transcribe.analysis.runner as runner_mod
    from transcribe.analysis.modules.ner import ner_config

    class _SkipNer:
        module_id = "ner"
        module_version = "1.3.0"

        def cache_config(self):
            return ner_config()

        def run(self, document, **kwargs):
            _ = document, kwargs
            return {
                "outcome": "skipped_not_applicable",
                "capability_reason": "unavailable_extra",
                "payload": {},
                "warnings": [
                    {
                        "code": "unavailable_extra",
                        "message": "spaCy NER model not available",
                    }
                ],
                "partial": False,
            }

    original = runner_mod.get_registered_modules

    def patched(*, through: str | None = None):
        mods = original(through=through)
        mods["ner"] = _SkipNer()
        return mods

    monkeypatch.setattr(runner_mod, "get_registered_modules", patched)
    projects, _clock, _ids, _runtime = _notebook(tmp_path, monkeypatch, ["Alice was here."])
    svc = DetectionService(projects)
    result = svc.run_detector("names", force=True)
    assert result["outcome"] == "skipped_not_applicable"
    assert result.get("capability") == "unavailable_extra"
    assert not (result.get("findings") or [])


def test_carry_forward_names_distinguishes_people_on_same_page():
    def _name_finding(*, finding_id: str, name: str, status: str = "unreviewed"):
        return DetectionFinding(
            finding_id=finding_id,
            detector_id="names",
            detector_version="1",
            notebook_id="nb",
            start_page_id="p1",
            end_page_id="p1",
            finding_type="names",
            confidence=1.0,
            evidence={"reason": name, "snippets": [name]},
            prompt_provenance={"prompt_id": "ner:people", "version": "1"},
            model_provenance={"model_name": "ner", "model_digest": None, "input_mode": "text"},
            input_fingerprint="fp",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
            review_status=status,
            detector_data={"name": name, "tag_slug": name.lower(), "count": 1},
        )

    prior = {
        "findings": [
            _name_finding(finding_id="old-a", name="Alice", status="approved").as_dict(),
            _name_finding(finding_id="old-b", name="Bob", status="rejected").as_dict(),
        ]
    }
    new = [
        _name_finding(finding_id="n-a", name="Alice"),
        _name_finding(finding_id="n-b", name="Bob"),
        _name_finding(finding_id="n-c", name="Carol"),
    ]
    out = carry_forward_reviews(new, prior)
    by_name = {f.detector_data["name"]: f.review_status for f in out}
    assert by_name["Alice"] == "approved"
    assert by_name["Bob"] == "rejected"
    assert by_name["Carol"] == "unreviewed"
