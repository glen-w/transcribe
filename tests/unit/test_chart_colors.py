"""Chart colour palettes for analysis View bar charts."""

from __future__ import annotations

from transcribe.ui.chart_colors import (
    DEFAULT_EMOTION_COLORS,
    DEFAULT_SENTIMENT_COLORS,
    color_for_label,
    sanitise_chart_colors,
)


def test_sanitise_chart_colors_defaults_when_empty() -> None:
    out = sanitise_chart_colors(None)
    assert out["sentiment"] == DEFAULT_SENTIMENT_COLORS
    assert out["emotion"] == DEFAULT_EMOTION_COLORS


def test_sanitise_chart_colors_merges_valid_overrides() -> None:
    out = sanitise_chart_colors(
        {
            "sentiment": {"negative": "#ff0000", "bogus": "#123456"},
            "emotion": {"joy": "2f8f4e", "anger": "not-a-color"},
        }
    )
    assert out["sentiment"]["negative"] == "#ff0000"
    assert out["sentiment"]["neutral"] == DEFAULT_SENTIMENT_COLORS["neutral"]
    assert out["emotion"]["joy"] == "#2f8f4e"
    assert out["emotion"]["anger"] == DEFAULT_EMOTION_COLORS["anger"]


def test_color_for_label_casefold() -> None:
    palette = {"joy": "#2f8f4e"}
    assert color_for_label("Joy", palette) == "#2f8f4e"
    assert color_for_label("sadness", palette) == "#888888"


def test_chart_color_defaults_do_not_import_streamlit() -> None:
    """Config/OCR must read palettes without pulling Streamlit into the process."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    script = """
import sys
from transcribe.config.models import ChartColorsConfig
from transcribe.ui.chart_colors import sanitise_chart_colors

ChartColorsConfig.from_dict({"sentiment": {"positive": "#2f8f4e"}})
sanitise_chart_colors(None)
leaked = [name for name in sys.modules if name == "streamlit" or name.startswith("streamlit.")]
assert not leaked, leaked
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
