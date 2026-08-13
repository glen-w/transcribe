"""Folder-per-notebook overwrite prelude (operator-confirmed delete + recreate)."""

from __future__ import annotations

from transcribe.corpus.adapters import (
    OVERWRITE_CONFIRM_PHRASE,
    AlreadyImportedFolder,
)
from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import ValidationError
from transcribe.ports import Clock, SystemClock
from transcribe.services.corpus_registry import unregister_notebook
from transcribe.services.project import delete_managed_notebook


def prepare_folder_overwrite(
    conflicts: list[AlreadyImportedFolder],
    corpus_paths: CorpusPaths,
    *,
    confirm: str,
    clock: Clock | None = None,
) -> list[AlreadyImportedFolder]:
    """Delete previously imported notebooks after exact confirmation.

    Requires ``confirm == "OVERWRITE ALL"``. Unregisters each conflict from the
    corpus index, then deletes the managed notebook directory. External originals
    outside ``projects_dir`` are never touched.
    """
    if confirm != OVERWRITE_CONFIRM_PHRASE:
        raise ValidationError(
            f"overwrite refused: type {OVERWRITE_CONFIRM_PHRASE!r} to confirm " f"(got {confirm!r})"
        )
    if not conflicts:
        return []

    clk = clock or SystemClock()
    wiped: list[AlreadyImportedFolder] = []
    for conflict in conflicts:
        root = conflict.project_root
        if root.is_dir() and (root / "project.json").is_file():
            unregister_notebook(corpus_paths, conflict.notebook_id, clock=clk)
            delete_managed_notebook(root, projects_dir=corpus_paths.projects_dir)
            wiped.append(conflict)
        else:
            # Index entry without loadable project: still drop the locator.
            unregister_notebook(corpus_paths, conflict.notebook_id, clock=clk)
            wiped.append(conflict)
    return wiped
