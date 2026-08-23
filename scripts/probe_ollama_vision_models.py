#!/usr/bin/env python3
"""Live OCR probe for installed Ollama vision models (developer tool).

Runs a short generate on ``tests/fixtures/mini_page.png`` with the same prompt
lanes Transcribe uses at job start (faithful_markdown or model recipe).

Usage (from repo root)::

    PYTHONPATH=src python scripts/probe_ollama_vision_models.py
    PYTHONPATH=src python scripts/probe_ollama_vision_models.py --json .test_outputs/model_probe_results.json

Requires a running Ollama daemon. Not part of the default offline pytest suite.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from transcribe.providers.ollama import OllamaVisionProvider, ollama_healthcheck
from transcribe.prompts import REGISTRY
from transcribe.services.model_advice import advise_model
from transcribe.services.ocr_model_recipes import recipe_for_model, recipe_prompt


def _default_fixture() -> Path:
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "mini_page.png"


def probe_models(
    *,
    base_url: str,
    fixture: Path,
    request_timeout: float = 180.0,
) -> list[dict[str, object]]:
    if not ollama_healthcheck(base_url):
        raise SystemExit(f"Ollama not reachable at {base_url}")
    if not fixture.is_file():
        raise SystemExit(f"Fixture not found: {fixture}")

    image_bytes = fixture.read_bytes()
    provider = OllamaVisionProvider(base_url, request_timeout=request_timeout)
    all_models, _ = provider._discover_uncached()
    vision = [
        m
        for m in all_models
        if m.capability_known and "vision" in {c.lower() for c in m.capabilities}
    ]
    by_name = {m.name: m for m in all_models}
    targets = list(vision)
    for extra in ("deepseek-ocr:latest",):
        if extra in by_name and extra not in {m.name for m in targets}:
            targets.append(by_name[extra])

    faithful = REGISTRY["faithful_markdown"].body
    results: list[dict[str, object]] = []
    for index, model in enumerate(targets, 1):
        name = model.name
        recipe = recipe_for_model(name)
        prompt = recipe_prompt(recipe)[2] if recipe else faithful
        row: dict[str, object] = {
            "model": name,
            "capabilities": list(model.capabilities),
            "family": model.family,
            "params": model.parameter_size,
            "advice_kind": advise_model(name, role="vision").kind,
            "prompt_id": recipe.prompt_id if recipe else "faithful_markdown",
        }
        print(f"[{index}/{len(targets)}] {name}", flush=True)
        t0 = time.monotonic()
        try:
            provider.probe_vision_model_load(model=name)
            row["load_probe"] = "ok"
        except Exception as exc:  # noqa: BLE001 — probe report
            row["load_probe"] = f"fail: {exc}"
        try:
            res = provider.transcribe_image(
                model=name,
                prompt=prompt,
                image_bytes=image_bytes,
                options={"temperature": 0.0, "num_predict": 512},
            )
            text = (res.text or "").strip()
            meta = res.provider_metadata or {}
            row["ocr_status"] = "empty" if not text else "ok"
            row["text_len"] = len(text)
            row["text_preview"] = text[:120].replace("\n", " ")
            row["eval_count"] = meta.get("eval_count")
            row["truncated"] = meta.get("truncated")
        except Exception as exc:  # noqa: BLE001 — probe report
            row["ocr_status"] = "error"
            row["error"] = str(exc)[:240]
        row["elapsed_s"] = round(time.monotonic() - t0, 1)
        results.append(row)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=_default_fixture(),
        help="PNG/JPEG page fixture (default: tests/fixtures/mini_page.png)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Write full JSON results to this path",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args(argv)

    results = probe_models(
        base_url=args.base_url,
        fixture=args.fixture,
        request_timeout=args.timeout,
    )
    print("\n=== SUMMARY ===")
    for row in results:
        print(
            f"{row['model']:<30} load={str(row.get('load_probe', '?'))[:12]:<12} "
            f"ocr={row.get('ocr_status', '?'):<5} len={row.get('text_len', 0):<4} "
            f"advice={row['advice_kind']}"
        )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")
    bad = [
        r
        for r in results
        if r.get("load_probe") != "ok" or r.get("ocr_status") in {"empty", "error"}
    ]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
