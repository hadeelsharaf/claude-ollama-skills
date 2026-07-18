#!/usr/bin/env python3
"""ollama_ask — delegate small tasks to a local Ollama model.

One file, Python 3.9+, standard library only. Claude Code skills call this
script so that big private inputs (git diffs, file bodies) stay on the local
machine and only a small drafted result goes back to Claude.

Subcommands:
  health         Check Ollama, models, and RAM fit.
  models         Show which model each task resolves to, and why.
  warmup         Load a model so later calls are fast.
  ask            Generic prompt -> text (or JSON object with --json-object).
  commit-msg     Read the STAGED git diff locally -> Conventional Commit message.
  draft-command  Plain-words task -> JSON {command, explanation, caution}.
  draft-code     Small spec -> code only (fences stripped, syntax-checked).
  fix-lint       Lint error + code window -> SEARCH/REPLACE suggestion (never applies).

Exit codes: 0 ok · 2 bad usage/over budget · 3 Ollama unreachable ·
4 model missing · 5 timeout/stall · 6 output failed validation.
"""
from __future__ import annotations

import argparse
import ctypes
import fnmatch
import json
import os
import platform
import py_compile
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNREACHABLE = 3
EXIT_NO_MODEL = 4
EXIT_STALL = 5
EXIT_BAD_OUTPUT = 6

TASKS = ("commit", "shell", "code", "general")

TASK_DEFAULTS = {
    "commit": {"max_tokens": 96, "temperature": 0.4},
    "shell": {"max_tokens": 192, "temperature": 0.0},
    "code": {"max_tokens": 512, "temperature": 0.2},
    "general": {"max_tokens": 256, "temperature": 0.3},
}

# First installed model whose name starts with a prefix wins (top first).
PREFERENCES = {
    "code": ["qwen3-coder", "qwen2.5-coder", "devstral", "deepseek-coder", "codegemma"],
    "commit": ["qwen2.5-coder", "llama3.1", "llama3.2", "qwen3", "gemma3"],
    "shell": ["qwen3", "llama3.1", "llama3.2", "qwen2.5"],
    "general": ["qwen3", "llama3.1", "gemma3", "llama3.2", "mistral"],
}

RUNTIME_DEFAULTS = {
    "host": "http://localhost:11434",
    "keep_alive": "30m",
    "stall_seconds": 90,
    "total_timeout_seconds": 480,
    "max_input_chars": 2500,
}

LOCKFILE_PATTERNS = [
    "*.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "*.min.*",
    "poetry.lock", "Cargo.lock", "composer.lock", "go.sum",
]

CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|build|chore|ci|docs|style|refactor|perf|test)"
    r"(\([\w\-\./]+\))?(!)?: .{1,72}$"
)

COMMIT_TYPES = "feat, fix, build, chore, ci, docs, style, refactor, perf, test"


class CliError(Exception):
    """Error with a user-facing message and an exit code."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


class ThinkRejected(Exception):
    """The model refused the 'think' field; retry without it."""


def eprint(*parts) -> None:
    print(*parts, file=sys.stderr)


def debug(message: str) -> None:
    if os.environ.get("OLLAMA_SKILLS_DEBUG"):
        eprint(f"[debug] {message}")


# --------------------------------------------------------------------------
# Config and model resolution
# --------------------------------------------------------------------------

def _read_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        eprint(f"warning: ignoring bad config {path}: {exc}")
        return {}


def load_config() -> dict:
    """Merge defaults <- user config <- project config (project wins)."""
    cfg = dict(RUNTIME_DEFAULTS)
    cfg["tasks"] = {task: dict(defaults) for task, defaults in TASK_DEFAULTS.items()}

    override = os.environ.get("OLLAMA_SKILLS_CONFIG")
    if override:
        files = [Path(override)]
    else:
        files = [Path.home() / ".ollama-skills.json", Path.cwd() / ".ollama-skills.json"]

    for path in files:
        if not path.is_file():
            continue
        data = _read_json_file(path)
        for key, value in data.items():
            if key == "tasks" and isinstance(value, dict):
                for task, task_cfg in value.items():
                    cfg["tasks"].setdefault(task, {}).update(task_cfg or {})
            else:
                cfg[key] = value
        debug(f"loaded config {path}")

    if os.environ.get("OLLAMA_HOST"):
        host = os.environ["OLLAMA_HOST"]
        if not host.startswith("http"):
            host = "http://" + host
        cfg["host"] = host
    return cfg


def installed_models(host: str) -> list:
    data = http_get_json(host, "/api/tags")
    return data.get("models", [])


def resolve_model(task: str, cfg: dict, flag_model, installed_cache: dict):
    """Return (model, source). source: flag | env | config | auto."""
    if flag_model:
        return flag_model, "flag"
    env_task = os.environ.get(f"OLLAMA_SKILLS_MODEL_{task.upper()}")
    if env_task:
        return env_task, "env"
    env_default = os.environ.get("OLLAMA_SKILLS_MODEL")
    if env_default:
        return env_default, "env"
    config_model = (cfg["tasks"].get(task) or {}).get("model")
    if config_model:
        return config_model, "config"

    if "models" not in installed_cache:
        installed_cache["models"] = [m.get("name", "") for m in installed_models(cfg["host"])]
    names = installed_cache["models"]
    for prefix in PREFERENCES.get(task, []):
        for name in names:
            if name.startswith(prefix):
                return name, "auto"
    if names:
        return names[0], "auto"
    raise CliError(EXIT_NO_MODEL, "No Ollama models installed. Try: ollama pull llama3.2:1b")


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def _unreachable(host: str) -> CliError:
    return CliError(
        EXIT_UNREACHABLE,
        f"Cannot reach Ollama at {host}. Is Ollama running? Try: ollama serve",
    )


def http_get_json(host: str, path: str) -> dict:
    try:
        with urllib.request.urlopen(host + path, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise CliError(EXIT_UNREACHABLE, f"Ollama returned HTTP {exc.code} for {path}")
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
        raise _unreachable(host)


def stream_generate(cfg: dict, payload: dict, stall_seconds: int,
                    total_seconds: int, quiet: bool) -> str:
    """POST /api/generate with stream:true. Returns the full response text."""
    host = cfg["host"]
    model = payload.get("model", "?")
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        host + "/api/generate", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    deadline = time.monotonic() + total_seconds
    pieces = []
    try:
        # The socket timeout applies to every read: it is the stall detector.
        with urllib.request.urlopen(request, timeout=stall_seconds) as resp:
            while True:
                if time.monotonic() > deadline:
                    raise CliError(
                        EXIT_STALL,
                        f"Total timeout after {total_seconds}s. Use a smaller model or input.",
                    )
                try:
                    line = resp.readline()
                except (socket.timeout, TimeoutError):
                    raise CliError(
                        EXIT_STALL,
                        f"Stalled: no output for {stall_seconds}s from {model}. "
                        "Warm up first, shrink the input, or pick a smaller model.",
                    )
                if not line:
                    break
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("error"):
                    raise CliError(EXIT_BAD_OUTPUT, f"Ollama error: {chunk['error']}")
                pieces.append(chunk.get("response", ""))
                if not quiet:
                    sys.stderr.write(".")
                    sys.stderr.flush()
                if chunk.get("done"):
                    break
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")
        except OSError:
            pass
        if exc.code == 404 or "not found" in detail.lower():
            raise CliError(
                EXIT_NO_MODEL,
                f"Model '{model}' is not installed. Try: ollama pull {model}",
            )
        if "think" in detail.lower():
            raise ThinkRejected()
        raise CliError(EXIT_BAD_OUTPUT, f"Ollama HTTP {exc.code}: {detail[:300]}")
    except (socket.timeout, TimeoutError):
        raise CliError(
            EXIT_STALL,
            f"Stalled: no output for {stall_seconds}s from {model}. "
            "Warm up first, shrink the input, or pick a smaller model.",
        )
    except (urllib.error.URLError, ConnectionError):
        raise _unreachable(host)
    finally:
        if not quiet:
            sys.stderr.write("\n")
            sys.stderr.flush()
    return "".join(pieces)


def generate(task: str, prompt: str, args, cfg: dict, system=None,
             response_format=None, max_tokens=None) -> str:
    """Resolve the model, call Ollama, sanitize <think> blocks."""
    cache: dict = {}
    model, _source = resolve_model(task, cfg, args.model, cache)
    task_cfg = cfg["tasks"].get(task) or {}
    options = {
        "num_predict": (args.max_tokens or max_tokens
                        or task_cfg.get("max_tokens")
                        or TASK_DEFAULTS[task]["max_tokens"]),
    }
    temperature = args.temperature
    if temperature is None:
        temperature = task_cfg.get("temperature")
    if temperature is None:
        temperature = TASK_DEFAULTS[task]["temperature"]
    options["temperature"] = temperature

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "think": False,
        "keep_alive": cfg.get("keep_alive", "30m"),
        "options": options,
    }
    if system:
        payload["system"] = system
    if response_format:
        payload["format"] = response_format

    stall = args.stall_seconds or int(cfg.get("stall_seconds", 90))
    total = args.timeout or int(cfg.get("total_timeout_seconds", 480))
    debug(f"model={model} stall={stall}s total={total}s options={options}")
    try:
        text = stream_generate(cfg, payload, stall, total, args.quiet)
    except ThinkRejected:
        payload.pop("think", None)
        text = stream_generate(cfg, payload, stall, total, args.quiet)
    return strip_think(text)


# --------------------------------------------------------------------------
# Sanitizers and small helpers
# --------------------------------------------------------------------------

def strip_think(text: str) -> str:
    return re.sub(r"<think>.*?(</think>|\Z)", "", text, flags=re.DOTALL).strip()


def strip_fences(text: str) -> str:
    """If the text is (or contains) a fenced code block, return the block body."""
    match = re.search(r"```[a-zA-Z0-9_+.-]*\n(.*?)\n?```", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def strip_quotes(text: str) -> str:
    text = text.strip()
    while len(text) > 1 and text[0] == text[-1] and text[0] in "\"'`":
        text = text[1:-1].strip()
    return text


def check_budget(text: str, cfg: dict, args) -> None:
    limit = args.max_input_chars or int(cfg.get("max_input_chars", 2500))
    if args.force:
        return
    if len(text) > limit:
        raise CliError(
            EXIT_USAGE,
            f"Input is {len(text)} chars, over the {limit}-char budget for local "
            "inference. Shrink the input, raise max_input_chars in "
            ".ollama-skills.json, or pass --force.",
        )


def free_ram_bytes():
    """Best-effort free RAM. Returns None when unknown."""
    try:
        if os.name == "nt":
            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            status = MemoryStatusEx()
            status.dwLength = ctypes.sizeof(MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
            return None
        meminfo = Path("/proc/meminfo")
        if meminfo.is_file():
            for line in meminfo.read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except Exception:  # noqa: BLE001 - RAM info is advisory only
        return None
    return None


def gb(num_bytes) -> str:
    return f"{num_bytes / 1e9:.1f} GB"


def run_git(cmd_args, check=True) -> str:
    try:
        result = subprocess.run(
            ["git"] + cmd_args, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        raise CliError(EXIT_USAGE, "git is not installed or not on PATH.")
    if check and result.returncode != 0:
        raise CliError(EXIT_USAGE, f"git {' '.join(cmd_args)} failed: {result.stderr.strip()}")
    return result.stdout


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------

def cmd_health(args, cfg: dict) -> int:
    version = http_get_json(cfg["host"], "/api/version").get("version", "?")
    models = installed_models(cfg["host"])
    free = free_ram_bytes()
    if args.json:
        print(json.dumps({
            "host": cfg["host"], "version": version,
            "models": [{"name": m.get("name"), "size": m.get("size")} for m in models],
            "free_ram_bytes": free,
        }, indent=2))
        return EXIT_OK
    print(f"Ollama {version} at {cfg['host']} — OK")
    if not models:
        print("No models installed. Try: ollama pull llama3.2:1b")
        return EXIT_OK
    print(f"Installed models ({len(models)}):")
    for model in models:
        name, size = model.get("name", "?"), int(model.get("size", 0))
        line = f"  {name:<24} {gb(size)}"
        if free is not None and size > free:
            line += f"   WARNING: bigger than free RAM ({gb(free)}) — will be slow or fail"
        print(line)
    if free is not None:
        print(f"Free RAM: {gb(free)}")
    return EXIT_OK


def cmd_models(args, cfg: dict) -> int:
    cache: dict = {}
    resolved = {}
    for task in TASKS:
        model, source = resolve_model(task, cfg, args.model, cache)
        resolved[task] = {"model": model, "source": source}
    if args.json:
        print(json.dumps({"tasks": resolved, "installed": cache.get("models", [])}, indent=2))
        return EXIT_OK
    print(f"{'task':<10} {'model':<28} source")
    for task, info in resolved.items():
        print(f"{task:<10} {info['model']:<28} {info['source']}")
    return EXIT_OK


def cmd_warmup(args, cfg: dict) -> int:
    started = time.monotonic()
    generate(args.task, "Reply with the single word: OK", args, cfg, max_tokens=8)
    seconds = time.monotonic() - started
    cache: dict = {}
    model, _ = resolve_model(args.task, cfg, args.model, cache)
    print(f"warmed {model} in {seconds:.1f}s (keep_alive {cfg.get('keep_alive')})")
    return EXIT_OK


def cmd_ask(args, cfg: dict) -> int:
    if args.stdin:
        prompt = sys.stdin.read()
    elif args.prompt:
        prompt = args.prompt
    else:
        raise CliError(EXIT_USAGE, "Give a prompt argument or use --stdin.")
    check_budget(prompt + (args.system or ""), cfg, args)

    response_format = "json" if args.json_object else None
    text = generate(args.task, prompt, args, cfg,
                    system=args.system, response_format=response_format)
    if args.json_object:
        try:
            json.loads(text)
        except json.JSONDecodeError:
            retry_system = ((args.system or "") +
                            " Return ONLY one valid JSON object. No prose.").strip()
            text = generate(args.task, prompt, args, cfg,
                            system=retry_system, response_format="json")
            try:
                json.loads(text)
            except json.JSONDecodeError:
                eprint(f"raw output:\n{text}")
                raise CliError(EXIT_BAD_OUTPUT, "Model did not return valid JSON.")
    print(text)
    return EXIT_OK


COMMIT_SYSTEM = (
    "You write git commit messages. Reply with ONE line in Conventional Commit "
    f"format: <type>: <summary>. Allowed types: {COMMIT_TYPES}. Use present "
    "tense. Keep the whole line under 72 characters. Describe only what the "
    "diff shows — never invent issue numbers or details. Your entire response "
    "is passed directly into git commit, so reply with the message only."
)


def _staged_context(cfg: dict, args) -> str:
    inside = run_git(["rev-parse", "--is-inside-work-tree"], check=False).strip()
    if inside != "true":
        raise CliError(EXIT_USAGE, "Not inside a git repository.")
    stat = run_git(["diff", "--cached", "--stat"]).strip()
    if not stat:
        raise CliError(EXIT_USAGE, "Nothing is staged. Run: git add <files> first.")
    names = [n for n in run_git(["diff", "--cached", "--name-only"]).splitlines() if n]
    kept = [n for n in names
            if not any(fnmatch.fnmatch(Path(n).name, p) for p in LOCKFILE_PATTERNS)]
    limit = args.max_input_chars or int(cfg.get("max_input_chars", 2500))
    parts = ["File summary:", stat, ""]
    used = sum(len(p) for p in parts)
    for name in kept:
        diff = run_git(["diff", "--cached", "-U1", "--", name])
        excerpt_lines = diff.splitlines()[:40]
        excerpt = "\n".join(excerpt_lines)
        if used + len(excerpt) > limit:
            parts.append(f"(more changes in {name} not shown)")
            break
        parts.append(excerpt)
        used += len(excerpt)
    return "\n".join(parts)[:limit]


def cmd_commit_msg(args, cfg: dict) -> int:
    context = _staged_context(cfg, args)
    style_note = "" if args.body else " Reply with one single line."
    prompt = f"Write the commit message for this staged change:\n\n{context}"
    text = generate("commit", prompt, args, cfg, system=COMMIT_SYSTEM + style_note)
    message = _clean_commit(text, args)

    if args.style == "conventional" and not CONVENTIONAL_RE.match(message.splitlines()[0]):
        feedback = (COMMIT_SYSTEM + style_note +
                    f" Your last answer was rejected: {message!r}. It must match "
                    "<type>: <summary> with an allowed type and under 72 chars.")
        text = generate("commit", prompt, args, cfg, system=feedback)
        message = _clean_commit(text, args)
        if not CONVENTIONAL_RE.match(message.splitlines()[0]):
            eprint(f"raw output:\n{text}")
            raise CliError(EXIT_BAD_OUTPUT,
                           "Model could not produce a valid Conventional Commit line.")
    print(message)
    return EXIT_OK


def _clean_commit(text: str, args) -> str:
    text = strip_fences(strip_think(text))
    if args.body:
        return text.strip()
    line = strip_quotes(text.strip().splitlines()[0] if text.strip() else "")
    return line.rstrip(".")


SHELL_SYSTEM_TEMPLATE = (
    "You translate a plain-words task into ONE {shell} command for {os_name}. "
    "Reply with ONLY a JSON object with exactly these keys: "
    '"command" (string, the command), '
    '"explanation" (string, one short sentence), '
    '"caution" (string, one short warning or "none"). '
    "Prefer safe, non-destructive flags. Never chain a download into execution."
)


def cmd_draft_command(args, cfg: dict) -> int:
    shell = args.shell or ("powershell" if os.name == "nt" else "bash")
    os_name = platform.system() or "this OS"
    system = SHELL_SYSTEM_TEMPLATE.format(shell=shell, os_name=os_name)
    check_budget(args.task_text, cfg, args)

    def attempt(extra: str = "") -> dict:
        text = generate("shell", args.task_text, args, cfg,
                        system=system + extra, response_format="json")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("not an object")
        if not isinstance(data.get("command"), str) or not data["command"].strip():
            raise ValueError("missing command")
        data.setdefault("explanation", "")
        data.setdefault("caution", "none")
        return data

    try:
        data = attempt()
    except (json.JSONDecodeError, ValueError):
        try:
            data = attempt(" Your last answer was invalid. JSON object ONLY.")
        except (json.JSONDecodeError, ValueError):
            raise CliError(EXIT_BAD_OUTPUT, "Model did not return a usable command JSON.")
    print(json.dumps(data, indent=2))
    return EXIT_OK


CODE_SYSTEM = (
    "You write code. Reply with ONLY the code for the request — no prose, no "
    "markdown fences. If details are missing, pick the most standard option. "
    "Write complete, runnable code in {lang}."
)


def _syntax_check(code_text: str, lang: str):
    """Returns None when OK, or an error string."""
    if lang == "python":
        tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                          encoding="utf-8")
        try:
            tmp.write(code_text)
            tmp.close()
            py_compile.compile(tmp.name, doraise=True)
            return None
        except py_compile.PyCompileError as exc:
            return str(exc)
        finally:
            os.unlink(tmp.name)
    if lang == "javascript" and shutil.which("node"):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                          encoding="utf-8")
        try:
            tmp.write(code_text)
            tmp.close()
            result = subprocess.run(["node", "--check", tmp.name],
                                    capture_output=True, text=True)
            return None if result.returncode == 0 else result.stderr.strip()
        finally:
            os.unlink(tmp.name)
    return None


def cmd_draft_code(args, cfg: dict) -> int:
    if args.spec_file:
        spec = Path(args.spec_file).read_text(encoding="utf-8")
    elif args.spec:
        spec = args.spec
    else:
        raise CliError(EXIT_USAGE, "Give --spec or --spec-file.")
    check_budget(spec, cfg, args)
    system = CODE_SYSTEM.format(lang=args.lang)

    code_text = strip_fences(generate("code", spec, args, cfg, system=system))
    error = _syntax_check(code_text, args.lang)
    if error:
        retry_spec = f"{spec}\n\nYour previous code had this syntax error:\n{error}\nFix it."
        code_text = strip_fences(generate("code", retry_spec, args, cfg, system=system))
        error = _syntax_check(code_text, args.lang)
        if error:
            eprint(f"raw output:\n{code_text}")
            raise CliError(EXIT_BAD_OUTPUT, f"Draft still has a syntax error: {error[:200]}")
    if args.out:
        Path(args.out).write_text(code_text + "\n", encoding="utf-8")
        eprint(f"wrote {args.out}")
    print(code_text)
    return EXIT_OK


FIX_SYSTEM = (
    "You fix ONE lint finding with the smallest possible edit. Reply in EXACTLY "
    "this format and nothing else:\n"
    "SUGGESTION\n<<<<<<< SEARCH\n(the exact original lines)\n=======\n"
    "(the replacement lines)\n>>>>>>> REPLACE\nWHY: one short sentence\n"
    "Rules: touch ONLY the flagged line(s); never change behavior; if a safe "
    "fix is not possible, reply with the single word SKIP."
)


def cmd_fix_lint(args, cfg: dict) -> int:
    if args.errors_file:
        error_text = Path(args.errors_file).read_text(encoding="utf-8")
    elif args.error:
        error_text = args.error
    else:
        raise CliError(EXIT_USAGE, "Give --error or --errors-file.")
    source = Path(args.file)
    if not source.is_file():
        raise CliError(EXIT_USAGE, f"No such file: {source}")
    lines = source.read_text(encoding="utf-8").splitlines()
    center = max(1, args.line)
    start = max(0, center - 1 - 15)
    end = min(len(lines), center + 15)
    window = "\n".join(f"{i + 1}: {lines[i]}" for i in range(start, end))
    prompt = (f"Lint finding:\n{error_text}\n\nFile {source.name}, "
              f"lines {start + 1}-{end} (flagged line {center}):\n{window}")
    check_budget(prompt, cfg, args)

    text = generate("code", prompt, args, cfg, system=FIX_SYSTEM, max_tokens=256)
    if text.strip() == "SKIP":
        print("SKIP")
        return EXIT_OK
    if "<<<<<<< SEARCH" not in text or ">>>>>>> REPLACE" not in text:
        text = generate("code", prompt, args, cfg,
                        system=FIX_SYSTEM + " Use the exact SUGGESTION format.",
                        max_tokens=256)
        if "<<<<<<< SEARCH" not in text or ">>>>>>> REPLACE" not in text:
            eprint(f"raw output:\n{text}")
            raise CliError(EXIT_BAD_OUTPUT, "Model did not return a SUGGESTION block.")
    print(text.strip())
    return EXIT_OK


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", help="exact Ollama model name (beats all config)")
    common.add_argument("--task", choices=TASKS, default="general",
                        help="task profile for model choice and budgets")
    common.add_argument("--max-tokens", type=int, dest="max_tokens")
    common.add_argument("--temperature", type=float)
    common.add_argument("--timeout", type=int, help="total seconds cap")
    common.add_argument("--stall-seconds", type=int, dest="stall_seconds")
    common.add_argument("--max-input-chars", type=int, dest="max_input_chars")
    common.add_argument("--force", action="store_true",
                        help="send input even when over the size budget")
    common.add_argument("--quiet", action="store_true", help="no progress dots")

    parser = argparse.ArgumentParser(
        prog="ollama_ask.py",
        description="Delegate small tasks to a local Ollama model.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_health = sub.add_parser("health", parents=[common], help="check Ollama + models + RAM")
    p_health.add_argument("--json", action="store_true")

    p_models = sub.add_parser("models", parents=[common], help="show model per task")
    p_models.add_argument("--json", action="store_true")

    sub.add_parser("warmup", parents=[common], help="load a model now")

    p_ask = sub.add_parser("ask", parents=[common], help="generic prompt -> text")
    p_ask.add_argument("prompt", nargs="?")
    p_ask.add_argument("--stdin", action="store_true", help="read the prompt from stdin")
    p_ask.add_argument("--system", help="system prompt")
    p_ask.add_argument("--json-object", action="store_true", dest="json_object",
                       help="force a JSON object answer")

    p_commit = sub.add_parser("commit-msg", parents=[common],
                              help="staged diff -> Conventional Commit message")
    p_commit.add_argument("--style", choices=["conventional", "plain"],
                          default="conventional")
    p_commit.add_argument("--body", action="store_true",
                          help="allow a multi-line message body")
    p_commit.set_defaults(task="commit")

    p_cmd = sub.add_parser("draft-command", parents=[common],
                           help="plain words -> shell command JSON")
    p_cmd.add_argument("task_text", help="the task in plain words")
    p_cmd.add_argument("--shell", choices=["powershell", "bash", "cmd", "sh"])
    p_cmd.set_defaults(task="shell")

    p_code = sub.add_parser("draft-code", parents=[common], help="small spec -> code")
    p_code.add_argument("--spec")
    p_code.add_argument("--spec-file", dest="spec_file")
    p_code.add_argument("--lang", default="python")
    p_code.add_argument("--out", help="also write the code to this file")
    p_code.set_defaults(task="code")

    p_fix = sub.add_parser("fix-lint", parents=[common],
                           help="lint finding -> SEARCH/REPLACE suggestion")
    p_fix.add_argument("--file", required=True)
    p_fix.add_argument("--line", type=int, required=True)
    p_fix.add_argument("--error")
    p_fix.add_argument("--errors-file", dest="errors_file")
    p_fix.set_defaults(task="code")

    return parser


HANDLERS = {
    "health": cmd_health,
    "models": cmd_models,
    "warmup": cmd_warmup,
    "ask": cmd_ask,
    "commit-msg": cmd_commit_msg,
    "draft-command": cmd_draft_command,
    "draft-code": cmd_draft_code,
    "fix-lint": cmd_fix_lint,
}


def main(argv=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code not in (0, None) else EXIT_OK
    cfg = load_config()
    try:
        return HANDLERS[args.command](args, cfg)
    except CliError as exc:
        eprint(f"error: {exc}")
        return exc.code
    except KeyboardInterrupt:
        eprint("interrupted")
        return EXIT_STALL


if __name__ == "__main__":
    sys.exit(main())
