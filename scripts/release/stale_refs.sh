#!/usr/bin/env bash
# Stale packaging / identity / TODO comment gate. Uses git grep (no ripgrep required).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

fail=0

git_grep() {
  # git grep returns 1 when no matches; 0 when hits; >1 on error
  git grep -n -E "$@" || true
}

check_absent() {
  local label="$1"
  local pattern="$2"
  local hits
  hits="$(git grep -n -E "$pattern" -- ':!CHANGELOG.md' ':!docs/archive' src docs README.md scripts Makefile 2>/dev/null || true)"
  if [[ -n "$hits" ]]; then
    echo "ERROR: stale ref ($label) still present:"
    echo "$hits"
    fail=1
  else
    echo "OK: no live hits for $label"
  fi
}

check_absent "src/setup.py path refs" 'src/setup\.py'

version_check="$(python3 - <<'PY'
import re, pathlib, sys
root = pathlib.Path(".")
init = (root / "src/transcribe/__init__.py").read_text(encoding="utf-8")
toml = (root / "pyproject.toml").read_text(encoding="utf-8")
m_init = re.search(r'__version__\s*=\s*"([^"]+)"', init)
m_toml = re.search(r'^version\s*=\s*"([^"]+)"', toml, re.M)
if not m_init or not m_toml:
    print("missing version field")
    sys.exit(1)
if m_init.group(1) != m_toml.group(1):
    print(f"mismatch pyproject={m_toml.group(1)} __init__={m_init.group(1)}")
    sys.exit(1)
print(m_toml.group(1))
PY
)" || {
  echo "ERROR: package version check failed: ${version_check:-}"
  fail=1
}
if [[ -n "${version_check:-}" && "$fail" -eq 0 ]]; then
  echo "OK: package version ${version_check}"
fi

hits_pip="$(git_grep 'pip install transcribe([^\[]|$)' -- ':!CHANGELOG.md' ':!docs/archive')"
if [[ -n "$hits_pip" ]]; then
  filtered="$(echo "$hits_pip" | grep -viE 'not on PyPI|pip install -e|editable|from (git|source)|matrix' || true)"
  if [[ -n "$filtered" ]]; then
    echo "ERROR: bare pip install transcribe advertised without not-on-PyPI / editable caveat:"
    echo "$filtered"
    fail=1
  else
    echo "OK: pip install transcribe mentions are caveated"
  fi
else
  echo "OK: no bare pip install transcribe hits"
fi

hits_extra="$(git_grep "pip install ['\"]?transcribe\[" -- ':!CHANGELOG.md' ':!docs/archive')"
if [[ -n "$hits_extra" ]]; then
  filtered_extra="$(echo "$hits_extra" | grep -viE 'not on PyPI|pip install -e|editable|from a Transcribe git checkout|matrix|Not supported' || true)"
  if [[ -n "$filtered_extra" ]]; then
    echo "ERROR: PyPI-style pip install transcribe[extra] without editable/git caveat:"
    echo "$filtered_extra"
    fail=1
  else
    echo "OK: pip install transcribe[extra] mentions are caveated"
  fi
else
  echo "OK: no pip install transcribe[extra] hits"
fi

todo_hits="$(git grep -n -E '#[[:space:]]*(TODO|FIXME)\b' -- src || true)"
if [[ -n "$todo_hits" ]]; then
  echo "ERROR: TODO/FIXME comments under src/:"
  echo "$todo_hits"
  fail=1
else
  echo "OK: zero TODO/FIXME comments under src/"
fi

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
echo "OK: stale-ref sweep passed"
