#!/usr/bin/env python3
"""Opt-in end-to-end test against a REAL local Ollama.

Run: RUN_OLLAMA_E2E=1 python tests/e2e_local.py
Optional: OLLAMA_SKILLS_MODEL=qwen2.5-coder:1.5b to pick the model for every task.

Prints one `E2E <name> <seconds>s` line per step. Exits 1 on any failure.
Skips politely (exit 0) when RUN_OLLAMA_E2E is not set.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "ollama_ask.py"


def rmtree_force(path: str) -> None:
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=onerror)


def run_step(name: str, argv: list, cwd=None, stdin_text=None) -> str:
    started = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)] + argv + ["--quiet"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=cwd, timeout=600, input=stdin_text,
        )
    except subprocess.TimeoutExpired:
        print(f"E2E {name} FAILED: no answer within 600s (is the model too big for this machine?)")
        sys.exit(1)
    seconds = time.monotonic() - started
    if result.returncode != 0:
        print(f"E2E {name} FAILED (exit {result.returncode}) after {seconds:.1f}s")
        print("stdout:", result.stdout.strip())
        print("stderr:", result.stderr.strip())
        sys.exit(1)
    print(f"E2E {name} {seconds:.1f}s")
    return result.stdout.strip()


def main() -> int:
    if os.environ.get("RUN_OLLAMA_E2E") != "1":
        print("skipped (set RUN_OLLAMA_E2E=1 to run against a real local Ollama)")
        return 0

    run_step("health", ["health"])
    run_step("warmup", ["warmup", "--task", "commit"])
    out = run_step("ask", ["ask", "Reply with the single word OK"])
    print(f"  ask said: {out[:60]!r}")

    tmp = tempfile.mkdtemp(prefix="ollama_e2e_")
    try:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
        (repo / "notify.py").write_text(
            "def notify(user, message):\n"
            "    if not user.email:\n"
            "        return False\n"
            "    send_email(user.email, message)\n"
            "    return True\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        message = run_step("commit-msg", ["commit-msg"], cwd=repo)
        print(f"  commit-msg said: {message!r}")
    finally:
        rmtree_force(tmp)

    out = run_step("draft-command", ["draft-command", "show the five newest files in this folder"])
    print(f"  draft-command said: {out[:100]!r}...")

    sample = "\n".join(
        f"2026-07-14T09:30:0{i % 10}Z ERROR connection refused to db attempt {i}"
        for i in range(30)
    )
    digest = run_step("summarize", ["summarize", "--kind", "log"], stdin_text=sample)
    print(f"  summarize said: {digest[:100]!r}...")

    print("E2E all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
