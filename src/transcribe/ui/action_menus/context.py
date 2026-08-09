"""Action context, Path-free canonical identity, and derived capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from transcribe.ui.action_menus.ids import NavStyle, ReturnMode


class IdentityError(ValueError):
    """Raised when notebook identity fields are invalid."""


@dataclass(frozen=True)
class CanonicalIdentity:
    """Validated notebook identity with stable equality/hash (no Path fields)."""

    subject_type: str  # "notebook"
    project_id: str
    project_root_key: str  # normalised absolute path string

    def __hash__(self) -> int:
        return hash((self.subject_type, self.project_id, self.project_root_key))


@dataclass(frozen=True)
class ContextCapabilities:
    project_exists: bool
    has_pages: bool


@dataclass(frozen=True)
class ActionContext:
    """Immutable strip context for one notebook card/row."""

    identity: CanonicalIdentity
    return_mode: ReturnMode
    nav_style: NavStyle
    instance_prefix: str
    projects_dir_key: str
    # Live-derived (not from stale NotebookSummary alone)
    project_exists: bool
    has_pages: bool
    page_ids: tuple[str, ...]
    open_page_id: str | None
    cover_page_id: str | None = None


def project_root_key(root: Path) -> str:
    """Stable absolute path key after resolve()."""
    return str(Path(root).expanduser().resolve())


def build_canonical_identity(
    *,
    project_id: str,
    project_root: Path | str,
    subject_type: str = "notebook",
) -> CanonicalIdentity:
    if subject_type != "notebook":
        raise IdentityError(f"unsupported subject_type: {subject_type!r}")
    pid = (project_id or "").strip()
    if not pid:
        raise IdentityError("project_id is required")
    key = project_root_key(Path(project_root))
    if not key:
        raise IdentityError("project_root is required")
    return CanonicalIdentity(
        subject_type=subject_type,
        project_id=pid,
        project_root_key=key,
    )


def capabilities_from_context(ctx: ActionContext) -> ContextCapabilities:
    return ContextCapabilities(
        project_exists=bool(ctx.project_exists),
        has_pages=bool(ctx.has_pages and ctx.page_ids),
    )
