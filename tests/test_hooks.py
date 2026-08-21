"""Tests for hooks/dispatch.py — the plugin's hook dispatcher.

Run: python -m unittest tests.test_hooks -v
The dispatcher is loaded from its file path (hooks/ is not a package) and
driven in-process: stdin is replaced per call, stdout captured.
"""
import importlib.util
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "dispatch", REPO / "hooks" / "dispatch.py")
dispatch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dispatch)


def rmtree_force(path):
    def onerr(fn, p, exc):
        os.chmod(p, stat.S_IWRITE)
        fn(p)
    shutil.rmtree(path, onerror=onerr)


class HookTestCase(unittest.TestCase):
    """Isolated HOME/cwd so ledger writes never touch the real repo."""

    def setUp(self):
        self._saved_env = dict(os.environ)
        self._saved_cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp(prefix="hooks_test_")
        os.environ["HOME"] = self._tmp
        os.environ["USERPROFILE"] = self._tmp
        os.environ.pop("OLLAMA_SKILLS_NO_USAGE", None)
        # cwd outside any git repo -> _usage_path falls back to HOME
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._saved_cwd)
        os.environ.clear()
        os.environ.update(self._saved_env)
        rmtree_force(self._tmp)

    def run_hook(self, event) -> "tuple[int, str, str]":
        payload = event if isinstance(event, str) else json.dumps(event)
        saved = sys.stdin
        sys.stdin = io.StringIO(payload)
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = dispatch.main()
        finally:
            sys.stdin = saved
        return code, out.getvalue(), err.getvalue()

    def ledger_rows(self) -> list:
        path = Path(self._tmp) / ".ollama-skills-usage.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]


class DispatcherSkeletonTests(HookTestCase):

    def test_unknown_event_is_silent_exit_zero(self):
        code, out, err = self.run_hook(
            {"hook_event_name": "PermissionRequest"})
        self.assertEqual((code, out, err), (0, "", ""))

    def test_malformed_json_exits_zero_and_leaves_breadcrumb(self):
        code, out, err = self.run_hook("{not json")
        self.assertEqual((code, out, err), (0, "", ""))
        rows = self.ledger_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cmd"], "hook_error")
        self.assertEqual(rows[0]["event"], "unknown")
        self.assertIn("v", rows[0])
        self.assertIn("ts", rows[0])
        # counts-only: exception class name, nothing else
        self.assertNotIn("{", rows[0]["error"])

    def test_non_dict_event_is_silent_exit_zero(self):
        code, out, err = self.run_hook("[1, 2, 3]")
        self.assertEqual((code, out, err), (0, "", ""))

    def test_breadcrumb_respects_usage_optout(self):
        os.environ["OLLAMA_SKILLS_NO_USAGE"] = "1"
        code, out, err = self.run_hook("{not json")
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertEqual(self.ledger_rows(), [])

    def test_crashing_handler_fails_open_with_breadcrumb(self):
        def boom(event):
            raise RuntimeError("handler exploded")
        original = dispatch.HANDLERS.get("SessionStart")
        dispatch.HANDLERS["SessionStart"] = boom
        try:
            code, out, err = self.run_hook(
                {"hook_event_name": "SessionStart"})
        finally:
            if original is not None:
                dispatch.HANDLERS["SessionStart"] = original
            else:
                dispatch.HANDLERS.pop("SessionStart", None)
        self.assertEqual((code, out, err), (0, "", ""))
        rows = self.ledger_rows()
        self.assertEqual(rows[0]["error"], "RuntimeError")
        self.assertEqual(rows[0]["event"], "SessionStart")


class _FakeProc:
    def __init__(self, returncode, stdout):
        self.returncode = returncode
        self.stdout = stdout


class SessionStartTests(HookTestCase):

    MODELS_OK = json.dumps({
        "tasks": {"commit": {"model": "qwen2.5-coder:1.5b", "source": "auto"},
                  "summarize": {"model": "gemma2:2b", "source": "auto"},
                  "shell": {"model": "gemma2:2b", "source": "auto"}},
        "installed": ["qwen2.5-coder:1.5b", "gemma2:2b"],
        "skipped": [], "hints": []})

    MODELS_DOWN = json.dumps({
        "tasks": {"commit": {"model": None, "source": "none"},
                  "summarize": {"model": None, "source": "none"}},
        "installed": [], "skipped": [], "hints": []})

    def _patch_models(self, proc):
        self._orig_run = dispatch.subprocess.run
        dispatch.subprocess.run = lambda *a, **k: proc
        self.addCleanup(
            lambda: setattr(dispatch.subprocess, "run", self._orig_run))

    def test_card_names_commit_and_summarize_models(self):
        self._patch_models(_FakeProc(0, self.MODELS_OK))
        code, out, err = self.run_hook({"hook_event_name": "SessionStart"})
        self.assertEqual(code, 0)
        self.assertIn("ollama-skills: local delegation ready", out)
        self.assertIn("commit -> qwen2.5-coder:1.5b", out)
        self.assertIn("summarize -> gemma2:2b", out)
        self.assertIn("summarize --kind test", out)
        self.assertLessEqual(len(out), 300)

    def test_silent_when_ollama_down(self):
        self._patch_models(_FakeProc(0, self.MODELS_DOWN))
        code, out, err = self.run_hook({"hook_event_name": "SessionStart"})
        self.assertEqual((code, out), (0, ""))

    def test_silent_when_models_call_fails(self):
        self._patch_models(_FakeProc(3, ""))
        code, out, err = self.run_hook({"hook_event_name": "SessionStart"})
        self.assertEqual((code, out), (0, ""))


class PromptHintTests(HookTestCase):

    def hint_for(self, prompt: str) -> str:
        code, out, err = self.run_hook(
            {"hook_event_name": "UserPromptSubmit", "prompt": prompt})
        self.assertEqual(code, 0)
        return out

    def test_commit_prompt_names_commit_skill(self):
        out = self.hint_for("please commit these changes")
        self.assertEqual(
            out, "hint: ollama-skills can do this locally "
                 "(skill: ollama-commit).\n")

    def test_failing_test_prompt_names_digest_skill(self):
        out = self.hint_for("the tests fail after my change, take a look")
        self.assertIn("(skill: ollama-digest).", out)

    def test_release_notes_prompt_names_digest_skill(self):
        out = self.hint_for("draft release notes for v0.9")
        self.assertIn("(skill: ollama-digest).", out)

    def test_pull_request_prompt_names_pr_skill(self):
        out = self.hint_for("open a pull request for this branch")
        self.assertIn("(skill: ollama-pr).", out)

    def test_unrelated_prompt_is_silent(self):
        self.assertEqual(self.hint_for("rename this variable please"), "")

    def test_one_hint_even_when_multiple_triggers_match(self):
        out = self.hint_for("commit this and open a pull request")
        self.assertEqual(out.count("hint:"), 1)

    def test_prompt_text_never_echoed(self):
        out = self.hint_for("commit the SECRET_TOKEN change")
        self.assertNotIn("SECRET_TOKEN", out)


class HooksJsonTests(unittest.TestCase):

    def setUp(self):
        self.data = json.loads(
            (REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))

    def test_registers_exactly_the_four_events(self):
        self.assertEqual(
            set(self.data["hooks"]),
            {"SessionStart", "UserPromptSubmit", "PreToolUse", "Stop"})

    def test_every_command_targets_the_dispatcher_via_plugin_root(self):
        for entries in self.data["hooks"].values():
            for entry in entries:
                for hook in entry["hooks"]:
                    self.assertEqual(hook["type"], "command")
                    self.assertIn(
                        '${CLAUDE_PLUGIN_ROOT}/hooks/dispatch.py',
                        hook["command"])

    def test_pretooluse_matchers_cover_bash_and_powershell(self):
        matchers = [e.get("matcher") for e in self.data["hooks"]["PreToolUse"]]
        self.assertEqual(matchers, ["Bash", "PowerShell"])

    def test_bash_entry_carries_if_prefilters(self):
        bash_entry = self.data["hooks"]["PreToolUse"][0]
        ifs = [h.get("if") for h in bash_entry["hooks"]]
        self.assertEqual(ifs, ["Bash(git *)", "Bash(docker *)"])


if __name__ == "__main__":
    unittest.main()
