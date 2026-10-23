"""Copy the packaged sample notebook into the workspace projects directory."""

from __future__ import annotations

from pathlib import Path

from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import ProjectError
from transcribe.ingest import IngestService
from transcribe.ports import Clock, IdGenerator
from transcribe.samples import demo_notebook_dir
from transcribe.services.project import (
    ProjectService,
    allocate_notebook_root,
    open_project_paths,
)

SAMPLE_TITLE = "Sample notebook"


def copy_demo_notebook(
    projects_dir: Path | str,
    *,
    clock: Clock,
    ids: IdGenerator,
    title: str = SAMPLE_TITLE,
    corpus_paths: CorpusPaths | None = None,
) -> Path:
    """Create a normal notebook from the packaged sample pages.

    Uses ``ProjectService.create`` and ``IngestService.import_path``, then seeds
    ``edited_text`` from sidecar ``.txt`` files so OCR is optional.
    """
    source = demo_notebook_dir()
    if not source.is_dir():
        raise ProjectError(f"sample notebook missing at {source}")
    pngs = sorted(p for p in source.glob("page-*.png") if p.is_file())
    if not pngs:
        raise ProjectError(f"sample notebook has no page-*.png files at {source}")

    root = allocate_notebook_root(projects_dir, title)
    paths = open_project_paths(root)
    projects = ProjectService(paths, clock=clock, ids=ids, corpus_paths=corpus_paths)
    projects.create(title=title)
    ingest = IngestService(
        paths,
        clock=clock,
        ids=ids,
        visual_declutter_enabled=False,
    )
    for png in pngs:
        ingest.import_path(png, visual_declutter_enabled=False)

    project = projects.load()
    if len(project.pages) != len(pngs):
        raise ProjectError(
            f"sample import expected {len(pngs)} pages, got {len(project.pages)}"
        )
    for page, png in zip(project.pages, pngs, strict=True):
        sidecar = png.with_suffix(".txt")
        if sidecar.is_file():
            text = sidecar.read_text(encoding="utf-8").strip()
            if text:
                projects.save_user_edit(page.page_id, text)
    return paths.root
