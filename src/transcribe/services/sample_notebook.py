"""Install the bundled sample notebook into the projects directory (U2.2)."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from PIL import Image, ImageDraw

from transcribe.ingest import IngestService
from transcribe.ports import Clock, IdGenerator, SystemClock, UuidGenerator
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.project import ProjectService, open_project_paths

SAMPLE_SLUG = "sample-notebook"
SAMPLE_TITLE = "Sample notebook"


def sample_package_root() -> Path:
    """Return the on-disk samples/demo-notebook directory (repo or package data)."""
    repo = Path(__file__).resolve().parents[3] / "samples" / "demo-notebook"
    if repo.is_dir():
        return repo
    # Packaged fallback (optional): samples shipped beside the package later.
    try:
        traj = resources.files("transcribe").joinpath("data", "sample-notebook")
        if traj.is_dir():
            return Path(str(traj))
    except (TypeError, AttributeError, ModuleNotFoundError):
        pass
    return repo


def _write_placeholder_png(dest: Path, *, label: str, size: tuple[int, int] = (640, 480)) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, (245, 242, 235))
    draw = ImageDraw.Draw(img)
    draw.rectangle([24, 24, size[0] - 24, size[1] - 24], outline=(60, 60, 60), width=2)
    draw.text((40, 40), label, fill=(30, 30, 30))
    img.save(dest, format="PNG")


def ensure_sample_fixture(root: Path | None = None) -> Path:
    """Ensure placeholder PNGs exist for the committed sample manifest."""
    base = root or sample_package_root()
    manifest_path = base / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"sample manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pages_dir = base / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for i, row in enumerate(manifest.get("pages") or [], start=1):
        rel = str(row.get("file") or f"page_{i:02d}.png")
        dest = pages_dir / Path(rel).name
        if not dest.is_file():
            _write_placeholder_png(dest, label=f"Sample page {i}")
    return base


def install_sample_notebook(
    runtime: RuntimePaths,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    force: bool = False,
) -> Path:
    """Copy the sample into ``runtime.projects_dir`` and return the project root.

    Uses existing ``ProjectService.create`` + ``IngestService.import_bytes`` and
    seeds ``edited_text`` so deterministic Analyse modules run without OCR.
    """
    clock = clock or SystemClock()
    ids = ids or UuidGenerator()
    fixture = ensure_sample_fixture()
    manifest_path = fixture / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"sample manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dest = runtime.projects_dir / SAMPLE_SLUG
    if dest.exists() and not force:
        # Already installed — return existing root.
        return dest
    if dest.exists() and force:
        import shutil

        shutil.rmtree(dest)

    paths = open_project_paths(dest)
    projects = ProjectService(paths, clock=clock, ids=ids)
    title = str(manifest.get("title") or SAMPLE_TITLE)
    projects.create(title)
    ingest = IngestService(paths, clock=clock, ids=ids)
    page_rows = list(manifest.get("pages") or [])
    for row in page_rows:
        rel = str(row.get("file") or "")
        src = fixture / "pages" / rel
        if not src.is_file():
            continue
        ingest.import_bytes(rel, src.read_bytes())
    project = projects.load()
    for page, row in zip(project.pages, page_rows, strict=False):
        text = str(row.get("text") or "").strip()
        if text:
            projects.save_user_edit(page.page_id, text)
    return dest
