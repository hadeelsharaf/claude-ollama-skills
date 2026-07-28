"""Contract tests for scripts/ollama_ask.py against a fake Ollama server.

Run: python -m unittest tests.test_ollama_ask -v
Standard library only. No network beyond 127.0.0.1.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import ollama_ask  # noqa: E402

FAKE_MODELS = [
    {"name": "qwen3:8b", "size": 5_000_000_000},
    {"name": "llama3.2:1b", "size": 1_300_000_000},
]
CANNED_TEXT = "feat: add upload retry loop"
CANNED_JSON = '{"command": "ls -la", "explanation": "lists files", "caution": "none"}'
SUGGESTION_TEXT = (
    "SUGGESTION\n<<<<<<< SEARCH\nimport os\n=======\n\n>>>>>>> REPLACE\n"
    "WHY: the import is unused\n"
)


class FakeOllamaHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    counters: dict = {}
    last_payload: dict = {}
    generate_calls: int = 0
    prompts: list = []
    models_response: list = FAKE_MODELS

    def log_message(self, *args):  # silence
        pass

    def _send_json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send_json(200, {"models": FakeOllamaHandler.models_response})
        elif self.path == "/api/version":
            self._send_json(200, {"version": "0.0-test"})
        else:
            self._send_json(404, {"error": "unknown path"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        FakeOllamaHandler.last_payload = payload
        if self.path == "/api/generate":
            FakeOllamaHandler.generate_calls += 1
            FakeOllamaHandler.prompts.append(payload.get("prompt", ""))
        if self.path != "/api/generate":
            self._send_json(404, {"error": "unknown path"})
            return
        prompt = payload.get("prompt", "") + payload.get("system", "")
        model = payload.get("model", "")

        if model == "missing-model":
            self._send_json(404, {"error": "model 'missing-model' not found"})
            return
        if model == "no-think-model" and "think" in payload:
            self._send_json(400, {"error": "model does not support think"})
            return

        if "THINKBLOCK" in prompt:
            text = "<think>secret reasoning</think>" + CANNED_TEXT
        elif "CODEBLOCK" in prompt:
            text = "```python\nprint('hi')\n```"
        elif "BADCOMMIT" in prompt:
            text = "I cannot help with that request."
        elif "SKIPFIX" in prompt:
            text = "SKIP"
        elif "NONASCII" in prompt:
            text = "naïve ✓ done"
        elif "SUGGESTFIX" in prompt:
            text = SUGGESTION_TEXT
        elif "BADJSON" in prompt:
            key = "badjson"
            FakeOllamaHandler.counters[key] = FakeOllamaHandler.counters.get(key, 0) + 1
            if FakeOllamaHandler.counters[key] == 1:
                text = "not json at all"
            else:
                text = CANNED_JSON
        elif payload.get("format") == "json":
            text = CANNED_JSON
        else:
            text = CANNED_TEXT

        # Stream as NDJSON, HTTP/1.0 close-delimited.
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        half = max(1, len(text) // 2)
        chunks = [text[:half], text[half:]]
        for i, chunk in enumerate(chunks):
            line = json.dumps({"model": model, "response": chunk, "done": False})
            self.wfile.write(line.encode() + b"\n")
            self.wfile.flush()
            if "SLOWSTALL" in prompt and i == 0:
                time.sleep(3)
        final = {
            "model": model, "response": "", "done": True,
            "prompt_eval_count": 10, "eval_count": 12,
            "load_duration": 1000000, "total_duration": 2000000,
        }
        self.wfile.write(json.dumps(final).encode() + b"\n")
        self.wfile.flush()


def rmtree_force(path: str) -> None:
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=onerror)


class QuietServer(ThreadingHTTPServer):
    """Client aborts (stall tests) make handlers raise on write; keep stderr clean."""

    def handle_error(self, request, client_address):
        pass


class OllamaAskTests(unittest.TestCase):
    server: ThreadingHTTPServer

    @classmethod
    def setUpClass(cls):
        cls.server = QuietServer(("127.0.0.1", 0), FakeOllamaHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeOllamaHandler.counters.clear()
        FakeOllamaHandler.models_response = FAKE_MODELS
        ollama_ask._TAGS_CACHE.clear()
        self._orig_free_ram = ollama_ask.free_ram_bytes
        ollama_ask.free_ram_bytes = lambda: 8_000_000_000
        self._saved_env = dict(os.environ)
        for key in list(os.environ):
            if key.startswith("OLLAMA"):
                del os.environ[key]
        self._tmp = tempfile.mkdtemp(prefix="ollama_ask_test_")
        os.environ["OLLAMA_HOST"] = f"http://127.0.0.1:{self.port}"
        os.environ["HOME"] = self._tmp
        os.environ["USERPROFILE"] = self._tmp
        self._saved_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._saved_cwd)
        ollama_ask.free_ram_bytes = self._orig_free_ram
        os.environ.clear()
        os.environ.update(self._saved_env)
        rmtree_force(self._tmp)

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ollama_ask.main(list(argv) + ["--quiet"])
        return code, out.getvalue(), err.getvalue()

    def run_stdin(self, text: str, *argv: str) -> tuple[int, str, str]:
        FakeOllamaHandler.generate_calls = 0
        FakeOllamaHandler.prompts = []
        saved = sys.stdin
        sys.stdin = io.StringIO(text)
        try:
            return self.run_cli(*argv)
        finally:
            sys.stdin = saved

    def resolved(self, *argv: str) -> dict:
        code, out, err = self.run_cli("models", "--json", *argv)
        self.assertEqual(code, 0, msg=err)
        return json.loads(out)

    DEVSTRAL = "devstral-small-2:latest"

    # -- model resolution ---------------------------------------------------

    def test_resolve_model_flag_wins(self):
        data = self.resolved("--model", "flag-model")
        self.assertEqual(data["tasks"]["general"]["model"], "flag-model")
        self.assertEqual(data["tasks"]["general"]["source"], "flag")

    def test_resolve_model_env_task_beats_env_default(self):
        os.environ["OLLAMA_SKILLS_MODEL"] = "default-model"
        os.environ["OLLAMA_SKILLS_MODEL_COMMIT"] = "commit-model"
        data = self.resolved()
        self.assertEqual(data["tasks"]["commit"]["model"], "commit-model")
        self.assertEqual(data["tasks"]["general"]["model"], "default-model")

    def test_resolve_model_project_config_beats_user_config(self):
        (Path(self._tmp) / ".ollama-skills.json").write_text(
            json.dumps({"tasks": {"commit": {"model": "user-model"}}}), encoding="utf-8")
        project = Path(self._tmp) / "project"
        project.mkdir()
        (project / ".ollama-skills.json").write_text(
            json.dumps({"tasks": {"commit": {"model": "project-model"}}}), encoding="utf-8")
        os.chdir(project)
        data = self.resolved()
        self.assertEqual(data["tasks"]["commit"]["model"], "project-model")

    def test_config_with_utf8_bom_is_read(self):
        """PowerShell's Out-File -Encoding utf8 writes a BOM; must still parse."""
        config = json.dumps({"tasks": {"commit": {"model": "bom-model"}}})
        (Path(self._tmp) / ".ollama-skills.json").write_bytes(
            b"\xef\xbb\xbf" + config.encode("utf-8"))
        data = self.resolved()
        self.assertEqual(data["tasks"]["commit"]["model"], "bom-model")
        self.assertEqual(data["tasks"]["commit"]["source"], "config")

    def test_resolve_model_autodetect_prefers_commit_list(self):
        data = self.resolved()
        self.assertEqual(data["tasks"]["commit"]["model"], "llama3.2:1b")
        self.assertEqual(data["tasks"]["commit"]["source"], "auto")

    def test_resolve_model_summarize_qwen3_is_last_resort(self):
        """summarize must not auto-pick the slow qwen3:8b when a fast model
        exists; qwen3 is only a last resort (prefer --model qwen3:8b)."""
        cfg = {"tasks": {}, "host": os.environ["OLLAMA_HOST"]}
        # qwen3:8b present alongside a fast fallback -> the fast model wins.
        model, source = ollama_ask.resolve_model(
            "summarize", cfg, None, {"models": ["qwen3:8b", "mistral:7b"]})
        self.assertEqual(model, "mistral:7b")
        self.assertEqual(source, "auto")
        # qwen3:8b alone -> still picked, as the documented last resort.
        model, _ = ollama_ask.resolve_model(
            "summarize", cfg, None, {"models": ["qwen3:8b"]})
        self.assertEqual(model, "qwen3:8b")

    def test_resolve_model_general_matches_gemma2(self):
        """Regression: a coder+gemma2 fleet must not dead-end 'general'
        (it did before gemma2 joined PREFERENCES), and a coder-only fleet
        must still resolve via the qwen2.5-coder floor."""
        cfg = {"tasks": {}, "host": os.environ["OLLAMA_HOST"]}
        model, source = ollama_ask.resolve_model(
            "general", cfg, None,
            {"models": ["qwen2.5-coder:1.5b", "gemma2:2b"]})
        self.assertEqual(model, "gemma2:2b")
        self.assertEqual(source, "auto")
        model, _ = ollama_ask.resolve_model(
            "general", cfg, None, {"models": ["qwen2.5-coder:1.5b"]})
        self.assertEqual(model, "qwen2.5-coder:1.5b")

    def test_resolve_model_summarize_prefers_gemma2_over_coder(self):
        """summarize digests logs; the general model must beat the coder."""
        cfg = {"tasks": {}, "host": os.environ["OLLAMA_HOST"]}
        model, _ = ollama_ask.resolve_model(
            "summarize", cfg, None,
            {"models": ["qwen2.5-coder:1.5b", "gemma2:2b"]})
        self.assertEqual(model, "gemma2:2b")

    def test_ram_gate_skips_oversized_auto(self):
        """An oversized model earlier in preference is skipped; the scan
        continues to a model that fits."""
        cfg = {"tasks": {}, "host": os.environ["OLLAMA_HOST"]}
        cache = {
            "models": [self.DEVSTRAL, "gemma2:2b"],
            "sizes": {self.DEVSTRAL: 15_177_374_099,
                      "gemma2:2b": 1_629_518_495},
            "free_ram": 8_000_000_000,
        }
        model, source = ollama_ask.resolve_model("code", cfg, None, cache)
        self.assertEqual(model, "gemma2:2b")
        self.assertEqual(source, "auto")

    def test_ram_gate_all_gated_exits_4(self):
        cfg = {"tasks": {}, "host": os.environ["OLLAMA_HOST"]}
        cache = {
            "models": [self.DEVSTRAL],
            "sizes": {self.DEVSTRAL: 15_177_374_099},
            "free_ram": 8_000_000_000,
        }
        with self.assertRaises(ollama_ask.CliError) as ctx:
            ollama_ask.resolve_model("code", cfg, None, cache)
        self.assertEqual(ctx.exception.code, ollama_ask.EXIT_NO_MODEL)
        message = str(ctx.exception)
        self.assertIn(self.DEVSTRAL, message)
        self.assertIn("15.2 GB", message)
        self.assertIn("8.0 GB", message)
        self.assertIn("--model", message)

    def test_ram_gate_pinned_model_bypasses(self):
        """Explicit picks are never gated: pinning is the informed override."""
        cfg = {"tasks": {}, "host": os.environ["OLLAMA_HOST"]}
        cache = {
            "models": [self.DEVSTRAL],
            "sizes": {self.DEVSTRAL: 15_177_374_099},
            "free_ram": 8_000_000_000,
        }
        model, source = ollama_ask.resolve_model(
            "code", cfg, self.DEVSTRAL, cache)
        self.assertEqual((model, source), (self.DEVSTRAL, "flag"))

    def test_ram_gate_no_sizes_no_gate(self):
        """A cache seeded without sizes (how other tests seed it) never
        gates — the gate stands down without data."""
        cfg = {"tasks": {}, "host": os.environ["OLLAMA_HOST"]}
        model, source = ollama_ask.resolve_model(
            "code", cfg, None, {"models": [self.DEVSTRAL]})
        self.assertEqual(model, self.DEVSTRAL)
        self.assertEqual(source, "auto")

    def test_models_reports_skips(self):
        FakeOllamaHandler.models_response = FAKE_MODELS + [
            {"name": self.DEVSTRAL, "size": 15_177_374_099},
        ]
        code, out, err = self.run_cli("models")
        self.assertEqual(code, 0, msg=err)
        self.assertIn(
            "skipped devstral-small-2:latest for code "
            "(15.2 GB > 8.0 GB free RAM)", out)
        code, out, err = self.run_cli("models", "--json")
        self.assertEqual(code, 0, msg=err)
        data = json.loads(out)
        self.assertEqual(data["skipped"], [{
            "model": self.DEVSTRAL, "size": 15_177_374_099,
            "free_ram": 8_000_000_000, "tasks": ["code"]}])

    # -- ask ----------------------------------------------------------------

    def test_ask_returns_text_and_exit_0(self):
        code, out, _ = self.run_cli("ask", "hello there")
        self.assertEqual(code, 0)
        self.assertIn(CANNED_TEXT, out)

    def test_ask_strips_think_block(self):
        code, out, _ = self.run_cli("ask", "THINKBLOCK please")
        self.assertEqual(code, 0)
        self.assertNotIn("<think>", out)
        self.assertNotIn("secret reasoning", out)
        self.assertIn(CANNED_TEXT, out)

    def test_think_field_retry_on_400(self):
        code, out, _ = self.run_cli("ask", "hello", "--model", "no-think-model")
        self.assertEqual(code, 0)
        self.assertIn(CANNED_TEXT, out)

    def test_stall_detection_exits_5(self):
        code, _, err = self.run_cli("ask", "SLOWSTALL now", "--stall-seconds", "1")
        self.assertEqual(code, 5)
        self.assertIn("stall", err.lower())

    def test_budget_refusal_exits_2(self):
        code, _, err = self.run_cli("ask", "x" * 3000)
        self.assertEqual(code, 2)
        self.assertIn("budget", err.lower())

    def test_budget_force_allows(self):
        code, out, _ = self.run_cli("ask", "x" * 3000, "--force")
        self.assertEqual(code, 0)
        self.assertIn(CANNED_TEXT, out)

    def test_json_object_mode_validates(self):
        code, out, _ = self.run_cli("ask", "BADJSON please", "--json-object")
        self.assertEqual(code, 0)
        json.loads(out)  # must parse

    # -- draft-command ------------------------------------------------------

    def test_draft_command_outputs_json_with_command_key(self):
        code, out, _ = self.run_cli("draft-command", "list files")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["command"])
        self.assertIn("explanation", data)

    # -- commit-msg ---------------------------------------------------------

    def _make_repo(self, staged: bool) -> Path:
        repo = Path(self._tmp) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        if staged:
            (repo / "upload.py").write_text(
                "def upload():\n    return 'SECRETMARKER123'\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
        os.chdir(repo)
        return repo

    def test_commit_msg_empty_staged_exits_2(self):
        self._make_repo(staged=False)
        code, _, err = self.run_cli("commit-msg")
        self.assertEqual(code, 2)
        self.assertIn("staged", err.lower())

    def test_commit_msg_generates_conventional(self):
        self._make_repo(staged=True)
        code, out, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        self.assertRegex(
            out.strip().splitlines()[0],
            r"^(feat|fix|build|chore|ci|docs|style|refactor|perf|test)"
            r"(\([\w\-\./]+\))?(!)?: .{1,72}$")

    def test_commit_msg_diff_never_in_output(self):
        self._make_repo(staged=True)
        code, out, _ = self.run_cli("commit-msg")
        self.assertEqual(code, 0)
        self.assertNotIn("SECRETMARKER123", out)

    # -- draft-code ---------------------------------------------------------

    def test_draft_code_strips_fences(self):
        code, out, _ = self.run_cli("draft-code", "--spec", "CODEBLOCK print hi",
                                    "--lang", "python")
        self.assertEqual(code, 0)
        self.assertNotIn("```", out)
        self.assertIn("print('hi')", out)

    # -- fix-lint -----------------------------------------------------------

    def test_fix_lint_outputs_suggestion_and_never_writes(self):
        target = Path(self._tmp) / "mod.py"
        original = "import os\nprint('x')\n"
        target.write_text(original, encoding="utf-8")
        code, out, _ = self.run_cli(
            "fix-lint", "--file", str(target), "--line", "1",
            "--error", "SUGGESTFIX F401 'os' imported but unused")
        self.assertEqual(code, 0)
        self.assertIn("<<<<<<< SEARCH", out)
        self.assertIn("WHY:", out)
        self.assertEqual(target.read_text(encoding="utf-8"), original)

    # -- health / errors ----------------------------------------------------

    def test_health_reports_models(self):
        code, out, _ = self.run_cli("health")
        self.assertEqual(code, 0)
        self.assertIn("qwen3:8b", out)
        self.assertIn("0.0-test", out)

    def test_unreachable_exits_3(self):
        # A bound-but-not-listening socket refuses connections deterministically.
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", 0))
        try:
            port = blocker.getsockname()[1]
            os.environ["OLLAMA_HOST"] = f"http://127.0.0.1:{port}"
            code, _, err = self.run_cli("health")
            self.assertEqual(code, 3)
            self.assertIn("running", err.lower())
        finally:
            blocker.close()

    def test_missing_model_exits_4(self):
        code, _, err = self.run_cli("ask", "hello", "--model", "missing-model")
        self.assertEqual(code, 4)
        self.assertIn("pull", err.lower())

    # -- validation-failure and robustness paths ------------------------------

    def test_commit_msg_invalid_twice_exits_6(self):
        repo = Path(self._tmp) / "repo6"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "notes.txt").write_text("BADCOMMIT marker\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        os.chdir(repo)
        code, _, err = self.run_cli("commit-msg")
        self.assertEqual(code, 6)
        self.assertIn("cannot help", err.lower())  # raw output surfaced on stderr

    def test_fix_lint_skip_path(self):
        target = Path(self._tmp) / "skipme.py"
        target.write_text("import os\n", encoding="utf-8")
        code, out, _ = self.run_cli(
            "fix-lint", "--file", str(target), "--line", "1",
            "--error", "SKIPFIX E501 line too long")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "SKIP")

    def test_payload_pins_think_false_and_defaults(self):
        code, _, _ = self.run_cli("ask", "hello there")
        self.assertEqual(code, 0)
        payload = FakeOllamaHandler.last_payload
        self.assertIs(payload.get("think"), False)
        self.assertEqual(payload["options"]["num_predict"], 256)  # 'general' default
        self.assertEqual(payload.get("keep_alive"), "30m")

    def test_json_object_sets_format(self):
        code, _, _ = self.run_cli("ask", "give json", "--json-object")
        self.assertEqual(code, 0)
        self.assertEqual(FakeOllamaHandler.last_payload.get("format"), "json")

    def test_staged_lockfiles_excluded_from_prompt(self):
        repo = Path(self._tmp) / "repolock"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "package-lock.json").write_text(
            '{"comment": "LOCKMARKER999"}\n', encoding="utf-8")
        (repo / "app.py").write_text("print('SRCMARKER777')\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        os.chdir(repo)
        code, _, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        prompt = FakeOllamaHandler.last_payload.get("prompt", "")
        self.assertNotIn("LOCKMARKER999", prompt)  # lockfile content stays out
        self.assertIn("SRCMARKER777", prompt)      # real source goes in

    def test_subprocess_pipe_nonascii_is_safe(self):
        """Regression: Windows pipes default to the ANSI codepage and crashed
        on non-ASCII model output before main() forced UTF-8."""
        env = dict(os.environ)
        env.pop("PYTHONUTF8", None)
        env.pop("PYTHONIOENCODING", None)
        script = ROOT / "scripts" / "ollama_ask.py"
        result = subprocess.run(
            [sys.executable, str(script), "ask", "NONASCII please", "--quiet"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=60,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("done", result.stdout)

    # -- summarize ----------------------------------------------------------

    def test_summarize_single_shot_one_call(self):
        code, out, err = self.run_stdin("line one\nline two\nline three\n",
                                        "summarize", "--kind", "log")
        self.assertEqual(code, 0, msg=err)
        self.assertIn(CANNED_TEXT, out)
        self.assertEqual(FakeOllamaHandler.generate_calls, 1)  # no map stage

    def test_summarize_map_reduce_multiple_calls(self):
        big = "\n".join(f"event number {i} happened on host node-{i}" for i in range(400))
        code, out, err = self.run_stdin(big, "summarize", "--kind", "events", "--no-dedupe")
        self.assertEqual(code, 0, msg=err)
        self.assertGreater(FakeOllamaHandler.generate_calls, 1)  # map + reduce

    def test_summarize_dedupe_collapses_repeats(self):
        repeated = "\n".join("ERROR connection refused to db" for _ in range(500))
        code, out, err = self.run_stdin(repeated, "summarize", "--kind", "log")
        self.assertEqual(code, 0, msg=err)
        prompt = FakeOllamaHandler.last_payload.get("prompt", "")
        self.assertIn("500×", prompt)  # collapsed to "500x <line>"
        self.assertEqual(FakeOllamaHandler.generate_calls, 1)  # collapse -> single-shot

    def test_summarize_no_dedupe_keeps_repeats(self):
        repeated = "\n".join("ERROR connection refused to db" for _ in range(500))
        code, _, err = self.run_stdin(repeated, "summarize", "--kind", "log", "--no-dedupe")
        self.assertEqual(code, 0, msg=err)
        # 500 identical 30-char lines ~ 15 KB > 3000-char chunk -> map stage runs
        self.assertGreater(FakeOllamaHandler.generate_calls, 1)

    def test_summarize_over_ceiling_exits_2(self):
        code, _, err = self.run_stdin("x" * 500, "summarize", "--ceiling-chars", "100")
        self.assertEqual(code, 2)
        self.assertIn("ceiling", err.lower())

    def test_summarize_ceiling_force_allows(self):
        code, out, err = self.run_stdin("x" * 500, "summarize",
                                        "--ceiling-chars", "100", "--force")
        self.assertEqual(code, 0, msg=err)

    def test_summarize_empty_input_exits_2(self):
        code, _, err = self.run_stdin("   \n  \n", "summarize")
        self.assertEqual(code, 2)
        self.assertIn("no input", err.lower())

    def test_summarize_verdict_default_and_no_verdict_flag(self):
        self.run_stdin("a\nb\nc\n", "summarize", "--kind", "log")
        self.assertIn("VERDICT", FakeOllamaHandler.last_payload.get("system", ""))
        self.run_stdin("a\nb\nc\n", "summarize", "--kind", "log", "--no-verdict")
        self.assertNotIn("VERDICT", FakeOllamaHandler.last_payload.get("system", ""))

    def test_summarize_pins_num_ctx(self):
        self.run_stdin("a\nb\nc\n", "summarize", "--kind", "log")
        self.assertEqual(FakeOllamaHandler.last_payload["options"].get("num_ctx"), 2048)

    def test_summarize_dropped_chunk_marker_partial_success(self):
        # Many normal lines + one chunk carrying SLOWSTALL; that chunk is dropped,
        # the rest still summarize -> exit 0 with an inline dropped marker.
        lines = [f"normal log line {i} on host abc" for i in range(300)]
        lines[150] = "SLOWSTALL trigger on this chunk"
        code, out, err = self.run_stdin("\n".join(lines), "summarize",
                                        "--kind", "log", "--no-dedupe", "--stall-seconds", "1")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("dropped", out.lower())

    def test_summarize_all_chunks_stall_exits_5(self):
        # Single stalling chunk (fits one chunk) -> all dropped, all stalls -> exit 5.
        code, _, err = self.run_stdin("SLOWSTALL only", "summarize",
                                      "--kind", "log", "--stall-seconds", "1")
        self.assertEqual(code, 5)

    # -- fixtures (kubectl / docker stand-ins) ------------------------------

    def _fixture(self, *parts) -> str:
        return (ROOT / "tests" / "fixtures" / Path(*parts)).read_text(encoding="utf-8")

    def test_summarize_kubectl_and_docker_fixtures_run(self):
        cases = [
            (("kubectl", "describe-pod-crashloop.txt"), "describe"),
            (("kubectl", "events.txt"), "events"),
            (("kubectl", "logs-crashloop.txt"), "log"),
            (("docker", "logs-crashloop.txt"), "log"),
        ]
        for parts, kind in cases:
            code, out, err = self.run_stdin(self._fixture(*parts),
                                            "summarize", "--kind", kind)
            self.assertEqual(code, 0, msg=f"{parts}: {err}")

    def test_summarize_describe_drops_env_block(self):
        text = self._fixture("kubectl", "describe-pod-crashloop.txt")
        self.run_stdin(text, "summarize", "--kind", "describe", "--chunk-chars", "500")
        sent = "\n".join(FakeOllamaHandler.prompts)
        self.assertNotIn("SECRET_TOKEN_ENVMARKER", sent)  # Env block pruned before model
        self.assertIn("Conditions", sent)                 # kept the useful section

    def test_kubectl_no_context_fixture_present(self):
        self.assertIn("current-context", self._fixture("kubectl", "no-context.txt").lower())

    def test_get_pods_json_fixture_parses(self):
        json.loads(self._fixture("kubectl", "get-pods.json"))  # must be valid JSON

    def test_draft_code_yaml_and_dockerfile_fence_free(self):
        for lang in ("yaml", "dockerfile"):
            code, out, err = self.run_cli("draft-code", "--spec", "CODEBLOCK make it",
                                          "--lang", lang)
            self.assertEqual(code, 0, msg=err)
            self.assertNotIn("```", out)

    # -- commit-push (gated commit + push) -----------------------------------

    def _make_push_repo(self, stage: bool = True):
        """Work repo + a local bare remote; nothing committed yet (unborn HEAD).

        No network involved: the "remote" is a second temp dir initialized with
        `git init --bare`. Both dirs live under self._tmp, so tearDown's
        rmtree_force(self._tmp) cleans them up.
        """
        work = Path(self._tmp) / "push_work"
        bare = Path(self._tmp) / "push_bare.git"
        work.mkdir()
        bare.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=work, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"],
                       cwd=work, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=work, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=work, check=True)
        subprocess.run(["git", "init", "--bare", "-q"], cwd=bare, check=True)
        subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=work, check=True)
        if stage:
            (work / "file.txt").write_text("hello\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=work, check=True)
        os.chdir(work)
        return work, bare

    def _local_commit_count(self, work: Path) -> int:
        result = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=work,
                                capture_output=True, text=True)
        return int(result.stdout.strip()) if result.returncode == 0 else 0

    def _bare_commit_count(self, bare: Path, ref: str) -> int:
        result = subprocess.run(
            ["git", "--git-dir", str(bare), "rev-list", "--count", ref],
            capture_output=True, text=True)
        return int(result.stdout.strip()) if result.returncode == 0 else 0

    def test_commit_push_non_protected_branch_succeeds(self):
        work, bare = self._make_push_repo()
        subprocess.run(["git", "branch", "-m", "work"], cwd=work, check=True)
        code, out, err = self.run_cli("commit-push", "--message", "test: add x")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(self._local_commit_count(work), 1)
        # The bare remote's own HEAD still points at its (never-created) default
        # branch, so ask for the pushed ref by name rather than relying on HEAD.
        log = subprocess.run(["git", "--git-dir", str(bare), "log", "--oneline", "work"],
                            capture_output=True, text=True, check=True).stdout
        self.assertIn("test: add x", log)

    def test_commit_push_protected_branch_without_allow_exits_7(self):
        work, bare = self._make_push_repo()
        subprocess.run(["git", "branch", "-m", "main"], cwd=work, check=True)
        code, out, err = self.run_cli("commit-push", "--message", "test: add x")
        self.assertEqual(code, 7, msg=err)
        self.assertIn("protected", err.lower())
        self.assertEqual(self._local_commit_count(work), 0)         # HEAD did not advance
        self.assertEqual(self._bare_commit_count(bare, "main"), 0)  # remote got nothing

    def test_commit_push_protected_branch_with_allow_succeeds(self):
        work, bare = self._make_push_repo()
        subprocess.run(["git", "branch", "-m", "main"], cwd=work, check=True)
        code, out, err = self.run_cli("commit-push", "--message", "test: allow main",
                                      "--allow-protected")
        self.assertEqual(code, 0, msg=err)
        local_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work,
                                   capture_output=True, text=True,
                                   check=True).stdout.strip()
        remote_sha = subprocess.run(["git", "--git-dir", str(bare), "rev-parse", "main"],
                                    capture_output=True, text=True,
                                    check=True).stdout.strip()
        self.assertEqual(local_sha, remote_sha)

    def test_commit_push_nothing_staged_exits_2(self):
        work, _bare = self._make_push_repo(stage=False)
        subprocess.run(["git", "branch", "-m", "work"], cwd=work, check=True)
        code, out, err = self.run_cli("commit-push", "--message", "test: nothing")
        self.assertEqual(code, 2, msg=err)
        self.assertIn("staged", err.lower())
        self.assertEqual(self._local_commit_count(work), 0)

    def test_commit_push_not_a_git_repo_exits_2(self):
        notrepo = Path(self._tmp) / "notrepo"
        notrepo.mkdir()
        os.chdir(notrepo)
        code, out, err = self.run_cli("commit-push", "--message", "test: nope")
        self.assertEqual(code, 2, msg=err)
        self.assertIn("git repository", err.lower())

    def test_commit_push_detached_head_exits_2(self):
        """Supplemental beyond the mandated 5 cases: confirms the detached-HEAD
        refusal. This repo detects the branch with `git symbolic-ref --short
        HEAD`, not the more common `rev-parse --abbrev-ref HEAD` idiom, because
        the installed git fails the latter with exit 128 on an UNBORN branch
        (verified empirically) -- which is exactly the starting state of every
        case above (staged but not yet committed). symbolic-ref succeeds on an
        unborn branch and fails only when HEAD is genuinely detached, so it is
        the one primitive that satisfies both this case and cases 1-4."""
        work, _bare = self._make_push_repo()
        subprocess.run(["git", "branch", "-m", "work"], cwd=work, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=work, check=True)
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work,
                             capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["git", "checkout", "-q", sha], cwd=work, check=True)
        (work / "file2.txt").write_text("second\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True)
        code, out, err = self.run_cli("commit-push", "--message", "test: detached")
        self.assertEqual(code, 2, msg=err)
        self.assertIn("detached", err.lower())

    # -- deny-list coverage (skill/agent safety wording) --------------------

    def test_denylist_covers_container_cluster_history(self):
        needles = [
            "docker system prune", "docker volume rm", "docker compose down -v",
            "--privileged", "kubectl delete namespace", "kubectl delete pvc",
            "--all-namespaces", "kubectl drain", "kubectl edit",
            "kubectl config use-context", "git rebase", "git filter-branch",
        ]
        for rel in ("skills/ollama-shell/SKILL.md", "agents/ollama-ops.md"):
            body = (ROOT / rel).read_text(encoding="utf-8")
            for needle in needles:
                self.assertIn(needle, body, msg=f"{needle!r} missing from {rel}")

    def test_denylist_covers_ollama_docker(self):
        needles = [
            "docker system prune", "docker volume rm", "docker compose down -v",
            "--privileged", "cloud metadata endpoints", "docker rm $(docker ps -aq)",
        ]
        rel = "skills/ollama-docker/SKILL.md"
        body = (ROOT / rel).read_text(encoding="utf-8")
        for needle in needles:
            self.assertIn(needle, body, msg=f"{needle!r} missing from {rel}")

    def test_denylist_covers_ollama_k8s(self):
        needles = [
            "kubectl delete namespace", "kubectl delete pvc", "kubectl drain",
            "kubectl replace --force", "ClusterRoleBinding", "base64-decoding secret data",
        ]
        rel = "skills/ollama-k8s/SKILL.md"
        body = (ROOT / rel).read_text(encoding="utf-8")
        for needle in needles:
            self.assertIn(needle, body, msg=f"{needle!r} missing from {rel}")

    def test_git_history_skill_bans_patches(self):
        """ollama-git-history must keep its no-patch privacy rule; a silent
        reword that dropped these needles would defeat the skill's purpose."""
        needles = [
            "git log -p", "--patch", "--word-diff", "--full-diff",
            "never shows patch content",
        ]
        rel = "skills/ollama-git-history/SKILL.md"
        body = (ROOT / rel).read_text(encoding="utf-8")
        for needle in needles:
            self.assertIn(needle, body, msg=f"{needle!r} missing from {rel}")

    def test_commit_push_born_attached_branch_succeeds(self):
        # The common real-world shape the other commit-push tests miss: a
        # branch with history and HEAD attached (not unborn, not detached).
        work, bare = self._make_push_repo(stage=False)
        subprocess.run(["git", "branch", "-m", "work"], cwd=work, check=True)
        (work / "one.txt").write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "chore: seed"],
                       cwd=work, check=True)
        (work / "two.txt").write_text("two\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True)
        code, out, err = self.run_cli("commit-push", "--message", "feat: add two")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(self._local_commit_count(work), 2)
        self.assertEqual(self._bare_commit_count(bare, "work"), 2)

    def test_push_safety_wording_present(self):
        # A silent reword dropping the gate wording would defeat commit-push's
        # safety story; both the skill and the agent must keep it.
        needles = [
            "never the model", "--force-with-lease",
            "delete a remote branch", "protected branch",
        ]
        for rel in ("skills/ollama-commit/SKILL.md", "agents/ollama-git.md"):
            body = (ROOT / rel).read_text(encoding="utf-8")
            for needle in needles:
                self.assertIn(needle, body, msg=f"{needle!r} missing from {rel}")


if __name__ == "__main__":
    unittest.main()
