#!/usr/bin/env python3
"""A/B token-consumption runner: the plugin's savings, measured for real.

Runs the same task prompt in a fresh fixture folder across three arms per
trial - without the plugin (the baseline), with the plugin loaded
(--plugin-dir <this repo>) but a neutral prompt, and directed (plugin loaded
AND the prompt names the skill) - via headless
`claude -p --output-format json --model opus`, and compares usage.

--dangerously-skip-permissions is passed ONLY because every run happens
inside a disposable generated fixture directory; never reuse this pattern
against a real project.

Paid API usage: ~18 opus runs at defaults (2 tasks x 3 arms x 3 runs). Run
the pilot first:
    python benchmarks/measure_ab.py --runs 1 --tasks summarize
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|build|chore|ci|docs|style|refactor|perf|test)"
    r"(\([\w\-\./]+\))?(!)?: .{1,72}$")
PROMPTS = {"commit": fixtures.PROMPT_COMMIT,
           "summarize": fixtures.PROMPT_SUMMARIZE}

# The "directed" arm: same tasks, but the prompt names the skill - measuring
# the plugin the way it is actually used (deliberate invocation), against the
# same neutral "without" baseline.
DIRECTED_PROMPTS = {
    "commit": ("Use the ollama-commit skill (local Ollama model) to commit "
               "the staged changes in this repository with an appropriate "
               "one-line commit message. Do not push."),
    "summarize": ("Use the ollama-digest skill (local Ollama model) to read "
                  "app.log and summarize what went wrong: the main failure "
                  "patterns and the most likely root cause. Keep it under "
                  "15 lines."),
}

# arm name -> (prompt set, plugin loaded)
ARMS = {"without": (PROMPTS, False),
        "with": (PROMPTS, True),
        "directed": (DIRECTED_PROMPTS, True)}


def run_claude(prompt: str, cwd: Path, with_plugin: bool) -> dict:
    """THE paid-subprocess boundary. Tests monkeypatch this function."""
    argv = ["claude", "-p", prompt, "--output-format", "json",
            "--model", "opus", "--dangerously-skip-permissions"]
    if with_plugin:
        argv += ["--plugin-dir", str(REPO_ROOT)]
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=600)
    except subprocess.TimeoutExpired:
        return {"error": "timeout after 600s"}
    except FileNotFoundError:
        return {"error": "claude CLI not on PATH"}
    if proc.returncode != 0:
        return {"error": f"claude exit {proc.returncode}: "
                         f"{proc.stderr.strip()[:300]}"}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": f"unparseable output: {proc.stdout[:200]}"}


def usage_row(data: dict) -> dict:
    usage = data.get("usage") or {}

    def num(key):
        value = usage.get(key)
        return int(value) if isinstance(value, (int, float)) else 0

    return {
        "tokens_consumed": (num("input_tokens")
                            + num("cache_creation_input_tokens")
                            + num("output_tokens")),
        "cache_read": num("cache_read_input_tokens"),
        "cost_usd": float(data.get("total_cost_usd") or 0),
        "duration_ms": int(data.get("duration_ms") or 0),
        "result_text": str(data.get("result") or ""),
        "error": data.get("error"),
    }


def _git_out(repo: Path, *args: str) -> str:
    # Explicit UTF-8: a non-ASCII model-drafted subject must fail validation,
    # not crash the matrix mid-paid-run on the ANSI codepage.
    return subprocess.run(["git"] + list(args), cwd=repo, capture_output=True,
                          text=True, encoding="utf-8",
                          errors="replace").stdout.strip()


def validate_commit(repo: Path) -> bool:
    if _git_out(repo, "rev-list", "--count", "HEAD") != "2":
        return False
    subject = _git_out(repo, "log", "-1", "--format=%s")
    staged = _git_out(repo, "diff", "--cached", "--name-only")
    return (bool(CONVENTIONAL_RE.match(subject)) and len(subject) <= 72
            and staged == "")


def validate_summarize(text: str) -> bool:
    low = text.lower()
    return ("db-primary" in low
            and ("refused" in low or "connection" in low)
            and ("oom" in low or "out of memory" in low))


def read_delegation(repo: Path) -> tuple:
    """(delegated, local_tokens) from the fixture's usage ledger."""
    ledger = Path(repo) / ".ollama-skills-usage.jsonl"
    if not ledger.is_file():
        return False, 0
    delivered, tokens = False, 0
    for line in ledger.read_text(encoding="utf-8",
                                 errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        tokens += int(rec.get("prompt_tokens") or 0) + int(
            rec.get("output_tokens") or 0)
        if rec.get("delivered"):
            delivered = True
    return delivered, tokens


def _make_fixture(task: str, base: Path) -> Path:
    if task == "commit":
        return fixtures.make_commit_fixture(base / "proj")
    dest = fixtures.make_log_fixture(base / "proj")
    subprocess.run(["git", "-c", "user.name=AB Bench",
                    "-c", "user.email=ab@bench.local", "init", "-q"],
                   cwd=dest, check=True, capture_output=True)
    return dest


def run_matrix(runs: int, tasks, arms, out_dir: Path) -> dict:
    rows = []
    for task in tasks:
        for arm in arms:
            prompt_set, plugin_loaded = ARMS[arm]
            for trial in range(runs):
                base = Path(tempfile.mkdtemp(prefix=f"ab_{task}_{arm}_"))
                fixture = _make_fixture(task, base)
                started = time.monotonic()
                row = usage_row(run_claude(prompt_set[task], fixture,
                                           plugin_loaded))
                row.update({"task": task, "arm": arm, "trial": trial,
                            "wall_s": round(time.monotonic() - started, 1)})
                if row["error"]:
                    row["success"] = False
                elif task == "commit":
                    row["success"] = validate_commit(fixture)
                else:
                    row["success"] = validate_summarize(row["result_text"])
                row["delegated"], row["local_tokens"] = (
                    read_delegation(fixture) if plugin_loaded else (None, 0))
                row.pop("result_text", None)   # keep the record small
                rows.append(row)
                print(f"  {task}/{arm} trial {trial + 1}/{runs}: "
                      f"{row['tokens_consumed']:,} tokens, "
                      f"ok={row['success']}", file=sys.stderr)
    agg = {"model": "opus", "runs_per_cell": runs, "rows": rows, "cells": {}}
    for task in tasks:
        cell = {}
        for arm in arms:
            ok = [r for r in rows if r["task"] == task and r["arm"] == arm
                  and r["success"]]
            n_all = len([r for r in rows
                         if r["task"] == task and r["arm"] == arm])
            tok = [r["tokens_consumed"] for r in ok]
            cell[arm] = {
                "ok": len(ok), "runs": n_all,
                "tokens_mean": round(sum(tok) / len(tok)) if tok else 0,
                "tokens_min": min(tok) if tok else 0,
                "tokens_max": max(tok) if tok else 0,
                "cache_read_mean": round(sum(r["cache_read"] for r in ok)
                                         / len(ok)) if ok else 0,
                "cost_mean_usd": round(sum(r["cost_usd"] for r in ok)
                                       / len(ok), 4) if ok else 0,
                "local_tokens_mean": round(sum(r["local_tokens"] for r in ok)
                                           / len(ok)) if ok else 0,
                "delegated": sum(1 for r in ok if r.get("delegated")),
            }
        # A savings claim needs at least one SUCCESSFUL run on each side -
        # a zero-success cell would otherwise print an absurd 100%. Every
        # plugin arm is compared against the same neutral "without" baseline.
        for arm in arms:
            if (arm != "without" and "without" in cell
                    and cell[arm]["ok"] and cell["without"]["ok"]
                    and cell["without"]["tokens_mean"]):
                cell[arm]["savings_pct"] = round(
                    100 * (1 - cell[arm]["tokens_mean"]
                           / cell["without"]["tokens_mean"]), 1)
        agg["cells"][task] = cell
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (out_dir / f"ab-{stamp}.json").write_text(
        json.dumps(agg, indent=2), encoding="utf-8")
    return agg


def render_table(agg: dict) -> str:
    lines = ["task       arm      ok    tokens (mean)  cache read  "
             "cost USD  local tokens  delegated"]
    for task, cell in agg["cells"].items():
        for arm in ("without", "with", "directed"):
            if arm not in cell:
                continue
            c = cell[arm]
            lines.append(
                f"{task:<10} {arm:<8} {c['ok']}/{c['runs']:<3} "
                f"{c['tokens_mean']:>13,}  {c['cache_read_mean']:>10,}  "
                f"{c['cost_mean_usd']:>8.4f}  {c['local_tokens_mean']:>12,}  "
                f"{c['delegated'] if arm != 'without' else '-'}")
            if "savings_pct" in c:
                lines.append(f"{task:<10} {arm} savings vs without: "
                             f"{c['savings_pct']}% "
                             "(mean tokens, successful runs only)")
    lines.append("")
    lines.append("All arms opus, cold folders; cache reads excluded from the "
                 "consumed metric. The directed arm's prompt names the skill; "
                 "the other two arms share one neutral prompt.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--tasks", default="commit,summarize")
    parser.add_argument("--arms", default="without,with,directed")
    parser.add_argument("--out", default=str(REPO_ROOT / "benchmarks"
                                             / "results"))
    args = parser.parse_args(argv)
    tasks = [t for t in args.tasks.split(",") if t]
    arms = [a for a in args.arms.split(",") if a]
    for task in tasks:
        if task not in PROMPTS:
            print(f"unknown task {task!r}", file=sys.stderr)
            return 2
    for arm in arms:
        if arm not in ARMS:
            print(f"unknown arm {arm!r} (choose from {sorted(ARMS)})",
                  file=sys.stderr)
            return 2
    if any(ARMS[arm][1] for arm in arms):
        health = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "ollama_ask.py"),
             "health"], capture_output=True, text=True)
        if health.returncode != 0:
            print("Ollama is not healthy - the WITH arm cannot delegate. "
                  "Start `ollama serve` first.", file=sys.stderr)
            return 3
    agg = run_matrix(args.runs, tasks, arms, Path(args.out))
    print(render_table(agg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
