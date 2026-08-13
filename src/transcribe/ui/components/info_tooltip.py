"""Accessible adjacent ⓘ tooltip helpers for non-widget labels and headings.

Streamlit widgets should prefer the built-in ``help=`` parameter (native ⓘ),
wrapped with :func:`widget_help` so Settings → Interface can turn tips off.

Use this module when help must sit beside a markdown heading, metric label,
or other non-widget touchpoint.
"""

from __future__ import annotations

import html
import uuid
from collections.abc import Sequence

import streamlit as st


def info_tooltips_enabled() -> bool:
    """Return whether instructional ⓘ / Streamlit help tips are enabled."""
    from transcribe.ui.action_menus.prefs import get_cached_runtime_prefs

    return bool(get_cached_runtime_prefs().show_info_tooltips)


def widget_help(text: str | None) -> str | None:
    """Pass-through for Streamlit ``help=`` that respects Interface prefs.

    Returns ``None`` when tips are disabled or ``text`` is empty, which hides
    Streamlit's native ⓘ icon.
    """
    if text is None:
        return None
    cleaned = str(text).strip()
    if not cleaned:
        return None
    if not info_tooltips_enabled():
        return None
    return cleaned


def build_info_tooltip_html(
    lines: Sequence[str] | str,
    *,
    control_id: str,
    aria_label: str,
    test_id: str = "tx-info-tooltip",
    tip_extra_class: str = "tx-methodology-info-tip",
    wrap_extra_class: str = "tx-methodology-info",
    respect_prefs: bool = True,
) -> str:
    """Build an ⓘ button + tooltip for one or more help lines.

    Returns an empty string when there is no tip body, or when instructional
    tips are disabled and ``respect_prefs`` is True (default). Pass
    ``respect_prefs=False`` for identity disclosure controls such as run-id.
    """
    if respect_prefs and not info_tooltips_enabled():
        return ""
    if isinstance(lines, str):
        body_lines = [lines] if lines.strip() else []
    else:
        body_lines = [str(line) for line in lines if str(line).strip()]
    if not body_lines:
        return ""
    tip_body = "<br>".join(html.escape(line) for line in body_lines)
    tip_id = html.escape(control_id, quote=True)
    aria = html.escape(aria_label, quote=True)
    test = html.escape(test_id, quote=True)
    wrap_cls = html.escape(f"tx-run-id-info {wrap_extra_class}".strip(), quote=True)
    tip_cls = html.escape(f"tx-run-id-info-tip {tip_extra_class}".strip(), quote=True)
    return (
        f'<span class="{wrap_cls}" data-testid="{test}">'
        f'<button type="button" class="tx-run-id-info-btn" tabindex="0" '
        f'aria-label="{aria}" aria-describedby="{tip_id}">ⓘ</button>'
        f'<span id="{tip_id}" class="{tip_cls}" role="tooltip">{tip_body}</span>'
        f"</span>"
    )


def build_section_heading_with_info_html(
    title: str,
    tip_html: str,
    *,
    heading_tag: str = "h4",
) -> str:
    """Wrap a section title and optional ⓘ tip in the shared heading flex row."""
    tag = heading_tag if heading_tag in {"h3", "h4", "h5", "h6"} else "h4"
    return (
        f'<div class="tx-section-info-heading">'
        f"<{tag}>{html.escape(title)}</{tag}>"
        f"{tip_html}"
        f"</div>"
    )


def render_caption_with_info(
    body: str,
    help_text: str,
    *,
    control_id: str | None = None,
) -> None:
    """Caption line with adjacent ⓘ tooltip (no click / no rerun)."""
    cleaned = str(help_text).strip()
    if not cleaned or not info_tooltips_enabled():
        st.caption(body)
        return
    tip_id = control_id or f"tx-cap-tip-{uuid.uuid4().hex[:12]}"
    tip_html = build_info_tooltip_html(
        cleaned,
        control_id=tip_id,
        aria_label="More info",
    )
    if not tip_html:
        st.caption(body)
        return
    body_esc = html.escape(body)
    st.markdown(
        f'<p class="tx-caption-with-info">{body_esc}{tip_html}</p>',
        unsafe_allow_html=True,
    )
