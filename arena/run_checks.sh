#!/usr/bin/env bash
# Run every guard for the idea specs.  Used in CI and before committing spec edits.
#
#   ./arena/run_checks.sh            # checks + index freshness
#   ./arena/run_checks.sh --fix      # also regenerate INDEX.md
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ "${1:-}" == "--fix" ]]; then
  python3 arena/build_index.py
  shift || true
fi

echo "== spec invariants =="
python3 arena/spec_checks.py

if python3 -c 'import pytest' 2>/dev/null; then
  echo
  echo "== pytest =="
  python3 -m pytest -q
else
  echo
  echo "pytest not installed — skipping the pytest wrapper (spec_checks already ran)"
  echo "install with: python3 -m pip install pytest"
fi
