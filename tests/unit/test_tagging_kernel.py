"""Host-agnostic tagging kernel."""

from __future__ import annotations

import pytest

from transcribe.tagging.colors import contrast_text_color, default_color_for_slug, parse_hex_color
from transcribe.tagging.kernel import (
    TagCatalog,
    TagError,
    apply_rewrite,
    change_slug,
    constrain_entries,
    delete_tag,
    display_tag,
    ensure_tag,
    filter_ids,
    merge_tags,
    normalize_slug,
    normalize_slugs,
    recolor,
    rename_label,
    snapshot_for_slugs,
)


def _ids():
    n = {"i": 0}

    def new_id() -> str:
        n["i"] += 1
        return f"tid{n['i']:04d}"

    return new_id


def test_normalize_slug_and_slugs_match_legacy_rules():
    assert normalize_slug(" Poetry ") == "poetry"
    assert normalize_slugs([" Dream ", "DREAM", "note", ""]) == ["dream", "note"]


def test_ensure_rename_label_does_not_change_slug():
    catalog, tag, created = ensure_tag(
        TagCatalog(), "Poetry", new_id=_ids(), now_iso="t1", color="#1d76db"
    )
    assert created is True
    assert tag.slug == "poetry"
    assert tag.label == "Poetry"
    renamed = rename_label(catalog, tag.tag_id, "Poems", now_iso="t2")
    kept = renamed.get_by_id(tag.tag_id)
    assert kept is not None
    assert kept.slug == "poetry"
    assert kept.label == "Poems"
    assert apply_rewrite(
        ["poetry"], change_slug(renamed, tag.tag_id, "poetry", now_iso="t3")[1]
    ) == ["poetry"]


def test_change_slug_and_merge_rewrite_plans():
    ids = _ids()
    catalog, a, _ = ensure_tag(TagCatalog(), "poety", new_id=ids, now_iso="t1")
    catalog, b, _ = ensure_tag(catalog, "poetry", new_id=ids, now_iso="t2")
    catalog, plan = merge_tags(catalog, a.tag_id, b.tag_id, now_iso="t3")
    assert plan.mapping == {"poety": "poetry"}
    assert catalog.get_by_slug("poety") is None
    assert apply_rewrite(["poety", "travel"], plan) == ["poetry", "travel"]
    assert apply_rewrite(["poetry", "poety"], plan) == ["poetry"]

    catalog, c, _ = ensure_tag(TagCatalog(), "lists", new_id=ids, now_iso="t4")
    catalog, plan2 = change_slug(catalog, c.tag_id, "todo lists", now_iso="t5")
    assert plan2.mapping == {"lists": "todo lists"}
    assert catalog.get_by_slug("todo lists") is not None


def test_delete_strips_assignments():
    ids = _ids()
    catalog, tag, _ = ensure_tag(TagCatalog(), "tmp", new_id=ids, now_iso="t1")
    catalog, plan = delete_tag(catalog, tag.tag_id, now_iso="t2")
    assert plan.mapping == {"tmp": None}
    assert apply_rewrite(["tmp", "keep"], plan) == ["keep"]
    assert catalog.tags == []


def test_filter_ids_and_constrain_entries():
    items = [
        ("p1", ["poetry", "travel"]),
        ("p2", ["travel"]),
        ("p3", ["poetry"]),
    ]
    assert filter_ids(items, ["poetry"]) == ["p1", "p3"]
    assert filter_ids(items, ["poetry", "travel"]) == ["p1"]
    assert filter_ids(items, ["poetry"], mode="or") == ["p1", "p3"]
    assert filter_ids(items, []) == ["p1", "p2", "p3"]
    entries = [
        {"page_id": "p1", "project_root": "/a"},
        {"page_id": "p2", "project_root": "/a"},
        {"page_id": "p3", "project_root": "/a"},
    ]
    tags = {"p1": ["poetry"], "p2": ["lists"], "p3": ["poetry", "lists"]}
    assert [e["page_id"] for e in constrain_entries(entries, tags, ["poetry"])] == ["p1", "p3"]
    assert constrain_entries(entries, tags, []) == entries


def test_constrain_entries_and_order_and_missing_tags():
    """Viewer AND filter preserves entry order; missing tag map → empty slugs."""
    entries = [
        {"page_id": "p3", "project_root": "/b"},
        {"page_id": "p1", "project_root": "/a"},
        {"page_id": "p2", "project_root": "/a"},
        {"page_id": "orphan", "project_root": "/a"},
    ]
    tags = {
        "p1": ["poetry", "travel"],
        "p2": ["travel"],
        "p3": ["poetry", "lists"],
    }
    multi = constrain_entries(entries, tags, ["poetry", "lists"])
    assert [e["page_id"] for e in multi] == ["p3"]
    both = constrain_entries(entries, tags, ["poetry", "travel"])
    assert [e["page_id"] for e in both] == ["p1"]
    none = constrain_entries(entries, tags, ["missing"])
    assert none == []
    # orphan has no tags entry → treated as untagged
    assert constrain_entries(entries, tags, ["poetry"]) == [
        {"page_id": "p3", "project_root": "/b"},
        {"page_id": "p1", "project_root": "/a"},
    ]
    assert constrain_entries([], tags, ["poetry"]) == []
    assert constrain_entries(entries, {}, ["poetry"]) == []


def test_default_color_stable_and_orphan_display():
    a = default_color_for_slug("poetry")
    b = default_color_for_slug("poetry")
    assert a == b
    assert a.startswith("#") and len(a) == 7
    orphan = display_tag(TagCatalog(), "poetry")
    assert orphan.slug == "poetry"
    assert orphan.tag_id == ""
    assert orphan.color == a
    assert contrast_text_color("#fbca04") == "#111111"
    assert contrast_text_color("#1d76db") == "#ffffff"
    with pytest.raises(ValueError):
        parse_hex_color("blue")


def test_snapshot_for_slugs_includes_orphans():
    ids = _ids()
    catalog, tag, _ = ensure_tag(TagCatalog(), "Poetry", new_id=ids, now_iso="t1")
    rows = snapshot_for_slugs(catalog, ["poetry", "unknown"])
    slugs = [r["slug"] for r in rows]
    assert slugs == ["poetry", "unknown"]
    assert rows[0]["tag_id"] == tag.tag_id
    assert rows[1]["tag_id"] == ""


def test_recolor_and_duplicate_slug_rejected():
    ids = _ids()
    catalog, tag, _ = ensure_tag(TagCatalog(), "a", new_id=ids, now_iso="t1", color="#111111")
    catalog, _other, _ = ensure_tag(catalog, "b", new_id=ids, now_iso="t2")
    catalog = recolor(catalog, tag.tag_id, "#00ff00", now_iso="t3")
    assert catalog.get_by_id(tag.tag_id).color == "#00ff00"
    with pytest.raises(TagError):
        change_slug(catalog, tag.tag_id, "b", now_iso="t4")
    with pytest.raises(TagError):
        merge_tags(catalog, tag.tag_id, tag.tag_id, now_iso="t5")
    with pytest.raises(TagError):
        ensure_tag(catalog, "   ", new_id=ids, now_iso="t6")
