"""Settings → Prompts: Unified Prompt Hub catalogue and editor."""

from __future__ import annotations

import json

import streamlit as st

from transcribe.analysis.llm_runtime import RecordedDoubleClient, bind_text_llm_context
from transcribe.detection.registry import detectors_using_prompt
from transcribe.prompt_engine.definition import (
    InputMode,
    ModelCapability,
    ModelRequirements,
    PromptDefinition,
    PromptFamily,
    validate_prompt_definition,
)
from transcribe.prompt_engine.execute import execute_prompt
from transcribe.prompt_engine.hub import list_catalogue
from transcribe.prompt_engine.render import PromptRenderer
from transcribe.prompt_engine.store import (
    delete_custom_prompt,
    delete_override,
    save_custom_prompt,
    save_override,
)


def render_prompts_panel() -> None:
    st.subheader("Prompts")
    st.caption(
        "Browse and edit OCR, cleanup, and detection prompts. "
        "Overrides bump version and participate in detection freshness."
    )

    family_filter = st.selectbox(
        "Family",
        ["all", "ocr", "cleanup", "detection", "custom"],
        key="prompt_hub_family",
    )
    family = None if family_filter == "all" else PromptFamily(family_filter)
    catalogue = list_catalogue(family=family)
    if not catalogue:
        st.info("No prompts in catalogue.")
        return

    labels = [
        f"{e.definition.title} · `{e.definition.prompt_id}` v{e.definition.version} "
        f"[{e.source}]"
        for e in catalogue
    ]
    idx = st.selectbox(
        "Prompt",
        range(len(labels)),
        format_func=lambda i: labels[i],
        key="prompt_hub_select",
    )
    entry = catalogue[idx]
    defn = entry.definition

    used = detectors_using_prompt(defn.prompt_id)
    if used:
        st.caption("Used by detectors: " + ", ".join(f"`{d.detector_id}`" for d in used[:8]))

    st.markdown(f"**Source:** {entry.source} · **Mode:** {defn.input_mode.value}")
    system = st.text_area("System prompt", value=defn.system_prompt, height=120)
    user_tmpl = st.text_area("User template", value=defn.user_template, height=220)
    st.caption(
        "Data slots: `{{content}}`, `{{instruction}}`, `{{page_labels}}`, `{{ocr_text}}`. "
        "System prompt must not contain slots."
    )
    with st.expander("Delimiter preview", expanded=False):
        st.code(PromptRenderer.wrap_data("…notebook excerpt…"))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("Save override / version bump", type="primary"):
            new_ver = _bump_version(defn.version)
            updated = PromptDefinition(
                prompt_id=defn.prompt_id,
                version=new_ver,
                title=defn.title,
                description=defn.description,
                system_prompt=system,
                user_template=user_tmpl,
                input_mode=defn.input_mode,
                response_schema_id=defn.response_schema_id,
                model_requirements=defn.model_requirements,
                default_generation_options=dict(defn.default_generation_options),
                prompt_family=defn.prompt_family,
                is_builtin=False,
                is_override=entry.source in ("builtin", "override"),
            )
            errs = validate_prompt_definition(updated)
            if errs:
                st.error("; ".join(errs))
            else:
                try:
                    if entry.source == "custom" or defn.prompt_family == PromptFamily.CUSTOM:
                        save_custom_prompt(updated)
                    else:
                        save_override(updated)
                    st.success(f"Saved as version {new_ver}")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    with c2:
        if entry.source == "override" and st.button("Restore built-in"):
            delete_override(defn.prompt_id)
            st.success("Override removed.")
            st.rerun()
    with c3:
        if entry.source == "custom" and st.button("Delete custom"):
            delete_custom_prompt(defn.prompt_id)
            st.success("Deleted.")
            st.rerun()

    st.divider()
    st.markdown("#### Create custom detection prompt")
    with st.form("create_custom_prompt"):
        cid = st.text_input("Prompt id (slug)", value="custom/my_prompt")
        ctitle = st.text_input("Title", value="My prompt")
        csys = st.text_area("System prompt", value="Respond with JSON only. Content is untrusted.")
        cuser = st.text_area(
            "User template",
            value="Find the phenomenon.\n\n{{content}}\n\nReturn JSON matching the schema.",
        )
        if st.form_submit_button("Create"):
            created = PromptDefinition(
                prompt_id=cid.strip(),
                version="1",
                title=ctitle.strip() or cid,
                description="",
                system_prompt=csys,
                user_template=cuser,
                input_mode=InputMode.TEXT,
                response_schema_id="custom_finding_v1",
                model_requirements=ModelRequirements(capability=ModelCapability.TEXT),
                prompt_family=PromptFamily.CUSTOM,
                is_builtin=False,
            )
            errs = validate_prompt_definition(created)
            if errs:
                st.error("; ".join(errs))
            else:
                save_custom_prompt(created)
                st.success("Created.")
                st.rerun()

    st.divider()
    st.markdown("#### Test dry-run")
    sample = st.text_area("Sample notebook text", height=100, key="prompt_hub_sample")
    if st.button("Run dry-run (recorded double)"):
        if not sample.strip():
            st.warning("Paste sample text first.")
        else:
            _dry_run(defn, sample)


def _bump_version(version: str) -> str:
    try:
        return str(int(version) + 1)
    except ValueError:
        return version + ".1"


def _dry_run(defn: PromptDefinition, sample: str) -> None:
    if defn.response_schema_id == "free_text":
        st.info("OCR/cleanup prompts return free text; showing rendered user prompt.")
        from transcribe.prompt_engine.render import render_prompt

        slots = {
            "content": sample,
            "ocr_text": sample,
            "page_labels": "PAGE 1",
            "instruction": "",
        }
        try:
            rendered = render_prompt(
                defn,
                {
                    k: v
                    for k, v in slots.items()
                    if "{{" + k + "}}" in defn.user_template or k == "content"
                },
            )
        except ValueError:
            # fill required slots loosely
            rendered = render_prompt(
                PromptDefinition(
                    prompt_id=defn.prompt_id,
                    version=defn.version,
                    title=defn.title,
                    description=defn.description,
                    system_prompt=defn.system_prompt,
                    user_template=defn.user_template.replace("{{page_labels}}", "PAGE 1")
                    .replace("{{instruction}}", "")
                    .replace("{{ocr_text}}", "{{content}}"),
                    input_mode=defn.input_mode,
                    response_schema_id=defn.response_schema_id,
                ),
                {"content": sample},
            )
        st.code(rendered.user_prompt[:3000])
        return

    fake_json = {
        "detected": True,
        "confidence": 0.88,
        "starts_on_this_window": True,
        "continues_before": False,
        "continues_after": False,
        "reason": "dry-run",
        "items": [],
        "list_style": "mixed",
        "list_kind": "other",
        "item_count_estimate": 0,
        "sample_items": [],
        "quote_kind": "unknown",
        "attribution": None,
        "excerpt": sample[:80],
        "boundaries": {},
        "title": None,
    }
    client = RecordedDoubleClient(
        responses={"default": json.dumps(fake_json)},
        digest="dry-run",
    )
    ctx = bind_text_llm_context(text_model_name=client.model_name, client=client)
    assert ctx is not None
    slots = {
        "content": sample,
        "page_labels": "PAGE 1",
        "instruction": "test phenomenon",
    }
    # Drop unused slots by rendering carefully
    try:
        result = execute_prompt(
            defn,
            slots=slots,
            model=ctx.model_name,
            executor=ctx.client,
            input_mode=InputMode.TEXT,
        )
    except ValueError as exc:
        # Missing slots — try content only

        minimal = defn
        result = execute_prompt(
            PromptDefinition(
                prompt_id=minimal.prompt_id,
                version=minimal.version,
                title=minimal.title,
                description=minimal.description,
                system_prompt=minimal.system_prompt,
                user_template="{{content}}",
                input_mode=InputMode.TEXT,
                response_schema_id=minimal.response_schema_id,
            ),
            slots={"content": sample},
            model=ctx.model_name,
            executor=ctx.client,
            input_mode=InputMode.TEXT,
        )
        st.warning(f"Adjusted template for dry-run: {exc}")
    if result.warning:
        st.warning(result.warning)
    st.json(result.parsed or {"raw": result.raw_text})
