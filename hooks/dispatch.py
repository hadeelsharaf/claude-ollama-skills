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
