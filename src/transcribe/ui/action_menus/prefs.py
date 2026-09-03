"""Interface menu preferences: models, sanitise, load/save, draft, recovery."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from transcribe.persistence.atomic import write_bytes_atomic
from transcribe.persistence.locks import mutation_lock
from transcribe.runtime_paths import RuntimePaths, build_runtime_paths
from transcribe.ui.action_menus.catalog import (
    ACTIONS_BY_ID,
    BUILT_IN_STANDARD_MENU,
    SECTION_ALLOWLISTS,
    section_default_actions,
)
from transcribe.ui.action_menus.ids import (
    ACTION_ORDER,
    SECTION_ORDER,
    ActionDisplay,
    ActionDisplaySetting,
    ActionId,
    SectionId,
    SectionMenuMode,
    StandardMenuMode,
)

logger = logging.getLogger(__name__)

INTERFACE_SCHEMA_VERSION = 1
INTERFACE_MENUS_FILENAME = "interface_menus.json"
DRAFT_SESSION_KEY = "interface_menus_draft"
_PREFS_CACHE: dict[str, Any] | None = None
_MAX_DIAG_LEN = 240


class SectionMenuPrefs(BaseModel):
    show_menu: bool = True
    mode: Literal["use_standard", "section_default", "manual"] = "section_default"
    selected: list[ActionId] = Field(default_factory=list)
    action_display: Literal["inherit", "icon", "text", "both"] = "inherit"


class InterfaceMenuPrefs(BaseModel):
    standard_menu_mode: Literal["built_in", "custom"] = "built_in"
    standard_menu: list[ActionId] = Field(default_factory=list)
    sections: dict[SectionId, SectionMenuPrefs] = Field(default_factory=dict)
    # Instructional ⓘ / Streamlit help= tips. Run-id identity ⓘ stays always on.
    show_info_tooltips: bool = True
    action_display: Literal["icon", "text", "both"] = "both"


@dataclass
class InterfaceDraft:
    prefs: InterfaceMenuPrefs
    raw_file_revision: str  # hash of complete raw bytes at last successful load
    recovery: bool = False
    recovery_message: str = ""
    path: Path | None = None


@dataclass
class SaveResult:
    ok: bool
    error: str | None = None
    conflict: bool = False


def _bound_diag(message: str) -> str:
    text = " ".join(message.split())
    if len(text) <= _MAX_DIAG_LEN:
        return text
    return text[: _MAX_DIAG_LEN - 3] + "..."


def interface_menus_path(runtime: RuntimePaths | None = None) -> Path:
    rt = runtime or build_runtime_paths()
    return rt.data_dir / "config" / INTERFACE_MENUS_FILENAME


def raw_file_revision(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prefs_integrity_hash(prefs_dict: dict[str, Any]) -> str:
    payload = json.dumps(prefs_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sanitise_action_ids(raw: list[Any] | None) -> list[ActionId]:
    """Keep known ActionIds, drop duplicates; emit in catalogue order."""
    if not raw:
        return []
    wanted: set[ActionId] = set()
    for item in raw:
        try:
            if isinstance(item, ActionId):
                aid = item
            else:
                aid = ActionId(str(item))
        except ValueError:
            continue
        if aid in ACTIONS_BY_ID:
            wanted.add(aid)
    return [a for a in ACTION_ORDER if a in wanted]


def sanitise_action_display(raw: Any) -> Literal["icon", "text", "both"]:
    if raw in ("icon", "text", "both"):
        return raw  # type: ignore[return-value]
    return "both"


def sanitise_section_action_display(
    raw: Any,
    *,
    default: Literal["inherit", "icon", "text", "both"] = "inherit",
) -> Literal["inherit", "icon", "text", "both"]:
    if raw in ("inherit", "icon", "text", "both"):
        return raw  # type: ignore[return-value]
    return default


def resolve_action_display(
    prefs: InterfaceMenuPrefs,
    section: SectionId,
) -> ActionDisplay:
    """Effective icon/text chrome for a section (inherit → global)."""
    sec = prefs.sections.get(section)
    if sec is None or sec.action_display == ActionDisplaySetting.INHERIT.value:
        return ActionDisplay(prefs.action_display)
    return ActionDisplay(sec.action_display)


def built_in_prefs() -> InterfaceMenuPrefs:
    sections: dict[SectionId, SectionMenuPrefs] = {}
    for sid in SECTION_ORDER:
        action_display: Literal["inherit", "icon", "text", "both"] = "inherit"
        if sid is SectionId.ARCHIVE_NOTEBOOK:
            action_display = "icon"
        sections[sid] = SectionMenuPrefs(
            show_menu=True,
            mode=SectionMenuMode.SECTION_DEFAULT.value,
            selected=[],
            action_display=action_display,
        )
    return InterfaceMenuPrefs(
        standard_menu_mode=StandardMenuMode.BUILT_IN.value,
        standard_menu=[],
        sections=sections,
        show_info_tooltips=True,
        action_display="both",
    )


def _restore_unusable_menus(prefs: InterfaceMenuPrefs) -> InterfaceMenuPrefs:
    """If sanitisation left an unusable shown menu, restore section/standard defaults."""
    data = prefs.model_copy(deep=True)
    if data.standard_menu_mode == "custom" and not data.standard_menu:
        data.standard_menu = list(BUILT_IN_STANDARD_MENU)

    for sid in SECTION_ORDER:
        sec = data.sections[sid]
        allow = set(SECTION_ALLOWLISTS[sid])
        sec.selected = [a for a in sanitise_action_ids(sec.selected) if a in allow]
        if not sec.show_menu:
            continue
        if sec.mode == "manual" and not sec.selected:
            sec.selected = list(section_default_actions(sid, subject_type="notebook"))
        elif sec.mode == "use_standard":
            std = (
                list(BUILT_IN_STANDARD_MENU)
                if data.standard_menu_mode == "built_in"
                else list(data.standard_menu)
            )
            if not any(a in allow for a in std):
                sec.selected = list(section_default_actions(sid, subject_type="notebook"))
                sec.mode = SectionMenuMode.SECTION_DEFAULT.value  # type: ignore[assignment]
    return data


def merge_prefs(partial: dict[str, Any] | None) -> InterfaceMenuPrefs:
    """Merge file payload onto built-ins; sanitise; fill unusable menus."""
    base = built_in_prefs()
    if not isinstance(partial, dict):
        return base

    mode = partial.get("standard_menu_mode", "built_in")
    if mode not in ("built_in", "custom"):
        mode = "built_in"
    standard = sanitise_action_ids(partial.get("standard_menu"))

    sections_in = partial.get("sections")
    if not isinstance(sections_in, dict):
        sections_in = {}

    sections: dict[SectionId, SectionMenuPrefs] = {}
    for sid in SECTION_ORDER:
        raw = sections_in.get(sid.value) or sections_in.get(sid)
        if not isinstance(raw, dict):
            sections[sid] = base.sections[sid]
            continue
        smode = raw.get("mode", "section_default")
        if smode not in ("use_standard", "section_default", "manual"):
            smode = "section_default"
        selected = sanitise_action_ids(raw.get("selected"))
        allow = set(SECTION_ALLOWLISTS[sid])
        selected = [a for a in selected if a in allow]
        show = raw.get("show_menu", True)
        if not isinstance(show, bool):
            show = True
        default_display = base.sections[sid].action_display
        action_display = sanitise_section_action_display(
            raw.get("action_display", default_display),
            default=default_display,
        )
        sections[sid] = SectionMenuPrefs(
            show_menu=show,
            mode=smode,
            selected=selected,
            action_display=action_display,
        )

    show_tips = partial.get("show_info_tooltips", True)
    if not isinstance(show_tips, bool):
        show_tips = True

    action_display = sanitise_action_display(partial.get("action_display", "both"))

    merged = InterfaceMenuPrefs(
        standard_menu_mode=mode,  # type: ignore[arg-type]
        standard_menu=standard,
        sections=sections,
        show_info_tooltips=show_tips,
        action_display=action_display,
    )
    return _restore_unusable_menus(merged)


def sanitise_prefs_for_save(prefs: InterfaceMenuPrefs) -> InterfaceMenuPrefs:
    """Authoritative sanitise before persist."""
    partial = prefs.model_dump(mode="json")
    return merge_prefs(partial)


def _envelope_bytes(prefs: InterfaceMenuPrefs) -> bytes:
    clean = sanitise_prefs_for_save(prefs)
    prefs_dict = clean.model_dump(mode="json")
    ordered_sections = {
        sid.value: prefs_dict["sections"][sid.value]
        for sid in SECTION_ORDER
        if sid.value in prefs_dict["sections"]
    }
    prefs_dict["sections"] = ordered_sections
    envelope = {
        "schema_version": INTERFACE_SCHEMA_VERSION,
        "prefs": prefs_dict,
        "prefs_hash": prefs_integrity_hash(prefs_dict),
    }
    return (json.dumps(envelope, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _recovery_draft(
    *,
    target: Path,
    revision: str,
    message: str,
) -> tuple[InterfaceMenuPrefs, InterfaceDraft]:
    msg = _bound_diag(message)
    logger.warning("interface_menus recovery: %s", msg)
    prefs = built_in_prefs()
    draft = InterfaceDraft(
        prefs=prefs.model_copy(deep=True),
        raw_file_revision=revision,
        recovery=True,
        recovery_message=msg,
        path=target,
    )
    return prefs, draft


def load_interface_prefs(
    path: Path | None = None,
) -> tuple[InterfaceMenuPrefs, InterfaceDraft]:
    """Load prefs. Fail-closed: never raises; returns built-ins on any fault."""
    target = path or interface_menus_path()
    try:
        if not target.exists():
            prefs = built_in_prefs()
            draft = InterfaceDraft(
                prefs=prefs.model_copy(deep=True),
                raw_file_revision=raw_file_revision(b""),
                recovery=False,
                path=target,
            )
            return prefs, draft
    except OSError as exc:
        return _recovery_draft(
            target=target,
            revision=raw_file_revision(b""),
            message=f"Could not access interface menus path: {exc}",
        )

    try:
        raw = target.read_bytes()
    except OSError as exc:
        return _recovery_draft(
            target=target,
            revision=raw_file_revision(b""),
            message=f"Could not read interface menus: {exc}",
        )

    revision = raw_file_revision(raw)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _recovery_draft(
            target=target,
            revision=revision,
            message=f"Malformed interface menus JSON: {exc}",
        )

    if not isinstance(payload, dict):
        return _recovery_draft(
            target=target,
            revision=revision,
            message="Interface menus file is not a JSON object.",
        )

    schema = payload.get("schema_version")
    if schema != INTERFACE_SCHEMA_VERSION:
        return _recovery_draft(
            target=target,
            revision=revision,
            message=(
                f"Unsupported interface menus schema_version={schema!r} "
                f"(expected {INTERFACE_SCHEMA_VERSION}). File preserved."
            ),
        )

    prefs_obj = payload.get("prefs")
    if not isinstance(prefs_obj, dict):
        return _recovery_draft(
            target=target,
            revision=revision,
            message="Interface menus envelope missing prefs object.",
        )

    stored_hash = payload.get("prefs_hash")
    recomputed = prefs_integrity_hash(prefs_obj)
    if stored_hash is not None and stored_hash != recomputed:
        return _recovery_draft(
            target=target,
            revision=revision,
            message="Interface menus prefs_hash mismatch; file preserved.",
        )

    merged = merge_prefs(prefs_obj)
    draft = InterfaceDraft(
        prefs=merged.model_copy(deep=True),
        raw_file_revision=revision,
        recovery=False,
        path=target,
    )
    return merged, draft


def invalidate_prefs_cache() -> None:
    global _PREFS_CACHE
    _PREFS_CACHE = None


def get_cached_runtime_prefs(*, path: Path | None = None) -> InterfaceMenuPrefs:
    global _PREFS_CACHE
    cache_key = str(path) if path is not None else ""
    if _PREFS_CACHE is not None and _PREFS_CACHE.get("key") == cache_key:
        return _PREFS_CACHE["prefs"]
    prefs, _ = load_interface_prefs(path)
    _PREFS_CACHE = {"prefs": prefs, "key": cache_key}
    return prefs


def _cas_write(
    draft: InterfaceDraft,
    prefs: InterfaceMenuPrefs,
    *,
    target: Path,
    backup_existing: bool,
) -> SaveResult:
    new_bytes = _envelope_bytes(prefs)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with mutation_lock(target):
            if target.exists():
                current = target.read_bytes()
            else:
                current = b""
            current_rev = raw_file_revision(current)
            if current_rev != draft.raw_file_revision:
                return SaveResult(
                    ok=False,
                    conflict=True,
                    error=(
                        "Interface menus were changed in another session. "
                        "Reload saved settings, then re-apply your edits."
                    ),
                )
            if backup_existing and target.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                backup = target.with_name(f"{target.name}.bak.{stamp}")
                shutil.copy2(target, backup)
            write_bytes_atomic(target, new_bytes)
            draft.prefs = sanitise_prefs_for_save(prefs).model_copy(deep=True)
            draft.raw_file_revision = raw_file_revision(new_bytes)
            draft.recovery = False
            draft.recovery_message = ""
            draft.path = target
    except OSError as exc:
        return SaveResult(ok=False, error=_bound_diag(f"Could not write interface menus: {exc}"))

    invalidate_prefs_cache()
    return SaveResult(ok=True)


def save_interface_prefs(
    draft: InterfaceDraft,
    *,
    path: Path | None = None,
) -> SaveResult:
    """Atomic compare-and-swap save using raw-file revision under locks."""
    if draft.recovery:
        return SaveResult(
            ok=False,
            error="Save disabled while interface menus file is in recovery state.",
        )

    target = path or draft.path or interface_menus_path()
    return _cas_write(
        draft,
        draft.prefs,
        target=target,
        backup_existing=False,
    )


def restore_built_in_defaults(
    draft: InterfaceDraft,
    *,
    path: Path | None = None,
) -> SaveResult:
    """Persisted Restore built-ins with the same CAS protection as Save."""
    target = path or draft.path or interface_menus_path()
    return _cas_write(
        draft,
        built_in_prefs(),
        target=target,
        backup_existing=True,
    )


def hydrate_draft_from_disk(
    session_state: dict[str, Any], *, path: Path | None = None
) -> InterfaceDraft:
    _, draft = load_interface_prefs(path)
    session_state[DRAFT_SESSION_KEY] = draft
    return draft


def reset_draft_to_built_ins(session_state: dict[str, Any]) -> InterfaceDraft:
    """Unsaved draft reset only; preserves recovery flag and baseline revision."""
    existing = session_state.get(DRAFT_SESSION_KEY)
    recovery = False
    recovery_message = ""
    revision = raw_file_revision(b"")
    path = interface_menus_path()
    if isinstance(existing, InterfaceDraft):
        recovery = existing.recovery
        recovery_message = existing.recovery_message
        revision = existing.raw_file_revision
        path = existing.path or path
    draft = InterfaceDraft(
        prefs=built_in_prefs(),
        raw_file_revision=revision,
        recovery=recovery,
        recovery_message=recovery_message,
        path=path,
    )
    session_state[DRAFT_SESSION_KEY] = draft
    return draft


def reload_draft_from_disk(
    session_state: dict[str, Any], *, path: Path | None = None
) -> InterfaceDraft:
    return hydrate_draft_from_disk(session_state, path=path)


def get_or_hydrate_draft(
    session_state: dict[str, Any], *, path: Path | None = None
) -> InterfaceDraft:
    existing = session_state.get(DRAFT_SESSION_KEY)
    if isinstance(existing, InterfaceDraft):
        return existing
    return hydrate_draft_from_disk(session_state, path=path)


def draft_is_dirty(draft: InterfaceDraft, *, path: Path | None = None) -> bool:
    """True when draft prefs differ from the last successfully loaded on-disk prefs."""
    if draft.recovery:
        return False
    loaded, _ = load_interface_prefs(path or draft.path)
    return draft.prefs.model_dump(mode="json") != loaded.model_dump(mode="json")


def validate_draft_for_save(prefs: InterfaceMenuPrefs) -> str | None:
    """Return error if an enabled section would have no allowed actions."""
    from transcribe.ui.action_menus.resolve import configured_actions_for_section

    clean = sanitise_prefs_for_save(prefs)
    for sid in SECTION_ORDER:
        section = clean.sections[sid]
        if not section.show_menu:
            continue
        configured = configured_actions_for_section(
            clean,
            sid,
            subject_type="notebook",
            apply_capabilities=False,
        )
        if not configured:
            return (
                f"Section “{sid.value}” has Show menu on but no allowed actions "
                f"for the selected mode. Choose at least one action or turn Show menu off."
            )
    return None
