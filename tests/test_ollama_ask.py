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
            self._send_json(200, {"models": FAKE_MODELS})
        elif self.path == "/api/version":
            self._send_json(200, {"version": "0.0-test"})
        else:
            self._send_json(404, {"error": "unknown path"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
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


def free_closed_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class OllamaAskTests(unittest.TestCase):
    server: ThreadingHTTPServer

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeOllamaHandler.counters.clear()
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
        os.environ.clear()
        os.environ.update(self._saved_env)
        rmtree_force(self._tmp)

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ollama_ask.main(list(argv) + ["--quiet"])
        return code, out.getvalue(), err.getvalue()

    def resolved(self, *argv: str) -> dict:
        code, out, err = self.run_cli("models", "--json", *argv)
        self.assertEqual(code, 0, msg=err)
        return json.loads(out)

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

    def test_resolve_model_autodetect_prefers_commit_list(self):
        data = self.resolved()
        self.assertEqual(data["tasks"]["commit"]["model"], "llama3.2:1b")
        self.assertEqual(data["tasks"]["commit"]["source"], "auto")

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
        os.environ["OLLAMA_HOST"] = f"http://127.0.0.1:{free_closed_port()}"
        code, _, err = self.run_cli("health")
        self.assertEqual(code, 3)
        self.assertIn("running", err.lower())

    def test_missing_model_exits_4(self):
        code, _, err = self.run_cli("ask", "hello", "--model", "missing-model")
        self.assertEqual(code, 4)
        self.assertIn("pull", err.lower())


if __name__ == "__main__":
    unittest.main()
