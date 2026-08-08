"""Load repo-root ``.env`` before path/config resolution.

Does not override variables already set in the process environment (shell /
Compose win over ``.env``). Avoids a ``python-dotenv`` dependency.
"""

from __future__ import annotations

from pathlib import Path

_bootstrapped = False


def _parse_env_line(line: str) -> tuple[str, str] | None:
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    if text.startswith("export "):
        text = text[len("export ") :].strip()
    if "=" not in text:
        return None
    key, _, value = text.partition("=")
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return key, value


def load_dotenv(env_path: Path) -> None:
    """Set missing keys from a dotenv-style file."""
    import os

    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if key not in os.environ:
            os.environ[key] = value


def bootstrap(env_path: Path | None = None) -> None:
    """Load ``.env`` from the repo root (or ``env_path``) once."""
    global _bootstrapped
    if _bootstrapped:
        return
    _bootstrapped = True
    if env_path is None:
        # src/transcribe/_bootstrap.py → repo root
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(env_path)
