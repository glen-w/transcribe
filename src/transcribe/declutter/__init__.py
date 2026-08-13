"""Visual declutter for human-facing scan cleanup (import-time; not OCR preprocess)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from io import BytesIO
from typing import Any, Literal

from PIL import Image

from transcribe.declutter.borders import (
    SCAN_BORDER_PARAMS,
    UNIFORM_OVERSCAN_PARAMS,
    ScanBorderParams,
    UniformOverscanParams,
    detect_declutter_border_insets,
    detect_scan_border_insets,
)
from transcribe.domain.fingerprint import canonical_json_bytes

# v2: add remove_uniform_overscan (stark white gutters) + multi-pass combine.
DECLUTTER_VERSION = 2

DECLUTTER_STATES = frozenset(
    {"disabled", "enabled_noop", "enabled_cropped", "error_fallback"}
)

DeclutterState = Literal[
    "disabled", "enabled_noop", "enabled_cropped", "error_fallback"
]

ENABLED_OPS: tuple[str, ...] = ("remove_scan_borders", "remove_uniform_overscan")

NOTE_MAX_LEN = 200


@dataclass(frozen=True)
class DeclutterResult:
    image_bytes: bytes
    state: DeclutterState
    version: int
    ops: tuple[str, ...]
    params: dict[str, Any]
    identity_sha256: str
    original_width: int
    original_height: int
    crop_left: int
    crop_top: int
    crop_right: int
    crop_bottom: int
    inset_left: int
    inset_top: int
    inset_right: int
    inset_bottom: int
    note: str

    @property
    def width(self) -> int:
        return self.crop_right - self.crop_left

    @property
    def height(self) -> int:
        return self.crop_bottom - self.crop_top

    def provenance_dict(self) -> dict[str, Any]:
        return {
            "declutter_state": self.state,
            "declutter_version": self.version,
            "declutter_ops": list(self.ops),
            "declutter_identity_sha256": self.identity_sha256,
            "declutter_params": self.params,
            "declutter_original_width": self.original_width,
            "declutter_original_height": self.original_height,
            "declutter_crop_left": self.crop_left,
            "declutter_crop_top": self.crop_top,
            "declutter_crop_right": self.crop_right,
            "declutter_crop_bottom": self.crop_bottom,
            "declutter_inset_left": self.inset_left,
            "declutter_inset_top": self.inset_top,
            "declutter_inset_right": self.inset_right,
            "declutter_inset_bottom": self.inset_bottom,
            "declutter_note": self.note,
        }


def _bound_note(note: str) -> str:
    note = note.strip()
    if len(note) <= NOTE_MAX_LEN:
        return note
    return note[: NOTE_MAX_LEN - 1] + "…"


def _default_params_block() -> dict[str, Any]:
    return {
        "remove_scan_borders": asdict(SCAN_BORDER_PARAMS),
        "remove_uniform_overscan": asdict(UNIFORM_OVERSCAN_PARAMS),
    }


def identity_payload(
    *,
    enabled: bool,
    version: int = DECLUTTER_VERSION,
    ops: tuple[str, ...] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not enabled:
        return {
            "visual_declutter_enabled": False,
            "declutter_version": version,
            "ops": [],
            "params": {},
        }
    return {
        "visual_declutter_enabled": True,
        "declutter_version": version,
        "ops": list(ops if ops is not None else ENABLED_OPS),
        "params": params if params is not None else _default_params_block(),
    }


def identity_sha256_for(*, enabled: bool) -> str:
    return sha256(canonical_json_bytes(identity_payload(enabled=enabled))).hexdigest()


def _full_frame_geometry(width: int, height: int) -> dict[str, int]:
    return {
        "original_width": width,
        "original_height": height,
        "crop_left": 0,
        "crop_top": 0,
        "crop_right": width,
        "crop_bottom": height,
        "inset_left": 0,
        "inset_top": 0,
        "inset_right": 0,
        "inset_bottom": 0,
    }


def _png_size(image_bytes: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(image_bytes)) as image:
        return int(image.size[0]), int(image.size[1])


def encode_declutter_png(image: Image.Image) -> bytes:
    """Deterministic PNG bytes for successful crops."""
    work = image
    if work.mode == "P":
        work = work.convert("RGB")
    elif work.mode not in ("L", "RGB", "RGBA"):
        work = work.convert("RGB")
    # Pixel-only copy strips EXIF/ICC/text info for stable SHA
    clean = Image.frombytes(work.mode, work.size, work.tobytes())
    out = BytesIO()
    clean.save(out, format="PNG", optimize=False, compress_level=6)
    return out.getvalue()


def apply_declutter(image_bytes: bytes, *, enabled: bool) -> DeclutterResult:
    """Apply visual declutter. Never raises; fail-safe returns exact input bytes."""
    try:
        return _apply_declutter_inner(image_bytes, enabled=enabled)
    except Exception as exc:  # noqa: BLE001 — ingest must never fail on declutter
        try:
            width, height = _png_size(image_bytes)
        except Exception:  # noqa: BLE001
            width, height = 0, 0
        geo = _full_frame_geometry(width, height)
        payload = identity_payload(enabled=enabled)
        return DeclutterResult(
            image_bytes=image_bytes,
            state="error_fallback",
            version=DECLUTTER_VERSION,
            ops=tuple(payload["ops"]),
            params=dict(payload["params"]),
            identity_sha256=sha256(canonical_json_bytes(payload)).hexdigest(),
            note=_bound_note(f"{type(exc).__name__}: {exc}"),
            **geo,
        )


def _apply_declutter_inner(image_bytes: bytes, *, enabled: bool) -> DeclutterResult:
    width, height = _png_size(image_bytes)
    geo = _full_frame_geometry(width, height)
    payload = identity_payload(enabled=enabled)
    ident = sha256(canonical_json_bytes(payload)).hexdigest()

    if not enabled:
        return DeclutterResult(
            image_bytes=image_bytes,
            state="disabled",
            version=DECLUTTER_VERSION,
            ops=(),
            params={},
            identity_sha256=ident,
            note="",
            **geo,
        )

    params_block = _default_params_block()
    payload = identity_payload(enabled=True, params=params_block)
    ident = sha256(canonical_json_bytes(payload)).hexdigest()

    with Image.open(BytesIO(image_bytes)) as src:
        src.load()
        mode = src.mode
        if mode == "P":
            color = src.convert("RGB")
        elif mode in ("L", "RGB", "RGBA"):
            color = src.copy()
        else:
            color = src.convert("RGB")

        gray = color.convert("L")
        insets, reason = detect_declutter_border_insets(
            gray,
            scan_params=SCAN_BORDER_PARAMS,
            overscan_params=UNIFORM_OVERSCAN_PARAMS,
        )
        if insets is None:
            return DeclutterResult(
                image_bytes=image_bytes,
                state="enabled_noop",
                version=DECLUTTER_VERSION,
                ops=ENABLED_OPS,
                params=params_block,
                identity_sha256=ident,
                note=_bound_note(reason or "noop"),
                **geo,
            )

        left, top, right_inset, bottom_inset = insets
        crop_left = left
        crop_top = top
        crop_right = width - right_inset
        crop_bottom = height - bottom_inset
        cropped = color.crop((crop_left, crop_top, crop_right, crop_bottom))
        out_bytes = encode_declutter_png(cropped)
        return DeclutterResult(
            image_bytes=out_bytes,
            state="enabled_cropped",
            version=DECLUTTER_VERSION,
            ops=ENABLED_OPS,
            params=params_block,
            identity_sha256=ident,
            original_width=width,
            original_height=height,
            crop_left=crop_left,
            crop_top=crop_top,
            crop_right=crop_right,
            crop_bottom=crop_bottom,
            inset_left=left,
            inset_top=top,
            inset_right=right_inset,
            inset_bottom=bottom_inset,
            note="",
        )


def journal_matches_identity(
    journal: dict[str, Any], *, enabled: bool
) -> bool:
    """True when journal may be finished under the current effective declutter setting.

    - Missing ``declutter_identity_sha256``: legacy journal; allow finish (pixels were
      already staged coherently without declutter identity bookkeeping).
    - Present: must equal the current effective identity; otherwise discard.
    """
    recorded = journal.get("declutter_identity_sha256")
    if recorded is None:
        return True
    return recorded == identity_sha256_for(enabled=enabled)


__all__ = [
    "DECLUTTER_VERSION",
    "DECLUTTER_STATES",
    "ENABLED_OPS",
    "SCAN_BORDER_PARAMS",
    "UNIFORM_OVERSCAN_PARAMS",
    "ScanBorderParams",
    "UniformOverscanParams",
    "DeclutterResult",
    "DeclutterState",
    "apply_declutter",
    "encode_declutter_png",
    "identity_payload",
    "identity_sha256_for",
    "journal_matches_identity",
    "detect_scan_border_insets",
    "detect_declutter_border_insets",
]
