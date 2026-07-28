#!/usr/bin/env python3
"""Opt-in end-to-end test against a REAL kind cluster + local Ollama.

Run: RUN_K8S_E2E=1 python tests/e2e_k8s.py
Requires: a running kind cluster with a crashlooping pod (see scripts/kind-up.sh),
kubectl with a current context, and gemma2:2b pulled. Runs ALONE — never with a
second model loaded (RAM ceiling on the dev machine).

Skips politely (exit 0) when RUN_K8S_E2E is not set.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "ollama_ask.py"


def sh(argv) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main() -> int:
    if os.environ.get("RUN_K8S_E2E") != "1":
        print("skipped (set RUN_K8S_E2E=1 to run against a real kind cluster)")
        return 0

    ctx = sh(["kubectl", "config", "current-context"])
    if ctx.returncode != 0 or not ctx.stdout.strip():
        print("no kubectl context — run scripts/kind-up.sh first")
        return 1
    print(f"context: {ctx.stdout.strip()}")

    pods = sh(["kubectl", "get", "pods", "-o",
               "jsonpath={.items[?(@.status.phase!='Running')].metadata.name}"])
    pod = (pods.stdout.split() or ["crashloop"])[0]
    print(f"triaging pod: {pod}")

    describe = sh(["kubectl", "describe", "pod", pod]).stdout
    events = sh(["kubectl", "get", "events",
                 f"--field-selector=involvedObject.name={pod}"]).stdout
    logs = sh(["kubectl", "logs", pod, "--tail", "200", "--previous"]).stdout
    blob = "\n".join([describe, events, logs])

    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "summarize", "--kind", "log", "--quiet"],
        input=blob, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600,
    )
    seconds = time.monotonic() - started
    if result.returncode != 0:
        print(f"E2E k8s-triage FAILED (exit {result.returncode}) after {seconds:.1f}s")
        print("stderr:", result.stderr.strip())
        return 1
    print(f"E2E k8s-triage {seconds:.1f}s")
    print("digest:\n" + result.stdout.strip())
    print("E2E k8s all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
