#!/usr/bin/env bash
# Scaffold for the commit-msg eval case: builds the deterministic "logpipe"
# commit fixture (benchmarks/fixtures.py) straight into the case's working
# directory (".") before the agent runs. Uses only the shared fixtures CLI —
# no fixture logic is duplicated here.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# Probe by EXECUTION, not command -v: on Windows, python3 can resolve to a
# pymanager/Store shim that exists on PATH but has no runtime installed.
PY=""
for cand in python python3; do
  if "$cand" -c "import sys" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || { echo "no working python interpreter found" >&2; exit 1; }
"$PY" "$REPO_ROOT/benchmarks/fixtures.py" commit .
