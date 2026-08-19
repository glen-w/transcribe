"""Icon constants are valid Material tokens for Streamlit."""

from __future__ import annotations

import transcribe.ui.icons as icons


def _material_names() -> list[str]:
    names: list[str] = []
    for name in dir(icons):
        if name.startswith("_"):
            continue
        value = getattr(icons, name)
        if isinstance(value, str) and value.startswith(":material/"):
            names.append(value)
        elif isinstance(value, tuple):
            names.extend(v for v in value if v.startswith(":material/"))
    return names


def test_icon_constants_are_material_tokens():
    for token in _material_names():
        assert token.startswith(":material/")
        assert token.endswith(":")


def test_use_variant_has_three_entries():
    assert len(icons.USE_VARIANT) == 3
