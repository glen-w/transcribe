"""Settings → Tags: workspace catalog manager (rename, colour, merge, delete)."""

from __future__ import annotations

import streamlit as st

from transcribe.runtime_paths import build_runtime_paths
from transcribe.services.tags import TagService
from transcribe.tagging.kernel import TagError, default_color_for_slug, parse_hex_color
from transcribe.ui import icons as ic
from transcribe.ui.tag_pills import render_tag_chips


@st.fragment
def render_tags_settings_panel() -> None:
    st.subheader("Tags")
    st.caption(
        "Workspace catalogue for notebook and page tags. Renaming a label keeps "
        "existing assignments. Changing a slug, merging, or deleting rewrites "
        "every notebook (skipped while OCR or Analyse is running)."
    )
    runtime = build_runtime_paths()
    svc = TagService(runtime)
    loaded = svc.catalog_load()
    if loaded.recovery:
        st.error(
            "Tag catalogue file needs recovery and was not overwritten. "
            f"{loaded.recovery_message}"
        )
        return

    catalog = loaded.catalog
    usage = svc.usage_counts()

    st.markdown("#### Create")
    c1, c2, c3 = st.columns([3, 1, 1])
    new_label = c1.text_input("Label", key="tag_create_label")
    new_color = c2.color_picker(
        "Colour",
        value=default_color_for_slug(new_label.strip().lower() or "tag"),
        key="tag_create_color",
    )
    if c3.button("Add tag", key="tag_create_save"):
        try:
            catalog, _tag, created = _ensure_new(svc, new_label, new_color)
            if created:
                st.success("Tag created")
                st.rerun()
            else:
                st.info("That slug already exists.")
        except TagError as exc:
            st.error(str(exc))

    if not catalog.tags:
        st.info("No tags yet. Create one here, or type tags on a page / notebook.")
        return

    st.divider()
    st.markdown("#### Catalogue")
    for tag in catalog.tags:
        nb_n = usage.notebooks.get(tag.slug, 0)
        pg_n = usage.pages.get(tag.slug, 0)
        with st.expander(f"{tag.label}  ·  `{tag.slug}`  ·  {nb_n} notebooks, {pg_n} pages"):
            render_tag_chips([tag.slug], catalog)
            e1, e2 = st.columns([3, 1])
            label_val = e1.text_input(
                "Label",
                value=tag.label,
                key=f"tag_label_{tag.tag_id}",
            )
            color_val = e2.color_picker(
                "Colour",
                value=tag.color if tag.color.startswith("#") else "#1d76db",
                key=f"tag_color_{tag.tag_id}",
            )
            b1, b2, b3 = st.columns(3)
            if b1.button("Save label / colour", key=f"tag_save_{tag.tag_id}"):
                try:
                    if label_val.strip() != tag.label:
                        svc.rename_label(tag.tag_id, label_val)
                    if color_val.lower() != tag.color.lower():
                        svc.recolor(tag.tag_id, color_val)
                    st.success("Saved")
                    st.rerun()
                except (TagError, ValueError) as exc:
                    st.error(str(exc))
            slug_in = st.text_input(
                "Change slug (rewrites assignments)",
                value=tag.slug,
                key=f"tag_slug_{tag.tag_id}",
            )
            if b2.button("Change slug", key=f"tag_slug_go_{tag.tag_id}"):
                if slug_in.strip().lower() == tag.slug:
                    st.info("Slug unchanged.")
                else:
                    try:
                        _, result = svc.change_slug(tag.tag_id, slug_in)
                        skipped = len(result.skipped_roots)
                        st.success(
                            f"Updated {result.updated_notebooks} notebook(s)"
                            + (f"; skipped {skipped} locked" if skipped else "")
                        )
                        st.rerun()
                    except TagError as exc:
                        st.error(str(exc))
            others = [t for t in catalog.tags if t.tag_id != tag.tag_id]
            if others:
                merge_choices = {f"{t.label} ({t.slug})": t.tag_id for t in others}
                merge_label = st.selectbox(
                    "Merge into",
                    options=list(merge_choices.keys()),
                    key=f"tag_merge_{tag.tag_id}",
                )
                if st.button("Merge", key=f"tag_merge_go_{tag.tag_id}", icon=ic.MERGE):
                    try:
                        _, result = svc.merge(tag.tag_id, merge_choices[str(merge_label)])
                        st.success(f"Merged. Updated {result.updated_notebooks} notebook(s).")
                        st.rerun()
                    except TagError as exc:
                        st.error(str(exc))
            confirm_key = f"tag_del_confirm_{tag.tag_id}"
            if st.session_state.get(confirm_key):
                st.warning("Delete this tag and strip it from all notebooks and pages?")
                d1, d2 = st.columns(2)
                if d1.button("Cancel", key=f"tag_del_no_{tag.tag_id}"):
                    st.session_state[confirm_key] = False
                    st.rerun()
                if d2.button("Delete permanently", key=f"tag_del_yes_{tag.tag_id}"):
                    try:
                        _, result = svc.delete(tag.tag_id)
                        st.session_state[confirm_key] = False
                        st.success(f"Deleted. Updated {result.updated_notebooks} notebook(s).")
                        st.rerun()
                    except TagError as exc:
                        st.error(str(exc))
            elif b3.button("Delete", key=f"tag_del_{tag.tag_id}"):
                st.session_state[confirm_key] = True
                st.rerun()


def _ensure_new(svc: TagService, label: str, color: str):
    from transcribe.tagging.kernel import ensure_tag

    loaded = svc.store.load()
    now = svc.store.now_iso()
    try:
        parse_hex_color(color)
    except ValueError as exc:
        raise TagError(str(exc)) from exc
    catalog, tag, created = ensure_tag(
        loaded.catalog,
        label,
        new_id=svc.ids.new_id,
        now_iso=now,
        color=color,
        label=label.strip() or None,
    )
    if created:
        svc.store.save(catalog)
    return catalog, tag, created
