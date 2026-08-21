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
        dispatch.HANDLERS["SessionStart"] = boom
        try:
            code, out, err = self.run_hook(
                {"hook_event_name": "SessionStart"})
        finally:
            dispatch.HANDLERS.pop("SessionStart", None)
        self.assertEqual((code, out, err), (0, "", ""))
        rows = self.ledger_rows()
        self.assertEqual(rows[0]["error"], "RuntimeError")
        self.assertEqual(rows[0]["event"], "SessionStart")


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
