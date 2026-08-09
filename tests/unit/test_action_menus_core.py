"""Core tests for interface action-menu prefs, catalogue, resolve, and nav."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transcribe.ports import UuidGenerator
from transcribe.ingest import IngestService
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.ui.action_menus.catalog import (
    ACTIONS,
    ACTIONS_BY_ID,
    BUILT_IN_STANDARD_MENU,
    SECTION_ALLOWLISTS,
    SECTION_DEFAULTS,
    help_for,
    icon_for,
    label_for,
    section_default_actions,
)
from transcribe.ui.action_menus.context import (
    ActionContext,
    IdentityError,
    build_canonical_identity,
    capabilities_from_context,
    project_root_key,
)
from transcribe.ui.action_menus.handlers import (
    HANDLERS,
    assert_handler_registry_closed,
    is_action_available,
)
from transcribe.ui.action_menus.ids import (
    SECTION_ORDER,
    ActionId,
    NavStyle,
    ReturnMode,
    SectionId,
    WorkflowMode,
    parse_return_mode,
)
from transcribe.ui.action_menus.nav import (
    ProjectRootError,
    first_valid_open_page,
    load_live_notebook_context,
    navigate_open,
    navigate_workflow,
    validate_project_root,
)
from transcribe.ui.action_menus.prefs import (
    INTERFACE_SCHEMA_VERSION,
    InterfaceMenuPrefs,
    SectionMenuPrefs,
    built_in_prefs,
    draft_is_dirty,
    invalidate_prefs_cache,
    load_interface_prefs,
    merge_prefs,
    prefs_integrity_hash,
    raw_file_revision,
    restore_built_in_defaults,
    sanitise_action_ids,
    save_interface_prefs,
    validate_draft_for_save,
)
from transcribe.ui.action_menus.render import action_widget_key
from transcribe.ui.action_menus.resolve import (
    configured_actions_for_section,
    resolve_section_actions,
)
from tests.conftest import FakeClock
from tests.ingest.test_ingest import _png_bytes


@pytest.fixture(autouse=True)
def _clear_prefs_cache() -> None:
    invalidate_prefs_cache()
    yield
    invalidate_prefs_cache()


def _write_envelope(path: Path, prefs: InterfaceMenuPrefs, *, schema: int = 1) -> bytes:
    prefs_dict = prefs.model_dump(mode="json")
    envelope = {
        "schema_version": schema,
        "prefs": prefs_dict,
        "prefs_hash": prefs_integrity_hash(prefs_dict),
    }
    raw = (json.dumps(envelope, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _make_project(projects_dir: Path, name: str = "nb1", *, with_page: bool = False):
    root = projects_dir / name
    paths = open_project_paths(root)
    clock, ids = FakeClock(), UuidGenerator()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create(name)
    if with_page:
        ingest = IngestService(paths, clock=clock, ids=ids)
        project = ingest.import_bytes("a.png", _png_bytes())
    return project, root


def test_catalogue_invariants() -> None:
    assert_handler_registry_closed()
    assert len(ACTIONS) == len({a.id for a in ACTIONS})
    for action in ACTIONS:
        assert action.label
        assert action.icon
        assert action.help
        assert action.id in HANDLERS
    for sid, allow in SECTION_ALLOWLISTS.items():
        for aid in allow:
            assert aid in ACTIONS_BY_ID
            assert aid in HANDLERS
    for key, defaults in SECTION_DEFAULTS.items():
        assert defaults
        allow = set(SECTION_ALLOWLISTS[key.section])
        for aid in defaults:
            assert aid in allow
    assert set(HANDLERS) == {a.id for a in ACTIONS}


def test_section_defaults() -> None:
    assert list(section_default_actions(SectionId.ARCHIVE_NOTEBOOK)) == [
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
    ]
    assert list(section_default_actions(SectionId.VIEW_NOTEBOOK)) == [
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
        ActionId.RENAME,
        ActionId.DELETE,
    ]
    prefs = built_in_prefs()
    assert configured_actions_for_section(prefs, SectionId.ARCHIVE_NOTEBOOK) == [
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
    ]
    assert configured_actions_for_section(prefs, SectionId.VIEW_NOTEBOOK) == [
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
        ActionId.RENAME,
        ActionId.DELETE,
    ]


def test_sanitise_drops_unknown_and_duplicates() -> None:
    assert sanitise_action_ids(
        ["open", "bogus", "analyse", "open", ActionId.EXPORT]
    ) == [ActionId.OPEN, ActionId.ANALYSE, ActionId.EXPORT]


def test_merge_partial_preserves_custom_and_fills_missing_sections() -> None:
    partial = {
        "standard_menu_mode": "custom",
        "standard_menu": ["open", "analyse", "unknown"],
        "sections": {
            "archive_notebook": {
                "show_menu": True,
                "mode": "manual",
                "selected": ["export", "open", "open"],
            }
        },
    }
    merged = merge_prefs(partial)
    assert merged.standard_menu == [ActionId.OPEN, ActionId.ANALYSE]
    assert SectionId.VIEW_NOTEBOOK in merged.sections
    assert merged.sections[SectionId.VIEW_NOTEBOOK].mode == "section_default"
    assert merged.sections[SectionId.ARCHIVE_NOTEBOOK].selected == [
        ActionId.OPEN,
        ActionId.EXPORT,
    ]


def test_empty_manual_restores_section_defaults() -> None:
    partial = {
        "sections": {
            "archive_notebook": {
                "show_menu": True,
                "mode": "manual",
                "selected": ["not-an-action"],
            }
        }
    }
    merged = merge_prefs(partial)
    assert merged.sections[SectionId.ARCHIVE_NOTEBOOK].selected == [
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
    ]


def test_load_missing_file_uses_builtins(tmp_path: Path) -> None:
    path = tmp_path / "config" / "interface_menus.json"
    prefs, draft = load_interface_prefs(path)
    assert prefs == built_in_prefs()
    assert draft.recovery is False
    assert draft.raw_file_revision == raw_file_revision(b"")


def test_load_non_object_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "interface_menus.json"
    path.write_text("[1, 2, 3]\n", encoding="utf-8")
    prefs, draft = load_interface_prefs(path)
    assert prefs == built_in_prefs()
    assert draft.recovery is True
    assert "not a JSON object" in draft.recovery_message
    assert path.read_text(encoding="utf-8").startswith("[")


def test_render_isolation_swallows_resolve_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """One strip failure must not raise into the Archive/View loop."""
    import transcribe.ui.action_menus.render as render_mod

    captions: list[str] = []

    class _FakeSt:
        def caption(self, text: str) -> None:
            captions.append(text)

        def columns(self, *_a, **_k):  # pragma: no cover
            raise AssertionError("columns should not run after resolve failure")

    monkeypatch.setattr(render_mod, "st", _FakeSt())
    monkeypatch.setattr(
        render_mod,
        "resolve_section_actions",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    ident = build_canonical_identity(project_id="p", project_root="/tmp/p")
    ctx = ActionContext(
        identity=ident,
        return_mode=ReturnMode.ARCHIVE,
        nav_style=NavStyle.CLICK_RERUN,
        instance_prefix="archive",
        projects_dir_key="/tmp",
        project_exists=True,
        has_pages=True,
        page_ids=("x",),
        open_page_id="x",
    )
    assert render_mod.render_configured_actions(SectionId.ARCHIVE_NOTEBOOK, ctx) == []
    assert captions and "unavailable" in captions[0].lower()


def test_load_corrupt_json_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "interface_menus.json"
    path.write_text("{not json", encoding="utf-8")
    prefs, draft = load_interface_prefs(path)
    assert prefs == built_in_prefs()
    assert draft.recovery is True
    assert "Malformed" in draft.recovery_message
    assert path.read_text(encoding="utf-8") == "{not json"


def test_load_unknown_schema_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "interface_menus.json"
    _write_envelope(path, built_in_prefs(), schema=99)
    prefs, draft = load_interface_prefs(path)
    assert prefs == built_in_prefs()
    assert draft.recovery is True
    assert "schema_version=99" in draft.recovery_message
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 99


def test_load_hash_mismatch_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "interface_menus.json"
    prefs_dict = built_in_prefs().model_dump(mode="json")
    envelope = {
        "schema_version": INTERFACE_SCHEMA_VERSION,
        "prefs": prefs_dict,
        "prefs_hash": "deadbeef",
    }
    path.write_text(json.dumps(envelope), encoding="utf-8")
    prefs, draft = load_interface_prefs(path)
    assert draft.recovery is True
    assert "prefs_hash" in draft.recovery_message
    assert prefs == built_in_prefs()


def test_save_cas_conflict(tmp_path: Path) -> None:
    path = tmp_path / "interface_menus.json"
    raw = _write_envelope(path, built_in_prefs())
    _, draft = load_interface_prefs(path)
    assert draft.raw_file_revision == raw_file_revision(raw)

    # Concurrent writer changes bytes under a different draft baseline.
    other = built_in_prefs()
    other.sections[SectionId.ARCHIVE_NOTEBOOK].show_menu = False
    _write_envelope(path, other)

    draft.prefs.sections[SectionId.VIEW_NOTEBOOK].show_menu = False
    result = save_interface_prefs(draft, path=path)
    assert result.ok is False
    assert result.conflict is True
    # Disk still has the concurrent write
    loaded, _ = load_interface_prefs(path)
    assert loaded.sections[SectionId.ARCHIVE_NOTEBOOK].show_menu is False


def test_save_and_restore_cas_success(tmp_path: Path) -> None:
    path = tmp_path / "interface_menus.json"
    _, draft = load_interface_prefs(path)
    draft.prefs.sections[SectionId.ARCHIVE_NOTEBOOK].mode = "manual"
    draft.prefs.sections[SectionId.ARCHIVE_NOTEBOOK].selected = [
        ActionId.OPEN,
        ActionId.ANALYSE,
    ]
    result = save_interface_prefs(draft, path=path)
    assert result.ok
    loaded, draft2 = load_interface_prefs(path)
    assert loaded.sections[SectionId.ARCHIVE_NOTEBOOK].selected == [
        ActionId.OPEN,
        ActionId.ANALYSE,
    ]

    result2 = restore_built_in_defaults(draft2, path=path)
    assert result2.ok
    loaded2, _ = load_interface_prefs(path)
    assert loaded2.sections[SectionId.ARCHIVE_NOTEBOOK].mode == "section_default"
    bak = list(path.parent.glob("interface_menus.json.bak.*"))
    assert bak


def test_restore_cas_conflict(tmp_path: Path) -> None:
    path = tmp_path / "interface_menus.json"
    _write_envelope(path, built_in_prefs())
    _, draft = load_interface_prefs(path)
    other = built_in_prefs()
    other.standard_menu_mode = "custom"
    other.standard_menu = [ActionId.OPEN]
    _write_envelope(path, other)
    result = restore_built_in_defaults(draft, path=path)
    assert result.ok is False
    assert result.conflict is True


def test_save_blocked_in_recovery(tmp_path: Path) -> None:
    path = tmp_path / "interface_menus.json"
    path.write_text("{}", encoding="utf-8")
    _, draft = load_interface_prefs(path)
    assert draft.recovery
    result = save_interface_prefs(draft, path=path)
    assert result.ok is False
    assert "recovery" in (result.error or "")


def test_unwritable_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config" / "interface_menus.json"
    _, draft = load_interface_prefs(path)
    draft.prefs.sections[SectionId.ARCHIVE_NOTEBOOK].show_menu = False

    def _boom(*_a, **_k):
        raise OSError("permission denied")

    monkeypatch.setattr(
        "transcribe.ui.action_menus.prefs.write_bytes_atomic",
        _boom,
    )
    result = save_interface_prefs(draft, path=path)
    assert result.ok is False
    assert "permission" in (result.error or "").lower() or "write" in (
        result.error or ""
    ).lower()


def test_draft_dirty_and_reload(tmp_path: Path) -> None:
    path = tmp_path / "interface_menus.json"
    _, draft = load_interface_prefs(path)
    assert draft_is_dirty(draft, path=path) is False
    draft.prefs.sections[SectionId.ARCHIVE_NOTEBOOK].show_menu = False
    assert draft_is_dirty(draft, path=path) is True


def test_show_menu_off_and_zero_capabilities() -> None:
    prefs = built_in_prefs()
    prefs.sections[SectionId.ARCHIVE_NOTEBOOK].show_menu = False
    assert configured_actions_for_section(prefs, SectionId.ARCHIVE_NOTEBOOK) == []

    ident = build_canonical_identity(project_id="p1", project_root="/tmp/p1")
    ctx = ActionContext(
        identity=ident,
        return_mode=ReturnMode.ARCHIVE,
        nav_style=NavStyle.CLICK_RERUN,
        instance_prefix="t",
        projects_dir_key="/tmp",
        project_exists=False,
        has_pages=False,
        page_ids=(),
        open_page_id=None,
    )
    prefs2 = built_in_prefs()
    assert resolve_section_actions(SectionId.ARCHIVE_NOTEBOOK, ctx, prefs=prefs2) == []


def test_resolve_capability_filter() -> None:
    prefs = built_in_prefs()
    prefs.sections[SectionId.ARCHIVE_NOTEBOOK].mode = "manual"
    prefs.sections[SectionId.ARCHIVE_NOTEBOOK].selected = list(BUILT_IN_STANDARD_MENU)
    ident = build_canonical_identity(project_id="p1", project_root="/tmp/p1")
    ctx = ActionContext(
        identity=ident,
        return_mode=ReturnMode.ARCHIVE,
        nav_style=NavStyle.CLICK_RERUN,
        instance_prefix="t",
        projects_dir_key="/tmp",
        project_exists=True,
        has_pages=False,
        page_ids=(),
        open_page_id=None,
    )
    resolved = resolve_section_actions(SectionId.ARCHIVE_NOTEBOOK, ctx, prefs=prefs)
    assert ActionId.OPEN not in resolved
    assert ActionId.TRANSCRIBE in resolved
    assert ActionId.ANALYSE in resolved
    assert ActionId.EXPORT in resolved


def test_identity_path_free_equality(tmp_path: Path) -> None:
    a = build_canonical_identity(project_id="x", project_root=tmp_path / "a")
    b = build_canonical_identity(project_id="x", project_root=str(tmp_path / "a"))
    assert a == b
    assert hash(a) == hash(b)
    assert not hasattr(a, "project_root") or not isinstance(
        getattr(a, "project_root", None), Path
    )
    with pytest.raises(IdentityError):
        build_canonical_identity(project_id="", project_root=tmp_path)


def test_validate_project_root(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    _, root = _make_project(projects, "ok")
    assert validate_project_root(root, projects_dir=projects) == root.resolve()

    with pytest.raises(ProjectRootError):
        validate_project_root(tmp_path / "outside", projects_dir=projects)
    with pytest.raises(ProjectRootError):
        validate_project_root(projects, projects_dir=projects)
    gone = projects / "deleted"
    gone.mkdir()
    (gone / "project.json").write_text("{}", encoding="utf-8")
    validate_project_root(gone, projects_dir=projects)
    gone_path = gone.resolve()
    # remove project
    (gone / "project.json").unlink()
    with pytest.raises(ProjectRootError):
        validate_project_root(gone_path, projects_dir=projects)


def test_navigate_refuses_stale_without_session_mutation(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    session: dict = {"ui_mode": "Archive", "root": "old"}
    ok = navigate_workflow(
        project_root_key=str(projects / "missing"),
        projects_dir_key=project_root_key(projects),
        mode=WorkflowMode.TRANSCRIBE,
        session=session,
        rerun=False,
    )
    assert ok is False
    assert session == {"ui_mode": "Archive", "root": "old"}


def test_navigate_workflow_ordered_transition(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    project, root = _make_project(projects, "wf", with_page=False)
    session = {
        "ui_mode": "Archive",
        "show_page_viewer": True,
        "view_page_id": "x",
        "page_return_mode": "Archive",
    }
    ok = navigate_workflow(
        project_root_key=str(root),
        projects_dir_key=project_root_key(projects),
        mode=WorkflowMode.ANALYSE,
        session=session,
        rerun=False,
    )
    assert ok is True
    assert session["root"] == str(root.resolve())
    assert session["ui_mode"] == "Analyse"
    assert session["show_page_viewer"] is False
    assert "view_page_id" not in session
    assert project.id


def test_open_return_modes_independent(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    project, root = _make_project(projects, "openme", with_page=True)
    for mode in (ReturnMode.ARCHIVE, ReturnMode.VIEW):
        ctx = load_live_notebook_context(
            project_id=project.id,
            project_root=root,
            projects_dir=projects,
            return_mode=mode,
        )
        assert ctx.has_pages
        session: dict = {}
        assert navigate_open(ctx, session=session, rerun=False) is True
        assert session["page_return_mode"] == mode.value
        assert session["ui_mode"] == mode.value
        assert session["view_page_id"] in session["view_page_ids"]


def test_first_valid_open_page_skips_stale_cover(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    project, _root = _make_project(projects, "cover", with_page=True)
    project.cover_page_id = "deleted-cover-id"
    assert first_valid_open_page(project) == project.pages[0].page_id
    project.cover_page_id = project.pages[0].page_id
    assert first_valid_open_page(project) == project.pages[0].page_id


def test_empty_notebook_open_unavailable(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    project, root = _make_project(projects, "empty", with_page=False)
    ctx = load_live_notebook_context(
        project_id=project.id,
        project_root=root,
        projects_dir=projects,
        return_mode=ReturnMode.ARCHIVE,
    )
    caps = capabilities_from_context(ctx)
    assert caps.project_exists
    assert not caps.has_pages
    assert not is_action_available(ActionId.OPEN, ctx, caps)
    assert is_action_available(ActionId.TRANSCRIBE, ctx, caps)
    assert is_action_available(ActionId.RENAME, ctx, caps)
    assert is_action_available(ActionId.DELETE, ctx, caps)
    session: dict = {}
    assert navigate_open(ctx, session=session, rerun=False) is False
    assert session == {}


def test_catalog_helpers_and_unknown_section_fallback() -> None:
    assert label_for(ActionId.RENAME) == ACTIONS_BY_ID[ActionId.RENAME].label
    assert icon_for(ActionId.DELETE) == ACTIONS_BY_ID[ActionId.DELETE].icon
    assert help_for(ActionId.OPEN) == ACTIONS_BY_ID[ActionId.OPEN].help
    assert section_default_actions(SectionId.VIEW_NOTEBOOK) == (
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
        ActionId.RENAME,
        ActionId.DELETE,
    )
    # Unknown subject_type falls back to allowlist first action.
    assert section_default_actions(
        SectionId.ARCHIVE_NOTEBOOK, subject_type="page"
    ) == (SECTION_ALLOWLISTS[SectionId.ARCHIVE_NOTEBOOK][0],)


def test_view_defaults_include_rename_and_delete_not_archive(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    project, root = _make_project(projects, "del", with_page=True)
    ctx = load_live_notebook_context(
        project_id=project.id,
        project_root=root,
        projects_dir=projects,
        return_mode=ReturnMode.VIEW,
    )
    prefs = built_in_prefs()
    assert resolve_section_actions(SectionId.VIEW_NOTEBOOK, ctx, prefs=prefs) == [
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
        ActionId.RENAME,
        ActionId.DELETE,
    ]
    archive_actions = resolve_section_actions(
        SectionId.ARCHIVE_NOTEBOOK, ctx, prefs=prefs
    )
    assert ActionId.RENAME not in archive_actions
    assert ActionId.DELETE not in archive_actions
    assert ActionId.RENAME in SECTION_ALLOWLISTS[SectionId.ARCHIVE_NOTEBOOK]


def test_widget_keys_unique_across_notebooks() -> None:
    k1 = action_widget_key(
        instance_prefix="archive",
        section=SectionId.ARCHIVE_NOTEBOOK,
        project_id="a",
        action=ActionId.OPEN,
    )
    k2 = action_widget_key(
        instance_prefix="archive",
        section=SectionId.ARCHIVE_NOTEBOOK,
        project_id="b",
        action=ActionId.OPEN,
    )
    assert k1 != k2
    assert "archive_notebook" in k1
    assert "__open__" in k1 or "open" in k1


def test_parse_return_mode() -> None:
    assert parse_return_mode("Archive") is ReturnMode.ARCHIVE
    assert parse_return_mode("View") is ReturnMode.VIEW
    assert parse_return_mode("Transcribe") is None
    assert parse_return_mode("bogus") is None


def test_validate_draft_for_save_empty_manual() -> None:
    prefs = built_in_prefs()
    # Force an unusable config that sanitise would normally repair — bypass by
    # turning show off then on with empty after constructing invalid mid-state
    # via model without merge.
    prefs.sections[SectionId.ARCHIVE_NOTEBOOK] = SectionMenuPrefs(
        show_menu=True,
        mode="manual",
        selected=[],
    )
    # validate runs sanitise which restores defaults → no error
    assert validate_draft_for_save(prefs) is None


def test_resolve_preserves_manual_configured_order() -> None:
    prefs = built_in_prefs()
    prefs.sections[SectionId.VIEW_NOTEBOOK].mode = "manual"
    prefs.sections[SectionId.VIEW_NOTEBOOK].selected = [
        ActionId.EXPORT,
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
    ]
    assert configured_actions_for_section(prefs, SectionId.VIEW_NOTEBOOK) == [
        ActionId.EXPORT,
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
    ]


def test_rendering_path_performs_no_mutation_writes(tmp_path: Path) -> None:
    """Resolve / capability build must not write prefs or mutate projects."""
    projects = tmp_path / "projects"
    projects.mkdir()
    project, root = _make_project(projects, "ro", with_page=True)
    prefs_path = tmp_path / "config" / "interface_menus.json"
    _write_envelope(prefs_path, built_in_prefs())
    before = {
        p: p.stat().st_mtime_ns
        for p in [prefs_path, root / "project.json"]
        if p.exists()
    }
    ctx = load_live_notebook_context(
        project_id=project.id,
        project_root=root,
        projects_dir=projects,
        return_mode=ReturnMode.ARCHIVE,
    )
    prefs, _ = load_interface_prefs(prefs_path)
    resolve_section_actions(SectionId.ARCHIVE_NOTEBOOK, ctx, prefs=prefs)
    after = {
        p: p.stat().st_mtime_ns
        for p in [prefs_path, root / "project.json"]
        if p.exists()
    }
    assert before == after


def test_deleted_notebook_context_zero_actions(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    project, root = _make_project(projects, "gone", with_page=True)
    pid = project.id
    # Delete after capturing paths
    import shutil

    shutil.rmtree(root)
    ctx = load_live_notebook_context(
        project_id=pid,
        project_root=root,
        projects_dir=projects,
        return_mode=ReturnMode.VIEW,
    )
    assert ctx.project_exists is False
    assert resolve_section_actions(
        SectionId.VIEW_NOTEBOOK, ctx, prefs=built_in_prefs()
    ) == []


def test_archive_view_wire_uses_configured_actions() -> None:
    source = Path("src/transcribe/ui/archive_views.py").read_text(encoding="utf-8")
    assert "render_configured_actions" in source
    assert "SectionId.ARCHIVE_NOTEBOOK" in source
    assert "SectionId.VIEW_NOTEBOOK" in source
    assert "ReturnMode.ARCHIVE" in source
    assert "ReturnMode.VIEW" in source
    shell = Path("src/transcribe/ui/shell.py").read_text(encoding="utf-8")
    assert "st-key-tr_al_" in shell
    assert "Settings" in shell


def test_multi_notebook_resolve_smoke(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    p1, r1 = _make_project(projects, "a", with_page=True)
    p2, r2 = _make_project(projects, "b", with_page=True)
    prefs = built_in_prefs()
    prefs.sections[SectionId.ARCHIVE_NOTEBOOK].mode = "manual"
    prefs.sections[SectionId.ARCHIVE_NOTEBOOK].selected = [
        ActionId.ANALYSE,
        ActionId.OPEN,
        ActionId.EXPORT,
    ]
    keys = set()
    for project, root in ((p1, r1), (p2, r2)):
        ctx = load_live_notebook_context(
            project_id=project.id,
            project_root=root,
            projects_dir=projects,
            return_mode=ReturnMode.ARCHIVE,
            instance_prefix="archive",
        )
        actions = resolve_section_actions(
            SectionId.ARCHIVE_NOTEBOOK, ctx, prefs=prefs
        )
        assert actions == [ActionId.ANALYSE, ActionId.OPEN, ActionId.EXPORT]
        for action in actions:
            keys.add(
                action_widget_key(
                    instance_prefix="archive",
                    section=SectionId.ARCHIVE_NOTEBOOK,
                    project_id=project.id,
                    action=action,
                )
            )
    assert len(keys) == 6


def test_settings_state_machine_save_reload_restore(tmp_path: Path) -> None:
    path = tmp_path / "interface_menus.json"
    _, draft = load_interface_prefs(path)
    assert draft_is_dirty(draft, path=path) is False

    draft.prefs.sections[SectionId.ARCHIVE_NOTEBOOK].mode = "manual"
    draft.prefs.sections[SectionId.ARCHIVE_NOTEBOOK].selected = [
        ActionId.OPEN,
        ActionId.EXPORT,
    ]
    assert draft_is_dirty(draft, path=path) is True
    assert save_interface_prefs(draft, path=path).ok

    # Simulate another session conflicting restore baseline
    _, draft_b = load_interface_prefs(path)
    draft.prefs.sections[SectionId.VIEW_NOTEBOOK].show_menu = False  # stale draft
    # Refresh draft_b and edit disk via save from draft_b
    draft_b.prefs.sections[SectionId.VIEW_NOTEBOOK].mode = "manual"
    draft_b.prefs.sections[SectionId.VIEW_NOTEBOOK].selected = [ActionId.TRANSCRIBE]
    assert save_interface_prefs(draft_b, path=path).ok

    # Stale draft save conflicts
    assert save_interface_prefs(draft, path=path).conflict is True

    # Reload clears dirty against disk
    loaded, draft_c = load_interface_prefs(path)
    assert loaded.sections[SectionId.VIEW_NOTEBOOK].selected == [ActionId.TRANSCRIBE]
    assert draft_is_dirty(draft_c, path=path) is False
    assert restore_built_in_defaults(draft_c, path=path).ok
