"""Plugin hook dispatcher for ollama-skills.

One stdlib-only entry point for every hook event the plugin registers
(SessionStart, UserPromptSubmit, PreToolUse, Stop). Reads the event JSON
from stdin, switches on hook_event_name, prints at most a small
counts-only payload, and exits 0.

Fail-open contract: ANY internal error exits 0 with no output, after a
best-effort counts-only breadcrumb row (cmd="hook_error") is appended to
the usage ledger. A broken hook must never block or slow the user, and a
crash is silent permissiveness, never silent refusal.

Verified mechanism reference:
docs/superpowers/notes/2026-08-08-hooks-capabilities-research.md
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = HOOKS_DIR.parent / "scripts"
SCRIPT = SCRIPTS_DIR / "ollama_ask.py"

# Tasks 2-5 register handlers here: {event_name: handler(event) -> None}
HANDLERS = {}

CARD_TASKS = ("commit", "summarize")


def handle_session_start(event: dict) -> None:
    """One compact counts-only card; silent unless delegation is ready."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "models", "--json"],
        capture_output=True, text=True, timeout=3)
    if proc.returncode != 0:
        return
    data = json.loads(proc.stdout)
    if not data.get("installed"):
        return  # Ollama unreachable or no models: never advertise
    tasks = data.get("tasks", {})
    parts = ["{} -> {}".format(t, tasks[t]["model"])
             for t in CARD_TASKS
             if isinstance(tasks.get(t), dict) and tasks[t].get("model")]
    if not parts:
        return
    print("ollama-skills: local delegation ready ({}). Failing tests: "
          "pipe the run into summarize --kind test (skill: ollama-digest)."
          .format(", ".join(parts)))


HANDLERS["SessionStart"] = handle_session_start


HINT_TRIGGERS = [
    (re.compile(r"\bcommit\b", re.I), "ollama-commit"),
    (re.compile(r"\bchangelog\b|\brelease notes\b", re.I), "ollama-digest"),
    (re.compile(r"\bdocker logs\b|\blog file\b|\bsummarize\b.{0,20}\blog\b",
                re.I), "ollama-digest"),
    (re.compile(r"\bfailing tests?\b|\btests? fail\b|\btest failures?\b",
                re.I), "ollama-digest"),
    (re.compile(r"\bpull request\b|\bpr description\b", re.I), "ollama-pr"),
]


def handle_prompt(event: dict) -> None:
    """First matching trigger wins; silent otherwise. Never echoes the
    prompt back - the hint names a skill and nothing else."""
    prompt = str(event.get("prompt") or "")
    for pattern, skill in HINT_TRIGGERS:
        if pattern.search(prompt):
            print("hint: ollama-skills can do this locally "
                  "(skill: {}).".format(skill))
            return


HANDLERS["UserPromptSubmit"] = handle_prompt


_GIT_LOG = re.compile(r"\bgit\s+log\b")
_GIT_LOG_PATCH = re.compile(r"(^|\s)(-p|--patch|--word-diff|--full-diff)\b")
_GIT_DIFF_CACHED = re.compile(r"\bgit\s+diff\b[^|]*--cached")
_DOCKER_LOGS = re.compile(r"\bdocker\s+logs\b")


def classify_bulk_read(command: str):
    """(skill, pipe_form) for a raw bulk read the skills ban, else None.

    Conservative on purpose: prefer missing a match to flagging a form a
    skill mandates (git diff --cached --stat must never match)."""
    if _GIT_LOG.search(command) and _GIT_LOG_PATCH.search(command):
        return ("ollama-digest",
                'git log --oneline <range> | python <script> summarize '
                '--kind git')
    if _GIT_DIFF_CACHED.search(command) and "--stat" not in command:
        return ("ollama-commit",
                "git diff --cached --stat (names and sizes only), or "
                "commit-msg to draft the message locally")
    if _DOCKER_LOGS.search(command) and "summarize" not in command:
        return ("ollama-docker",
                'docker logs --tail 200 <container> 2>&1 | python <script> '
                'summarize --kind log')
    return None


def handle_pretooluse(event: dict) -> None:
    """Only ever tightens: "ask" adds a prompt; never allow, never deny."""
    if event.get("tool_name") not in ("Bash", "PowerShell"):
        return
    command = str((event.get("tool_input") or {}).get("command") or "")
    hit = classify_bulk_read(command)
    if hit is None:
        return
    skill, pipe_form = hit
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": (
            "ollama-skills: this reads bulk content the {} path delegates "
            "locally - pipe form: {}. Run it anyway?".format(
                skill, pipe_form))}}))


HANDLERS["PreToolUse"] = handle_pretooluse


def _breadcrumb(event_name: str, exc: BaseException) -> None:
    """Counts-only failure row. Best-effort: swallows its own errors."""
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        import ollama_ask
        cfg = ollama_ask.load_config()
        if not ollama_ask._usage_enabled(cfg):
            return
        path, _ = ollama_ask._usage_path(cfg)
        row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "v": 1, "cmd": "hook_error", "event": event_name,
               "error": type(exc).__name__}
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:
        pass


def main() -> int:
    event_name = "unknown"
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            return 0
        event_name = str(event.get("hook_event_name") or "unknown")
        handler = HANDLERS.get(event_name)
        if handler is not None:
            handler(event)
        return 0
    except BaseException as exc:
        if isinstance(exc, KeyboardInterrupt):
            return 0
        _breadcrumb(event_name, exc)
        return 0


if __name__ == "__main__":
    sys.exit(main())
