"""Settings → Detection: catalogue and custom detector editor."""

from __future__ import annotations

import streamlit as st

from transcribe.detection.api import DetectionService
from transcribe.detection.custom import (
    CustomDetectorDefinition,
    compile_custom_detector,
)
from transcribe.detection.registry import list_all_detectors


@st.fragment
def render_detection_settings_panel() -> None:
    st.subheader("Detection")
    st.caption("Built-in and custom detectors. Run from View → Detect after selecting a notebook.")

    dets = list_all_detectors()
    from transcribe.services.tags import TagService

    tag_svc = TagService()
    st.markdown("#### Auto-tag pages")
    st.caption(
        "When enabled, a successful Detect run (or Apply from findings) adds the "
        "detector’s tag to matching pages. This does not change detection cache identity."
    )
    for d in dets:
        key = f"detect_auto_tag_default_{d.detector_id.replace('/', '_')}"
        current = tag_svc.auto_tag_enabled(d.detector_id)
        checked = st.checkbox(
            f"{d.title} (`{d.finding_type}`)",
            value=current,
            key=key,
        )
        if checked != current:
            tag_svc.set_auto_tag(d.detector_id, checked)

    st.divider()
    st.markdown("#### Detectors")
    for d in dets:
        st.markdown(f"- **{d.title}** (`{d.detector_id}` v{d.version}) — {d.description[:120]}")

    st.divider()
    st.markdown("#### Custom detector")
    with st.form("custom_detector_form"):
        name = st.text_input("Name", value="Dreams")
        instruction = st.text_area(
            "Instruction",
            value="Find pages describing dreams. Include adjacent-page spans. "
            "Ignore metaphorical uses of dream.",
            height=120,
        )
        scope = st.selectbox("Scope", ["notebook", "page"])
        adjacent = st.checkbox("Adjacent-page detection", value=True)
        auto_tag_custom = st.checkbox(
            "Auto-tag matching pages by default",
            value=False,
            help="After Detect runs this detector, tag spanned pages with the finding type.",
        )
        model_mode = st.selectbox("Model mode", ["auto", "text", "vision"])
        threshold = st.slider("Confidence threshold", 0.0, 1.0, 0.7, 0.05)
        submitted = st.form_submit_button("Save custom detector", type="primary")
        if submitted:
            custom = CustomDetectorDefinition(
                name=name,
                instruction=instruction,
                scope=scope,
                adjacent_page_detection=adjacent,
                model_mode=model_mode,
                confidence_threshold=threshold,
            )
            preview = compile_custom_detector(custom)
            if preview is None:
                st.error("Invalid custom detector (check instruction length).")
            else:
                DetectionService.register_custom_detector(custom)
                if auto_tag_custom:
                    TagService().set_auto_tag(preview.detector_id, True)
                st.success(f"Saved `{preview.detector_id}`")
                st.json(
                    {
                        "detector_id": preview.detector_id,
                        "prompt_ref": preview.prompt_ref.as_dict(),
                        "scope": preview.scope.value,
                        "window_size": preview.window_size,
                    }
                )

    customs = DetectionService.list_custom_detector_defs()
    if customs:
        st.markdown("#### Saved custom detectors")
        for row in customs:
            cid = row.get("custom_id") or row.get("name")
            c1, c2 = st.columns([4, 1])
            c1.write(f"**{row.get('name')}** (`custom/{cid}`)")
            if c2.button("Delete", key=f"del_custom_{cid}"):
                DetectionService.delete_custom_detector(str(cid))
                st.rerun()
