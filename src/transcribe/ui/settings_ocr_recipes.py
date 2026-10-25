"""Settings → Models: OCR model recipe overlay editor."""

from __future__ import annotations

import json

import streamlit as st

from transcribe.config.errors import OCR_RECIPES_INVALID, ConfigError
from transcribe.prompts import REGISTRY as OCR_REGISTRY
from transcribe.services.ocr_model_recipe_store import (
    known_ocr_prompt_ids,
    load_recipes,
    recipes_path,
    remove_overlay_row,
    reset_overlay,
    set_recipe_enabled,
    upsert_overlay_row,
)
from transcribe.services.ocr_model_recipes import (
    ADVICE_KINDS,
    MATCH_MODES,
    OcrModelRecipe,
)
from transcribe.ui import icons as ic
from transcribe.ui.components.info_tooltip import widget_help


def _options_summary(recipe: OcrModelRecipe) -> str:
    if not recipe.generation_options:
        return "—"
    keys = ", ".join(sorted(recipe.generation_options))
    return keys


def _match_summary(recipe: OcrModelRecipe) -> str:
    mode = recipe.match_mode or "any"
    tokens = ", ".join(recipe.match_tokens) or "—"
    extra = ""
    if recipe.exclude_tokens:
        extra = f" · exclude {', '.join(recipe.exclude_tokens)}"
    return f"{mode}: {tokens}{extra}"


def render_ocr_recipes_section() -> None:
    st.markdown("#### OCR model recipes")
    st.caption(
        "Per-tag prompt freeze and generation-option overlay applied at job start. "
        "Changing options changes the next job’s skip fingerprint. "
        "A custom notebook prompt still wins prompt text. "
        f"Stored at `{recipes_path()}`."
    )
    loaded = load_recipes()
    if loaded.error_code:
        st.error(f"{loaded.error_code}: {loaded.error_message}")
        st.caption(
            "Jobs are using builtin recipes until this file is replaced. "
            "Reset overlay writes an empty valid file (builtins only)."
        )
        if st.button(
            "Reset overlay (builtins only)",
            key="ocr_recipes_reset_corrupt",
            icon=ic.RESET,
        ):
            try:
                reset_overlay()
                st.success("Wrote an empty overlay.")
                st.rerun()
            except ConfigError as exc:
                st.error(f"{exc.code}: {exc}")
        return

    if not loaded.effective:
        st.info("No recipes.")
        return

    for recipe in loaded.effective:
        cols = st.columns([2.2, 2.6, 1.1, 1.4, 0.9, 0.8])
        cols[0].markdown(f"**{recipe.title}**  \n`{recipe.recipe_id}` · {recipe.source}")
        cols[1].caption(_match_summary(recipe))
        freeze_label = "freeze prompt" if recipe.freeze_prompt else "options only"
        cols[2].caption(f"{freeze_label}  \n`{recipe.prompt_id}`")
        cols[3].caption(_options_summary(recipe))
        enabled_key = f"ocr_recipe_enabled_{recipe.recipe_id}"
        checked = cols[4].checkbox(
            "On",
            value=recipe.enabled,
            key=enabled_key,
            help=widget_help(
                "Enabled recipes match first-to-last at job start. "
                "Disable to drop a builtin lane without editing Python."
            ),
        )
        if checked != recipe.enabled:
            try:
                set_recipe_enabled(recipe.recipe_id, checked)
                st.rerun()
            except ConfigError as exc:
                st.error(f"{exc.code}: {exc}")
        if recipe.source == "custom":
            if cols[5].button(
                "Remove",
                key=f"ocr_recipe_remove_{recipe.recipe_id}",
                icon=ic.DELETE,
            ):
                try:
                    remove_overlay_row(recipe.recipe_id)
                    st.rerun()
                except ConfigError as exc:
                    st.error(f"{exc.code}: {exc}")
        elif recipe.source == "override":
            if cols[5].button(
                "Revert",
                key=f"ocr_recipe_revert_{recipe.recipe_id}",
                icon=ic.UNDO,
            ):
                try:
                    remove_overlay_row(recipe.recipe_id)
                    st.rerun()
                except ConfigError as exc:
                    st.error(f"{exc.code}: {exc}")
        else:
            cols[5].caption("")

    prompt_ids = sorted(known_ocr_prompt_ids()) or sorted(OCR_REGISTRY)
    with st.expander("Add or edit recipe overlay"):
        st.caption(
            "Same recipe_id overlays a builtin. A new id is a custom lane. "
            "User rows are tried before remaining builtins."
        )
        existing_ids = [r.recipe_id for r in loaded.effective]
        pick = st.selectbox(
            "Existing recipe",
            options=["(new)"] + existing_ids,
            key="ocr_recipe_edit_pick",
        )
        selected = next((r for r in loaded.effective if r.recipe_id == pick), None)
        default_id = selected.recipe_id if selected else ""
        default_title = selected.title if selected else ""
        default_tokens = ", ".join(selected.match_tokens) if selected else ""
        default_exclude = ", ".join(selected.exclude_tokens) if selected else ""
        default_mode = selected.match_mode if selected else "any"
        default_prompt = (
            selected.prompt_id
            if selected and selected.prompt_id in prompt_ids
            else (prompt_ids[0] if prompt_ids else "faithful_markdown")
        )
        default_freeze = selected.freeze_prompt if selected else True
        default_kind = selected.advice_kind if selected else "ocr_oriented"
        default_enabled = selected.enabled if selected else True
        default_warnings = "\n".join(selected.warnings) if selected else ""
        default_opts = (
            json.dumps(selected.generation_options, indent=2)
            if selected and selected.generation_options
            else "{\n  \"repeat_penalty\": 1.2,\n  \"stop\": [\"```\\n```\"]\n}"
        )
        with st.form("ocr_recipe_overlay_form"):
            recipe_id = st.text_input("recipe_id", value=default_id)
            title = st.text_input("Title", value=default_title)
            match_tokens = st.text_input(
                "Match tokens (comma-separated substrings)",
                value=default_tokens,
            )
            match_mode = st.selectbox(
                "Match mode",
                options=sorted(MATCH_MODES),
                index=sorted(MATCH_MODES).index(default_mode)
                if default_mode in MATCH_MODES
                else 0,
            )
            exclude_tokens = st.text_input(
                "Exclude tokens (comma-separated)",
                value=default_exclude,
            )
            prompt_id = st.selectbox(
                "OCR prompt",
                options=prompt_ids,
                index=prompt_ids.index(default_prompt)
                if default_prompt in prompt_ids
                else 0,
            )
            freeze_prompt = st.checkbox(
                "Freeze this prompt (otherwise options-only)",
                value=default_freeze,
            )
            advice_kind = st.selectbox(
                "Advice kind",
                options=sorted(ADVICE_KINDS),
                index=sorted(ADVICE_KINDS).index(default_kind)
                if default_kind in ADVICE_KINDS
                else 0,
            )
            enabled = st.checkbox("Enabled", value=default_enabled)
            warnings = st.text_area("Warnings (one per line)", value=default_warnings)
            options_text = st.text_area(
                "Generation options JSON",
                value=default_opts,
                help=widget_help(
                    "Allowed keys: repeat_penalty, stop, temperature, num_predict. "
                    "Set a key to null to drop it from a builtin overlay."
                ),
            )
            submitted = st.form_submit_button(
                "Save recipe overlay", type="primary", icon=ic.SAVE
            )
            if submitted:
                try:
                    try:
                        raw_opts = json.loads(options_text or "{}")
                    except json.JSONDecodeError as exc:
                        raise ConfigError(
                            OCR_RECIPES_INVALID, f"generation options JSON: {exc}"
                        ) from exc
                    tokens = [t.strip() for t in match_tokens.split(",") if t.strip()]
                    excludes = [t.strip() for t in exclude_tokens.split(",") if t.strip()]
                    warning_list = [w.strip() for w in warnings.splitlines() if w.strip()]
                    row = {
                        "recipe_id": recipe_id.strip(),
                        "title": title.strip(),
                        "match_tokens": tokens,
                        "match_mode": match_mode,
                        "exclude_tokens": excludes,
                        "prompt_id": prompt_id,
                        "freeze_prompt": bool(freeze_prompt),
                        "generation_options": raw_opts,
                        "warnings": warning_list,
                        "advice_kind": advice_kind,
                        "enabled": bool(enabled),
                    }
                    upsert_overlay_row(row)
                    st.success(f"Saved `{row['recipe_id']}`.")
                    st.rerun()
                except ConfigError as exc:
                    st.error(f"{exc.code}: {exc}")
