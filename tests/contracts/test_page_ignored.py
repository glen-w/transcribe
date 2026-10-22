"""Contract: Page.ignored round-trips and Reading filter semantics."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes
from transcribe.ingest import IngestService
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.ui.action_menus.nav import chronological_page_ids

pytestmark = pytest.mark.contract


def test_page_ignored_persists_in_project_json(tmp_path: Path):
    paths = open_project_paths(tmp_path / "nb")
    clock, ids = FakeClock(), SequentialIds("ign")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("Ignored contract")
    IngestService(paths, clock=clock, ids=ids).import_bytes("a.png", _png_bytes())
    page_id = projects.load().pages[0].page_id
    projects.set_page_ignored(page_id, True)
    reloaded = ProjectService(paths, clock=clock, ids=ids).load()
    assert reloaded.pages[0].ignored is True
    payload = reloaded.as_dict()
    assert payload["pages"][0].get("ignored") is True
    visible = chronological_page_ids(reloaded, include_ignored=False)
    assert visible == []
