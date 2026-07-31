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
CANNED_PR_JSON = ('{"title": "feat: add retry logic", '
                  '"body": "- adds a retry loop to uploads"}')
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
    models_seen: list = []
    tags_calls: int = 0
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
            FakeOllamaHandler.tags_calls += 1
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
            FakeOllamaHandler.models_seen.append(payload.get("model", ""))
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
        elif "SKIPRETRY" in prompt:
            key = "skipretry"
            FakeOllamaHandler.counters[key] = FakeOllamaHandler.counters.get(key, 0) + 1
            text = ("no suggestion markers here"
                    if FakeOllamaHandler.counters[key] == 1 else "SKIP")
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
        elif "INVALID_JSON_PLEASE" in prompt:
            text = "this is not json at all"
        elif "pull request descriptions" in prompt:
            text = CANNED_PR_JSON
        elif "ALWAYSWRONGTYPE" in prompt:
            text = "fix: update stuff"
        elif "WRONGTYPEONCE" in prompt:
            key = "wrongtype"
            FakeOllamaHandler.counters[key] = FakeOllamaHandler.counters.get(key, 0) + 1
            text = ("fix: update stuff" if FakeOllamaHandler.counters[key] == 1
                    else "docs: update the guides")
        elif "SCOPEDRAFTONCE" in prompt:
            key = "scopedraft"
            FakeOllamaHandler.counters[key] = FakeOllamaHandler.counters.get(key, 0) + 1
            text = ("docs(readme.md): update the guides"
                    if FakeOllamaHandler.counters[key] == 1
                    else "docs: update the guides")
        elif "SCOPEDWRONGONCE" in prompt:
            key = "scopedwrong"
            FakeOllamaHandler.counters[key] = FakeOllamaHandler.counters.get(key, 0) + 1
            text = ("fix(readme.md): tweak"
                    if FakeOllamaHandler.counters[key] == 1
                    else "docs: update the guides")
        elif "LONGLINEONCE" in prompt:
            key = "longline"
            FakeOllamaHandler.counters[key] = FakeOllamaHandler.counters.get(key, 0) + 1
            text = ("feat: " + "x" * 80 if FakeOllamaHandler.counters[key] == 1
                    else CANNED_TEXT)
        elif "ALWAYSSCOPED" in prompt:
            text = "docs(readme.md): update the guides"
        elif "suggested type: docs" in prompt:
            text = "docs: update the guides"
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
        # Tests must never write a usage ledger into the real repo or home.
        # Usage tests opt back in explicitly by deleting this key.
        os.environ["OLLAMA_SKILLS_NO_USAGE"] = "1"
        ollama_ask._USAGE_RECORDS.clear()
        ollama_ask._USAGE_CTX.update(
            {"cmd": None, "avoided_chars": 0, "hinted": False})
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
        FakeOllamaHandler.models_seen = []
        FakeOllamaHandler.tags_calls = 0
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

    def test_require_git_repo_raises_outside_repo(self):
        with tempfile.TemporaryDirectory() as td:
            old = os.getcwd()
            os.chdir(td)
            try:
                with self.assertRaises(ollama_ask.CliError) as ctx:
                    ollama_ask._require_git_repo()
            finally:
                os.chdir(old)
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(str(ctx.exception), "Not inside a git repository.")

    def test_require_current_branch_refuses_detached_head(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "init", "-q", td], check=True)
            env_dir = Path(td)
            (env_dir / "f.txt").write_text("x", encoding="utf-8")
            subprocess.run(["git", "-C", td, "add", "."], check=True)
            subprocess.run(["git", "-C", td, "-c", "user.email=t@t", "-c",
                            "user.name=t", "commit", "-q", "-m", "seed"], check=True)
            sha = subprocess.run(["git", "-C", td, "rev-parse", "HEAD"],
                                 capture_output=True, text=True, check=True).stdout.strip()
            subprocess.run(["git", "-C", td, "checkout", "-q", sha], check=True)
            old = os.getcwd()
            os.chdir(td)
            try:
                with self.assertRaises(ollama_ask.CliError) as ctx:
                    ollama_ask._require_current_branch()
            finally:
                os.chdir(old)
        self.assertEqual(ctx.exception.code, 2)

    def test_resolve_remote_missing_remote_raises(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "init", "-q", td], check=True)
            old = os.getcwd()
            os.chdir(td)
            try:
                with self.assertRaises(ollama_ask.CliError) as ctx:
                    ollama_ask._resolve_remote(None, "")
            finally:
                os.chdir(old)
        self.assertEqual(str(ctx.exception), "Remote 'origin' not found.")

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

    def test_draft_command_double_bad_json_two_calls_exit_6(self):
        """Pin the ceiling: two malformed-JSON drafts in a row must stop at
        exactly two /api/generate calls and exit 6, not loop further."""
        FakeOllamaHandler.generate_calls = 0
        code, out, err = self.run_cli("draft-command", "INVALID_JSON_PLEASE task")
        self.assertEqual(code, 6, msg=err)
        self.assertEqual(FakeOllamaHandler.generate_calls, 2)

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

    def test_change_kind_uniform_kinds(self):
        line, t = ollama_ask._change_kind(["docs/a.md", "README.md"])
        self.assertEqual(t, "docs")
        self.assertIn("2 markdown docs", line)
        self.assertIn("suggested type: docs", line)
        _line, t = ollama_ask._change_kind([".github/workflows/ci.yml"])
        self.assertEqual(t, "ci")
        _line, t = ollama_ask._change_kind(["tests/test_x.py"])
        self.assertEqual(t, "test")
        _line, t = ollama_ask._change_kind(
            [".claude-plugin/plugin.json", "config/x.json"])
        self.assertEqual(t, "chore")

    def test_change_kind_mixed_and_behavior_none(self):
        _line, t = ollama_ask._change_kind(["skills/ollama-pr/SKILL.md"])
        self.assertIsNone(t)   # prompt contracts are behavior, NOT docs
        _line, t = ollama_ask._change_kind(["scripts/ollama_ask.py"])
        self.assertIsNone(t)   # code: the model and Claude decide
        line, t = ollama_ask._change_kind(["docs/a.md", "scripts/x.py"])
        self.assertIsNone(t)   # mixed kinds -> no suggestion
        self.assertNotIn("suggested type", line)
        line, t = ollama_ask._change_kind(["docs/gen.py"])
        self.assertIsNone(t)   # docs/ arm requires a .md base; .py falls to code
        self.assertIn("code", line)

    def test_change_kind_all_lockfiles_excluded(self):
        line, t = ollama_ask._change_kind([])
        self.assertEqual(line, "File kinds: lockfiles only (excluded from excerpts)")
        self.assertIsNone(t)

    def test_semantic_problem_cases(self):
        # -- first-attempt (retry-feedback) checks: final=False (default) --
        self.assertIsNone(ollama_ask._semantic_problem("docs: update x", "docs"))
        self.assertIn("contradicts",
                      ollama_ask._semantic_problem("fix: update x", "docs"))
        self.assertIn("filename",
                      ollama_ask._semantic_problem("docs(readme.md): x", None))
        self.assertIn("filename",
                      ollama_ask._semantic_problem("fix(scripts/a.py): x", None))
        # a non-path-shaped scope is now also a (non-fatal) retry complaint,
        # just with different wording than the filename accusation.
        self.assertIn("drop the scope",
                      ollama_ask._semantic_problem("feat(parser): x", None))
        self.assertIsNone(ollama_ask._semantic_problem("not a commit line", "docs"))

        # -- equivalence sets: build satisfies chore/ci on the FIRST attempt too --
        self.assertIsNone(ollama_ask._semantic_problem("build: bump deps", "chore"))
        self.assertIsNone(ollama_ask._semantic_problem("build: update pipeline", "ci"))
        self.assertIn("contradicts",
                      ollama_ask._semantic_problem("chore: bump deps", "ci"))

        # -- final gate: scope-only defects are never fatal --
        self.assertIsNone(
            ollama_ask._semantic_problem("docs(readme.md): x", "docs", final=True))
        self.assertIsNone(
            ollama_ask._semantic_problem("feat(parser): x", None, final=True))
        # -- final gate: a true type contradiction beyond equivalence stays fatal --
        self.assertIn("contradicts",
                      ollama_ask._semantic_problem("fix: update x", "docs", final=True))
        self.assertIsNone(
            ollama_ask._semantic_problem("build: bump deps", "chore", final=True))

        # -- both scope AND type wrong at once: joined into one complaint,
        # type first, so the single corrective retry can fix both --
        combined = ollama_ask._semantic_problem("fix(readme.md): x", "docs")
        self.assertIn("contradicts", combined)
        self.assertIn("filename", combined)
        self.assertLess(combined.index("contradicts"), combined.index("filename"))

        # -- stated=True: truthful wording when the type came from --type,
        # not from classifying the staged files --
        stated_complaint = ollama_ask._semantic_problem(
            "fix: update x", "docs", stated=True)
        self.assertIn("stated type", stated_complaint)
        # scope-only defects stay non-fatal regardless of stated=
        self.assertIn("drop the scope",
                      ollama_ask._semantic_problem("feat(parser): x", None, stated=True))

    def _make_docs_repo(self):
        repo = Path(self._tmp) / "docsrepo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "README.md").write_text("# hello\n", encoding="utf-8")
        (repo / "docs").mkdir()
        (repo / "docs" / "note.md").write_text("note\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        os.chdir(repo)
        return repo

    def test_commit_msg_prompt_leads_with_kind_line(self):
        self._make_docs_repo()
        FakeOllamaHandler.prompts = []
        code, out, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        self.assertTrue(out.startswith("docs:"), msg=out)
        body = FakeOllamaHandler.prompts[0]
        lines = body.splitlines()
        kind_line = lines[2]
        self.assertTrue(kind_line.startswith("File kinds:"), msg=lines[:4])
        self.assertIn("suggested type: docs", body)
        self.assertIn("Excerpts (reference only", body)
        # Privacy: the kind line itself is labels + counts only - no filenames.
        self.assertNotIn("/", kind_line)
        self.assertNotIn(".md", kind_line)

    def test_commit_msg_wrong_type_retried_and_corrected(self):
        repo = self._make_docs_repo()
        (repo / "docs" / "extra.md").write_text("WRONGTYPEONCE\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        code, out, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(out.strip(), "docs: update the guides")

    def test_commit_retry_makes_exactly_two_generate_calls(self):
        """Pin the one-corrective-retry policy: a format/semantic reject on
        attempt 1 must cost exactly one retry, never more."""
        repo = self._make_docs_repo()
        (repo / "docs" / "extra.md").write_text("WRONGTYPEONCE\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        FakeOllamaHandler.generate_calls = 0
        code, out, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(FakeOllamaHandler.generate_calls, 2)

    def test_commit_msg_filename_scope_retried(self):
        repo = self._make_docs_repo()
        (repo / "docs" / "extra.md").write_text("SCOPEDRAFTONCE\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        code, out, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(out.strip(), "docs: update the guides")

    def test_commit_msg_combined_type_and_scope_retry_feedback(self):
        """A draft with BOTH a filename scope and a type that contradicts the
        caller's stated --type must get ONE retry whose feedback mentions
        both defects, not just the scope - otherwise the retry can fix the
        scope alone and still land on exit 6 for the type."""
        repo = Path(self._tmp) / "combinedrepo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "a.py").write_text("print('x')\n", encoding="utf-8")
        (repo / "notes.md").write_text("SCOPEDWRONGONCE\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        os.chdir(repo)
        code, out, err = self.run_cli("commit-msg", "--type", "docs")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(out.strip(), "docs: update the guides")
        system = FakeOllamaHandler.last_payload.get("system", "")
        self.assertIn("stated type", system)
        self.assertIn("scope (readme.md)", system)

    def test_commit_msg_persistent_wrong_type_exits_6(self):
        repo = self._make_docs_repo()
        (repo / "docs" / "extra.md").write_text("ALWAYSWRONGTYPE\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        code, out, err = self.run_cli("commit-msg")
        self.assertEqual(code, 6, msg=err)

    def test_commit_double_reject_two_calls_then_exit_6(self):
        """Pin the ceiling: a draft that fails on both attempts must stop at
        exactly two /api/generate calls, not loop or retry a third time."""
        repo = self._make_docs_repo()
        (repo / "docs" / "extra.md").write_text("ALWAYSWRONGTYPE\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        FakeOllamaHandler.generate_calls = 0
        code, out, err = self.run_cli("commit-msg")
        self.assertEqual(code, 6, msg=err)
        self.assertEqual(FakeOllamaHandler.generate_calls, 2)

    def test_commit_msg_mixed_diff_scoped_draft_prints(self):
        """New contract: for a mixed staged mix (suggested is None), a
        scope-only defect that survives both attempts is PRINTED — Claude
        owns editing it — instead of exiting 6."""
        repo = Path(self._tmp) / "mixedrepo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "scripts").mkdir()
        (repo / "docs").mkdir()
        (repo / "scripts" / "x.py").write_text(
            "print('ALWAYSSCOPED')\n", encoding="utf-8")
        (repo / "docs" / "a.md").write_text(
            "ALWAYSSCOPED notes\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        os.chdir(repo)
        code, out, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(out.strip(), "docs(readme.md): update the guides")

    def test_staged_context_renames_sort_by_real_churn(self):
        """A renamed+edited file must not fall to churn 0 (and sort last):
        --numstat with default rename detection prints "old => new", which
        never matches a --name-only path. --no-renames forces an add+delete
        pair instead, so the new path gets credited with its real churn."""
        repo = Path(self._tmp) / "renamerepo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@e.st"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
        core_lines = "\n".join(f"line{i}" for i in range(30)) + "\n"
        (repo / "core.py").write_text(core_lines, encoding="utf-8")
        (repo / "tiny.txt").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
        subprocess.run(["git", "mv", "core.py", "engine.py"], cwd=repo, check=True)
        (repo / "engine.py").write_text(
            core_lines + "extra = 1  # ENGINE_MARKER\n", encoding="utf-8")
        (repo / "tiny.txt").write_text("hello\nasdf  # TINY_MARKER\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        os.chdir(repo)
        FakeOllamaHandler.prompts = []
        code, out, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        prompt = FakeOllamaHandler.prompts[0]
        self.assertIn("ENGINE_MARKER", prompt)
        self.assertIn("TINY_MARKER", prompt)
        self.assertLess(prompt.index("ENGINE_MARKER"), prompt.index("TINY_MARKER"))

    def test_staged_context_oversized_lead_file_still_yields_excerpt(self):
        """A single oversized lead file must not zero out every excerpt: the
        truncate-then-mark branch fits what it can before the "not shown"
        marker instead of appending only the marker and breaking empty."""
        repo = Path(self._tmp) / "bigrepo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        big_lines = "\n".join(
            f"x = {i}  # BIGFILEMARKER filler filler filler filler"
            for i in range(60))
        (repo / "big.py").write_text(big_lines + "\n", encoding="utf-8")
        (repo / "small.py").write_text("y = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        os.chdir(repo)
        FakeOllamaHandler.prompts = []
        code, out, err = self.run_cli(
            "commit-msg", "--max-input-chars", "800")
        self.assertEqual(code, 0, msg=err)
        prompt = FakeOllamaHandler.prompts[0]
        self.assertIn("BIGFILEMARKER", prompt)
        # The full marker must survive the [:limit] clamp - a clipped
        # "(more changes in x n" is the regression this test pins.
        self.assertIn("not shown)", prompt)

    # -- usage ledger --------------------------------------------------------

    def _read_ledger(self, repo: Path) -> list:
        path = repo / ".ollama-skills-usage.jsonl"
        self.assertTrue(path.is_file(), msg=f"no ledger at {path}")
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_usage_ledger_written_in_repo(self):
        repo = self._make_repo(staged=True)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        code, _, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        records = self._read_ledger(repo)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["v"], 1)
        self.assertEqual(rec["cmd"], "commit-msg")
        self.assertEqual(rec["task"], "commit")
        self.assertEqual(rec["prompt_tokens"], 10)   # fake server's real counts
        self.assertEqual(rec["output_tokens"], 12)
        self.assertTrue(rec["delivered"])
        self.assertIn("avoided_chars", rec)          # value wired in Task 2
        self.assertGreater(rec["returned_chars"], 0)
        exclude = repo / ".git" / "info" / "exclude"
        self.assertIn(".ollama-skills-usage.jsonl",
                      exclude.read_text(encoding="utf-8"))

    def test_usage_exclude_entry_written_once(self):
        repo = self._make_repo(staged=True)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        self.assertEqual(self.run_cli("commit-msg")[0], 0)
        self.assertEqual(self.run_cli("commit-msg")[0], 0)
        entries = [line for line in
                   (repo / ".git" / "info" / "exclude").read_text(
                       encoding="utf-8").splitlines()
                   if line == ".ollama-skills-usage.jsonl"]
        self.assertEqual(len(entries), 1)

    def test_usage_exclude_preserves_pattern_without_trailing_newline(self):
        repo = self._make_repo(staged=True)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        exclude = repo / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text("# mine\nsecrets.env", encoding="utf-8")  # no \n at EOF
        self.assertEqual(self.run_cli("commit-msg")[0], 0)
        lines = exclude.read_text(encoding="utf-8").splitlines()
        self.assertIn("secrets.env", lines)                    # pattern intact
        self.assertIn(".ollama-skills-usage.jsonl", lines)     # ours on its own line

    def test_usage_exclude_works_in_linked_worktree(self):
        repo = self._make_repo(staged=True)
        subprocess.run(["git", "config", "user.email", "t@e.st"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
        wt = Path(self._tmp) / "wt"
        subprocess.run(["git", "worktree", "add", "-q", str(wt)], cwd=repo, check=True)
        os.chdir(wt)
        (wt / "extra.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=wt, check=True)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        self.assertEqual(self.run_cli("commit-msg")[0], 0)
        self.assertTrue((wt / ".ollama-skills-usage.jsonl").is_file())
        status = subprocess.run(["git", "status", "--porcelain"], cwd=wt,
                                capture_output=True, text=True, check=True).stdout
        self.assertNotIn(".ollama-skills-usage.jsonl", status)
        os.chdir(self._tmp)   # release the worktree dir for teardown on Windows

    def test_usage_optout_env_writes_nothing(self):
        repo = self._make_repo(staged=True)   # setUp already set NO_USAGE=1
        code, _, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        self.assertFalse((repo / ".ollama-skills-usage.jsonl").exists())

    def test_usage_optout_config_writes_nothing(self):
        repo = self._make_repo(staged=True)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        (repo / ".ollama-skills.json").write_text(
            json.dumps({"usage_log": False}), encoding="utf-8")
        code, _, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        self.assertFalse((repo / ".ollama-skills-usage.jsonl").exists())

    def test_usage_ledger_never_contains_content(self):
        repo = self._make_repo(staged=True)   # stages SECRETMARKER123 in upload.py
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        self.assertEqual(
            self.run_cli("commit-msg", "--hint", "SECRETHINT456")[0], 0)
        text = (repo / ".ollama-skills-usage.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("SECRETMARKER123", text)
        self.assertNotIn("upload.py", text)
        self.assertNotIn("SECRETHINT456", text)

    def test_usage_log_path_override(self):
        repo = self._make_repo(staged=True)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        target_dir = Path(self._tmp) / "elsewhere"
        target_dir.mkdir()
        target = target_dir / "usage.jsonl"
        (repo / ".ollama-skills.json").write_text(
            json.dumps({"usage_log_path": str(target)}), encoding="utf-8")
        code, _, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        self.assertTrue(target.is_file())
        self.assertFalse((repo / ".ollama-skills-usage.jsonl").exists())

    def test_usage_log_path_nonstring_falls_back(self):
        repo = self._make_repo(staged=True)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        (repo / ".ollama-skills.json").write_text(
            json.dumps({"usage_log_path": 12345}), encoding="utf-8")
        code, _, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)   # exit code must survive the typo
        self.assertTrue((repo / ".ollama-skills-usage.jsonl").is_file())

    def test_usage_path_home_fallback_outside_repo(self):
        os.chdir(self._tmp)   # tempdir, not a git repo; HOME/USERPROFILE = self._tmp
        cfg = {"tasks": {}}
        path, root = ollama_ask._usage_path(cfg)
        self.assertIsNone(root)
        self.assertEqual(path, Path(self._tmp) / ".ollama-skills-usage.jsonl")

    def test_usage_retry_marks_only_final_delivered(self):
        repo = self._make_docs_repo()
        (repo / "docs" / "extra.md").write_text("WRONGTYPEONCE\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        code, _, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        records = self._read_ledger(repo)
        self.assertEqual(len(records), 2)
        self.assertEqual([r["delivered"] for r in records], [False, True])
        self.assertEqual(records[0]["avoided_chars"], 0)

    def test_usage_exit6_marks_all_undelivered(self):
        repo = self._make_docs_repo()
        (repo / "docs" / "extra.md").write_text("ALWAYSWRONGTYPE\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        code, _, _ = self.run_cli("commit-msg")
        self.assertEqual(code, 6)
        records = self._read_ledger(repo)
        self.assertEqual(len(records), 2)
        self.assertFalse(any(r["delivered"] for r in records))
        self.assertTrue(all(r["avoided_chars"] == 0 for r in records))

    def test_usage_commit_msg_avoided_positive(self):
        repo = self._make_repo(staged=True)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        code, _, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        rec = self._read_ledger(repo)[0]
        self.assertGreater(rec["avoided_chars"], 0)
        # counterfactual is the FULL staged diff, bigger than the model's input
        self.assertGreater(rec["avoided_chars"], rec["returned_chars"])

    def test_usage_summarize_avoided_is_raw_input(self):
        os.chdir(self._tmp)   # not a repo -> ledger falls back to HOME (= _tmp)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        sample = "\n".join(f"2026-07-14T09:30:00Z ERROR db refused attempt {i}"
                           for i in range(40))
        code, _, err = self.run_stdin(sample, "summarize", "--kind", "log")
        self.assertEqual(code, 0, msg=err)
        ledger = Path(self._tmp) / ".ollama-skills-usage.jsonl"
        records = [json.loads(line) for line in
                   ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
        final = records[-1]
        self.assertTrue(final["delivered"])
        self.assertEqual(final["cmd"], "summarize")
        self.assertGreaterEqual(final["avoided_chars"], len(sample) - 2)

    def test_usage_ask_avoided_is_zero(self):
        repo = self._make_repo(staged=True)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        code, _, err = self.run_cli("ask", "say hi")
        self.assertEqual(code, 0, msg=err)
        rec = self._read_ledger(repo)[0]
        self.assertEqual(rec["avoided_chars"], 0)   # honest zero by design

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

    def test_usage_fix_lint_skip_claims_zero(self):
        repo = self._make_repo(staged=True)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        target = repo / "code.py"
        target.write_text("import os\nSKIPFIX\n" * 40, encoding="utf-8")
        code, out, err = self.run_cli("fix-lint", "--file", str(target),
                                      "--line", "1", "--error", "unused import")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(out.strip(), "SKIP")
        rec = self._read_ledger(repo)[-1]
        self.assertTrue(rec["delivered"])
        self.assertEqual(rec["avoided_chars"], 0)

    # -- author-intent channel ------------------------------------------------

    def test_commit_msg_intent_line_position(self):
        self._make_repo(staged=True)
        FakeOllamaHandler.prompts = []
        code, out, err = self.run_cli(
            "commit-msg", "--type", "feat", "--hint", "add retry helper to uploads")
        self.assertEqual(code, 0, msg=err)
        lines = FakeOllamaHandler.prompts[0].splitlines()
        self.assertEqual(
            lines[2], "Author's intent: feat - add retry helper to uploads")
        self.assertTrue(lines[4].startswith("File kinds:"), msg=lines[:6])

    def test_commit_msg_type_flag_beats_classifier(self):
        repo = self._make_repo(staged=True)   # code repo: classifier suggests None
        (repo / "extra.py").write_text("# WRONGTYPEONCE\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        FakeOllamaHandler.prompts = []
        code, out, err = self.run_cli("commit-msg", "--type", "docs")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(out.strip(), "docs: update the guides")
        self.assertEqual(len(FakeOllamaHandler.prompts), 2)   # corrective retry ran

    def test_commit_msg_type_flag_persistent_conflict_exits_6(self):
        repo = self._make_repo(staged=True)
        (repo / "extra.py").write_text("# ALWAYSWRONGTYPE\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        code, _, _ = self.run_cli("commit-msg", "--type", "docs")
        self.assertEqual(code, 6)

    def test_commit_msg_hint_sanitized(self):
        self._make_repo(staged=True)
        FakeOllamaHandler.prompts = []
        messy = "add\nretry\thelper  " + "x" * 300
        code, _, err = self.run_cli("commit-msg", "--hint", messy)
        self.assertEqual(code, 0, msg=err)
        intent = FakeOllamaHandler.prompts[0].splitlines()[2]
        self.assertTrue(intent.startswith("Author's intent: add retry helper x"))
        self.assertLessEqual(len(intent), len("Author's intent: ") + 200)

    def test_usage_hinted_field(self):
        repo = self._make_repo(staged=True)
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        self.assertEqual(self.run_cli("commit-msg", "--type", "feat")[0], 0)
        self.assertEqual(self.run_cli("commit-msg")[0], 0)
        records = self._read_ledger(repo)
        self.assertTrue(records[0]["hinted"])
        self.assertNotIn("hinted", records[-1])

    def test_staged_context_orders_by_churn(self):
        repo = Path(self._tmp) / "churnrepo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "a.txt").write_text("tiny\n", encoding="utf-8")
        (repo / "z.py").write_text(
            "\n".join(f"def f{i}(): return {i}" for i in range(30)) + "\n",
            encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        os.chdir(repo)
        FakeOllamaHandler.prompts = []
        code, _, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        body = FakeOllamaHandler.prompts[0]
        self.assertLess(body.find("def f0"), body.find("tiny"),
                        msg="high-churn z.py must be excerpted before tiny a.txt")

    def test_commit_msg_length_feedback_includes_count(self):
        repo = self._make_repo(staged=True)
        (repo / "extra.py").write_text("# LONGLINEONCE\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        FakeOllamaHandler.prompts = []
        code, out, err = self.run_cli("commit-msg")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(out.strip(), "feat: add upload retry loop")
        self.assertEqual(len(FakeOllamaHandler.prompts), 2)
        self.assertIn("It is 86 chars", FakeOllamaHandler.prompts[1]
                      + FakeOllamaHandler.last_payload.get("system", ""))

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

    def test_fix_lint_skip_on_retry_still_fails_format(self):
        # SKIP is a valid answer only on the FIRST attempt; on the corrective
        # retry it means the model dodged the format instruction -> exit 6.
        target = Path(self._tmp) / "skipretry.py"
        target.write_text("import os\n", encoding="utf-8")
        FakeOllamaHandler.generate_calls = 0
        code, out, err = self.run_cli(
            "fix-lint", "--file", str(target), "--line", "1",
            "--error", "SKIPRETRY bad name")
        self.assertEqual(code, 6, msg=err)
        self.assertEqual(FakeOllamaHandler.generate_calls, 2)

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
        # The spawned real subprocess reads REAL free RAM (the in-process
        # free_ram monkeypatch in setUp doesn't cross the subprocess
        # boundary) and would exit 4 if the resident models don't fit free
        # RAM. Pin the model explicitly - explicit pins bypass the RAM gate
        # by design, and this test's subject (UTF-8 pipes) is untouched.
        env["OLLAMA_SKILLS_MODEL"] = "qwen3:8b"
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

    def test_summarize_pins_model_once_for_whole_map_reduce_run(self):
        """Model resolution must happen once per summarize run, not once per
        generate() call. Regression: free RAM sampled fresh on every chunk
        meant a mid-run drop (e.g. the picked model loading) could gate out
        every candidate at chunk K and abort the whole run with exit 4,
        losing the K-1 completed chunk digests. cmd_summarize now resolves
        and pins the model before the map loop, so later chunks reuse the
        pin instead of re-sampling free RAM."""
        calls = {"n": 0}

        def flaky_free_ram():
            # Plenty of free RAM for the first (and, post-fix, only)
            # resolution; a crash to 0 thereafter would gate out every
            # installed model if resolve_model were re-entered per chunk.
            calls["n"] += 1
            return 8_000_000_000 if calls["n"] == 1 else 0

        ollama_ask.free_ram_bytes = flaky_free_ram

        big = "\n".join(f"event number {i} happened on host node-{i}" for i in range(400))
        code, out, err = self.run_stdin(big, "summarize", "--kind", "events", "--no-dedupe")

        self.assertEqual(code, 0, msg=err)  # would be 4 if re-gated mid-run
        self.assertGreater(FakeOllamaHandler.generate_calls, 1)  # map + reduce ran
        self.assertEqual(len(set(FakeOllamaHandler.models_seen)), 1)  # one model, pinned
        self.assertLessEqual(FakeOllamaHandler.tags_calls, 1)  # resolved at most once
        self.assertEqual(calls["n"], 1)  # free RAM sampled exactly once for the run

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

    def _make_pr_repo(self, url="https://github.com/example/repo.git",
                      upstream=True):
        """Local repo with a fake origin, a main base, and a feature branch.
        No network: the remote URL is never fetched; upstream is wired with
        update-ref + branch config, exactly what @{u} resolution needs."""
        work = Path(self._tmp) / "prrepo"
        work.mkdir()

        def g(*a):
            subprocess.run(["git", *a], cwd=work, check=True,
                           capture_output=True, text=True)

        g("init", "-q")
        g("config", "user.email", "t@example.com")
        g("config", "user.name", "T")
        (work / "one.txt").write_text("one\n", encoding="utf-8")
        g("add", ".")
        g("commit", "-q", "-m", "chore: seed")
        g("branch", "-m", "main")
        g("update-ref", "refs/remotes/origin/main", "HEAD")
        g("symbolic-ref", "refs/remotes/origin/HEAD",
          "refs/remotes/origin/main")
        g("checkout", "-q", "-b", "feature")
        (work / "two.txt").write_text("SECRET_FILE_CONTENT\n", encoding="utf-8")
        g("add", ".")
        g("commit", "-q", "-m", "feat: add two")
        g("remote", "add", "origin", url)
        if upstream:
            g("update-ref", "refs/remotes/origin/feature", "HEAD")
            g("config", "branch.feature.remote", "origin")
            g("config", "branch.feature.merge", "refs/heads/feature")
        os.chdir(work)
        return work

    def _install_fake_cli(self, name: str, create_exit: int = 0,
                          auth_exit: int = 0) -> Path:
        """Put a fake gh/glab first on PATH. It answers `auth status` with
        `auth_exit` (0 = authenticated), records the argv of any other call to
        a capture file, and either prints a fake URL or fails with
        `create_exit`. Found via shutil.which (which honours .bat through
        PATHEXT on Windows). setUp/tearDown's os.environ save/restore undoes
        the PATH change."""
        bin_dir = Path(self._tmp) / "fakebin"
        bin_dir.mkdir(exist_ok=True)
        capture = bin_dir / f"{name}-argv.txt"
        if os.name == "nt":
            script = bin_dir / f"{name}.bat"
            lines = ["@echo off",
                     f'if "%1"=="auth" exit /b {auth_exit}',
                     f'echo %* >> "{capture}"']
            if create_exit:
                lines += ["echo boom 1>&2", f"exit /b {create_exit}"]
            else:
                lines += ["echo https://example.test/pr/1"]
            script.write_text("\r\n".join(lines) + "\r\n", encoding="ascii")
        else:
            script = bin_dir / name
            lines = ["#!/bin/sh",
                     f'[ "$1" = "auth" ] && exit {auth_exit}',
                     f'printf \'%s \' "$@" >> "{capture}"',
                     f'printf \'\\n\' >> "{capture}"']
            if create_exit:
                lines += ["echo boom >&2", f"exit {create_exit}"]
            else:
                lines += ["echo https://example.test/pr/1"]
            script.write_text("\n".join(lines) + "\n", encoding="ascii")
            script.chmod(0o755)
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]
        return capture

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

    def test_git_history_skill_bans_patches(self):
        """ollama-digest must keep its no-patch privacy rule; a silent
        reword that dropped these needles would defeat the skill's purpose."""
        needles = [
            "git log -p", "--patch", "--word-diff", "--full-diff",
            "never shows patch content",
            # digest accuracy: on git input the VERDICT line invites invented
            # error/warning counts (observed live 2026-07-29) — pin the flag.
            "--no-verdict",
        ]
        rel = "skills/ollama-digest/SKILL.md"
        body = (ROOT / rel).read_text(encoding="utf-8")
        for needle in needles:
            self.assertIn(needle, body, msg=f"{needle!r} missing from {rel}")

    def test_digest_skill_bans_reading_the_file(self):
        """ollama-digest delegates the file body away; a reword that dropped
        the no-read rule would silently defeat the privacy design."""
        body = (ROOT / "skills" / "ollama-digest" / "SKILL.md").read_text(
            encoding="utf-8")
        for needle in ("do not read the file yourself", "Get-Content",
                       "UNTRUSTED DRAFT", "--tail"):
            self.assertIn(needle, body, msg=f"{needle!r} missing")

    def test_digest_skill_keeps_both_privacy_rules(self):
        body = (ROOT / "skills" / "ollama-digest" / "SKILL.md").read_text(
            encoding="utf-8")
        for needle in ("do not read the file yourself",
                       "never shows patch content", "--no-verdict"):
            self.assertIn(needle, body, msg=f"{needle!r} missing")

    def test_removed_skills_are_gone(self):
        for rel in ("skills/ollama-k8s", "skills/ollama-logs",
                    "skills/ollama-git-history", "tests/e2e_k8s.py",
                    "scripts/kind-up.sh"):
            self.assertFalse((ROOT / rel).exists(),
                             msg=f"{rel} should have been removed in 0.5.0")

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

    def test_commit_intent_rule_pinned(self):
        for rel in ("skills/ollama-commit/SKILL.md", "agents/ollama-git.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("pass what you already know", text, msg=rel)
            self.assertIn("--type", text, msg=rel)
            self.assertIn("--hint", text, msg=rel)
            self.assertIn("omit both", text, msg=rel)

    # -- pr-desc --------------------------------------------------------------

    def test_pr_desc_returns_valid_json(self):
        self._make_pr_repo()
        code, out, err = self.run_cli("pr-desc")
        self.assertEqual(code, 0, msg=err)
        data = json.loads(out)
        self.assertEqual(data["title"], "feat: add retry logic")
        self.assertTrue(data["body"])

    def test_pr_desc_prompt_has_no_patch_content(self):
        self._make_pr_repo()
        FakeOllamaHandler.prompts = []
        code, out, err = self.run_cli("pr-desc")
        self.assertEqual(code, 0, msg=err)
        sent = "\n".join(FakeOllamaHandler.prompts)
        self.assertIn("feat: add two", sent)            # subjects reach the model
        self.assertNotIn("SECRET_FILE_CONTENT", sent)   # file bodies never do
        self.assertNotIn("+++", sent)
        self.assertNotIn("@@", sent)

    def test_pr_desc_empty_range_exits_2(self):
        work = self._make_pr_repo()
        subprocess.run(["git", "checkout", "-q", "main"], cwd=work, check=True)
        code, out, err = self.run_cli("pr-desc")
        self.assertEqual(code, 2, msg=err)
        self.assertIn("No commits", err)

    def test_pr_desc_invalid_twice_exits_6(self):
        work = self._make_pr_repo()
        (work / "three.txt").write_text("three\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "INVALID_JSON_PLEASE"],
                       cwd=work, check=True)
        code, out, err = self.run_cli("pr-desc")
        self.assertEqual(code, 6, msg=err)

    # -- pr-create --------------------------------------------------------

    def test_pr_create_draft_by_default(self):
        self._make_pr_repo()
        capture = self._install_fake_cli("gh")
        code, out, err = self.run_cli("pr-create", "--title", "feat: add two",
                                      "--body", "Adds two.")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("creating draft PR: feature -> main", out)
        self.assertIn("https://example.test/pr/1", out)
        argv = capture.read_text(encoding="utf-8", errors="replace")
        self.assertIn("--draft", argv)
        self.assertIn("--base", argv)

    def test_pr_create_ready_omits_draft(self):
        self._make_pr_repo()
        capture = self._install_fake_cli("gh")
        code, out, err = self.run_cli("pr-create", "--title", "feat: add two",
                                      "--body", "Adds two.", "--ready")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("creating ready PR: feature -> main", out)
        self.assertNotIn("--draft", capture.read_text(encoding="utf-8",
                                                      errors="replace"))

    def test_pr_create_title_body_verbatim(self):
        self._make_pr_repo()
        capture = self._install_fake_cli("gh")
        code, out, err = self.run_cli(
            "pr-create", "--title", "feat: add two (verbatim check)",
            "--body", "Line one with spaces. Line two.")
        self.assertEqual(code, 0, msg=err)
        argv = capture.read_text(encoding="utf-8", errors="replace")
        self.assertIn("feat: add two (verbatim check)", argv)
        self.assertIn("Line one with spaces. Line two.", argv)

    def test_pr_create_glab_mapping(self):
        self._make_pr_repo(url="https://gitlab.com/example/repo.git")
        capture = self._install_fake_cli("glab")
        code, out, err = self.run_cli("pr-create", "--title", "feat: add two",
                                      "--body", "Adds two.")
        self.assertEqual(code, 0, msg=err)
        argv = capture.read_text(encoding="utf-8", errors="replace")
        for needle in ("mr", "create", "--description", "--target-branch",
                       "--source-branch", "--draft"):
            self.assertIn(needle, argv, msg=f"{needle!r} missing from glab argv")

    def test_pr_create_unknown_host_exits_2(self):
        self._make_pr_repo(url="https://bitbucket.org/example/repo.git")
        code, out, err = self.run_cli("pr-create", "--title", "t",
                                      "--body", "b")
        self.assertEqual(code, 2, msg=err)
        self.assertIn("bitbucket.org", err)

    def test_pr_create_missing_cli_exits_2(self):
        self._make_pr_repo()
        orig_which = ollama_ask.shutil.which
        ollama_ask.shutil.which = (
            lambda name, *a, **k: None if name in ("gh", "glab")
            else orig_which(name, *a, **k))
        try:
            code, out, err = self.run_cli("pr-create", "--title", "t",
                                          "--body", "b")
        finally:
            ollama_ask.shutil.which = orig_which
        self.assertEqual(code, 2, msg=err)
        self.assertIn("not installed", err)

    def test_pr_create_no_upstream_exits_2(self):
        self._make_pr_repo(upstream=False)
        self._install_fake_cli("gh")
        code, out, err = self.run_cli("pr-create", "--title", "t",
                                      "--body", "b")
        self.assertEqual(code, 2, msg=err)
        self.assertIn("no upstream", err.lower())

    def test_pr_create_deleted_tracking_ref_exits_2(self):
        # branch.<x>.remote/merge configured but the remote-tracking ref
        # itself is gone: `@{u}` prints the literal "@{u}" on stdout and
        # exits non-zero. The guard must key off returncode, not stdout.
        work = self._make_pr_repo()
        subprocess.run(["git", "update-ref", "-d", "refs/remotes/origin/feature"],
                       cwd=work, check=True)
        self._install_fake_cli("gh")
        code, out, err = self.run_cli("pr-create", "--title", "t",
                                      "--body", "b")
        self.assertEqual(code, 2, msg=err)
        self.assertIn("no upstream", err.lower())

    def test_pr_create_unpushed_commits_exits_2(self):
        # An extra local commit made after the fixture wires upstream leaves
        # the remote branch stale; the PR must not be opened from it.
        work = self._make_pr_repo()
        (work / "three.txt").write_text("three\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat: add three"],
                       cwd=work, check=True)
        self._install_fake_cli("gh")
        code, out, err = self.run_cli("pr-create", "--title", "t",
                                      "--body", "b")
        self.assertEqual(code, 2, msg=err)
        self.assertIn("unpushed", err.lower())

    def test_pr_create_cli_failure_exits_8(self):
        self._make_pr_repo()
        self._install_fake_cli("gh", create_exit=1)
        code, out, err = self.run_cli("pr-create", "--title", "t",
                                      "--body", "b")
        self.assertEqual(code, 8, msg=err)
        self.assertIn("boom", err)

    def test_pr_create_protected_head_exits_2(self):
        # Protected-head is checked before base/upstream resolution, so a
        # plain checkout to main (no upstream wiring needed) is enough.
        work = self._make_pr_repo()
        subprocess.run(["git", "checkout", "-q", "main"], cwd=work, check=True)
        code, out, err = self.run_cli("pr-create", "--title", "t",
                                      "--body", "b")
        self.assertEqual(code, 2, msg=err)
        self.assertIn("Refusing to open a PR from 'main'", err)

    def test_pr_create_head_equals_base_exits_2(self):
        self._make_pr_repo()
        code, out, err = self.run_cli("pr-create", "--title", "t",
                                      "--body", "b", "--base", "feature")
        self.assertEqual(code, 2, msg=err)
        self.assertIn("Head and base are both 'feature'", err)

    def test_pr_create_unauthenticated_exits_2(self):
        self._make_pr_repo()
        self._install_fake_cli("gh", auth_exit=1)
        code, out, err = self.run_cli("pr-create", "--title", "t",
                                      "--body", "b")
        self.assertEqual(code, 2, msg=err)
        self.assertIn("not authenticated", err)

    def test_pr_create_cli_timeout_exits_8(self):
        # Hermetic timeout test: the sleeping-shim approach (a real shim that
        # sleeps longer than a monkeypatched-small PR_CLI_*_TIMEOUT) risks
        # flakiness under Windows process-spawn/scheduling jitter, so this
        # instead patches ollama_ask.subprocess.run to raise TimeoutExpired
        # only for calls to the fake CLI binary (auth status and/or create),
        # leaving every git subprocess call untouched.
        self._make_pr_repo()
        self._install_fake_cli("gh")
        fake_cli = shutil.which("gh")
        orig_run = ollama_ask.subprocess.run

        def fake_run(argv, *a, **k):
            if argv and argv[0] == fake_cli:
                raise subprocess.TimeoutExpired(cmd=argv, timeout=1)
            return orig_run(argv, *a, **k)

        ollama_ask.subprocess.run = fake_run
        try:
            code, out, err = self.run_cli("pr-create", "--title", "t",
                                          "--body", "b")
        finally:
            ollama_ask.subprocess.run = orig_run
        self.assertEqual(code, 8, msg=err)
        self.assertIn("timed out", err.lower())

    # -- stats ---------------------------------------------------------------

    def _write_stats_fixture(self) -> Path:
        """Ledger fixture + cwd config pointing usage_log_path at it."""
        os.chdir(self._tmp)
        path = Path(self._tmp) / "fixture-usage.jsonl"
        now = ollama_ask.datetime.now(ollama_ask.timezone.utc)
        recent = now.isoformat(timespec="seconds")
        old = (now - ollama_ask.timedelta(days=30)).isoformat(timespec="seconds")
        rows = [
            {"v": 1, "ts": recent, "cmd": "commit-msg", "task": "commit",
             "model": "m", "prompt_tokens": 400, "output_tokens": 20,
             "duration_s": 2.0, "returned_chars": 40, "avoided_chars": 8000,
             "delivered": True},
            {"v": 1, "ts": recent, "cmd": "commit-msg", "task": "commit",
             "model": "m", "prompt_tokens": 400, "output_tokens": 20,
             "duration_s": 2.0, "returned_chars": 40, "avoided_chars": 0,
             "delivered": False},
            {"v": 1, "ts": old, "cmd": "summarize", "task": "summarize",
             "model": "m", "prompt_tokens": 900, "output_tokens": 100,
             "duration_s": 5.0, "returned_chars": 400, "avoided_chars": 20000,
             "delivered": True},
        ]
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
            fh.write("not json at all\n")
        (Path(self._tmp) / ".ollama-skills.json").write_text(
            json.dumps({"usage_log_path": str(path)}), encoding="utf-8")
        return path

    def test_stats_table_totals_and_footer(self):
        self._write_stats_fixture()
        code, out, err = self.run_cli("stats")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("commit-msg", out)
        self.assertIn("TOTAL", out)
        self.assertIn("1 malformed line(s) skipped", out)
        self.assertIn('"avoided" is a counterfactual', out)
        self.assertIn("review overhead is not counted", out)

    def test_stats_json_math(self):
        self._write_stats_fixture()
        code, out, err = self.run_cli("stats", "--json")
        self.assertEqual(code, 0, msg=err)
        data = json.loads(out)
        self.assertEqual(data["skipped_lines"], 1)
        cm = data["per_cmd"]["commit-msg"]
        self.assertEqual(cm["calls"], 2)
        self.assertEqual(cm["delivered"], 1)
        self.assertEqual(cm["local_tokens"], 840)          # all calls, real counts
        self.assertEqual(cm["est_avoided_tokens"], 2000)   # 8000 // 4, delivered only
        self.assertEqual(cm["est_returned_tokens"], 10)    # 40 // 4, delivered only
        self.assertEqual(cm["net_est_saved_tokens"], 1990)
        self.assertEqual(data["total"]["calls"], 3)
        self.assertEqual(data["total"]["local_tokens"], 1840)

    def test_stats_type_confused_records_skipped(self):
        path = self._write_stats_fixture()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"v": 1, "ts": "2026-07-29T00:00:00+00:00",
                                 "cmd": "ask", "prompt_tokens": "x",
                                 "delivered": True}) + "\n")
        code, out, err = self.run_cli("stats", "--json")
        self.assertEqual(code, 0, msg=err)
        data = json.loads(out)
        self.assertEqual(data["skipped_lines"], 2)   # 1 malformed + 1 type-confused
        self.assertNotIn("ask", data["per_cmd"])

    def test_stats_empty_existing_ledger_zeroed_total(self):
        os.chdir(self._tmp)
        path = Path(self._tmp) / "empty-usage.jsonl"
        path.write_text("", encoding="utf-8")
        (Path(self._tmp) / ".ollama-skills.json").write_text(
            json.dumps({"usage_log_path": str(path)}), encoding="utf-8")
        code, out, err = self.run_cli("stats", "--json")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(json.loads(out)["total"]["calls"], 0)

    def test_stats_since_filters_old_records(self):
        self._write_stats_fixture()
        code, out, err = self.run_cli("stats", "--json", "--since", "7")
        self.assertEqual(code, 0, msg=err)
        data = json.loads(out)
        self.assertNotIn("summarize", data["per_cmd"])   # 30 days old
        self.assertEqual(data["total"]["calls"], 2)

    def test_stats_reset_renames_ledger(self):
        path = self._write_stats_fixture()
        code, out, err = self.run_cli("stats", "--reset")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("Ledger reset", err)   # stderr: stdout stays data-only
        self.assertFalse(path.exists())
        self.assertTrue(Path(str(path) + ".bak").is_file())
        code, out, _ = self.run_cli("stats")
        self.assertIn("No usage recorded yet", out)

    def test_stats_json_reset_stdout_stays_json(self):
        path = self._write_stats_fixture()
        code, out, err = self.run_cli("stats", "--json", "--reset")
        self.assertEqual(code, 0, msg=err)
        data = json.loads(out)               # stdout must be pure JSON
        self.assertEqual(data["total"]["calls"], 3)
        self.assertIn("Ledger reset", err)
        self.assertTrue(Path(str(path) + ".bak").is_file())

    def test_stats_missing_ledger_friendly(self):
        os.chdir(self._tmp)   # no repo, no config; HOME ledger absent
        code, out, err = self.run_cli("stats")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("No usage recorded yet", out)

    def test_pr_skill_safety_wording_present(self):
        # A silent reword dropping draft-by-default or the deny-list would
        # defeat ollama-pr's safety story - pin the load-bearing wording as
        # normalized-whitespace PHRASES (not loose single-word needles that
        # "drafted"/"remains" would also satisfy).
        needles = [
            "UNTRUSTED DRAFT",
            "never pass `--ready` unless the user explicitly asked",
            "never force-push",
            "never `--web`",
            "head branch is main or master",
            "as a **draft** by default",
        ]
        rel = "skills/ollama-pr/SKILL.md"
        body = (ROOT / rel).read_text(encoding="utf-8")
        normalized = " ".join(body.split())
        for needle in needles:
            self.assertIn(needle, normalized, msg=f"{needle!r} missing from {rel}")


if __name__ == "__main__":
    unittest.main()
