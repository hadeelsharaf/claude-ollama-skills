#!/usr/bin/env bash
# Scaffold for the summarize eval case: builds the deterministic app.log
# fixture (benchmarks/fixtures.py) straight into the case's working directory
# (".") before the agent runs. Uses only the shared fixtures CLI — no fixture
# logic is duplicated here.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
"$PY" "$REPO_ROOT/benchmarks/fixtures.py" log .
