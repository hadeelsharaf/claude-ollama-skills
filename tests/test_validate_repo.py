"""Failure-path tests for scripts/validate_repo.py (caps + catalog budget).

The happy path runs in CI as a script; these pin the guard rails themselves:
per-file caps fire, the total budget fires, and every failure message stays
ASCII (legacy Windows codepages crash on non-ASCII in unreconfigured pipes).
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import validate_repo


def _write_skill(root: Path, name: str, desc: str) -> Path:
    p = root / "skills" / name / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nname: {name}\ndescription: {desc}\n---\n"
                 "UNTRUSTED DRAFT\n", encoding="utf-8")
    return p


def _write_agent(root: Path, name: str, desc: str) -> Path:
    p = root / "agents" / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nname: {name}\ndescription: {desc}\n"
                 "model: haiku\ntools: Bash\n---\nUNTRUSTED DRAFT\n",
                 encoding="utf-8")
    return p


class ValidateRepoFailurePaths(unittest.TestCase):
    def setUp(self):
        self._root = validate_repo.ROOT
        self._failures = validate_repo.FAILURES
        self._budget = validate_repo.CATALOG_BUDGET
        validate_repo.FAILURES = []
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        validate_repo.ROOT = self.root

    def tearDown(self):
        validate_repo.ROOT = self._root
        validate_repo.FAILURES = self._failures
        validate_repo.CATALOG_BUDGET = self._budget
        self.tmp.cleanup()

    def test_over_cap_skill_description_fails_ascii(self):
        desc = "Use when testing. " + "x" * validate_repo.DESC_CAP_SKILL
        path = _write_skill(self.root, "demo", desc)
        buf = io.StringIO()
        with redirect_stdout(buf):
            validate_repo.check_skill(path)
        self.assertEqual(len(validate_repo.FAILURES), 1)
        out = buf.getvalue()
        self.assertIn("the catalog bills every session", out)
        self.assertTrue(out.isascii(), "validator failure output must be ASCII")

    def test_over_cap_agent_description_fails_ascii(self):
        desc = "Use for testing. " + "y" * validate_repo.DESC_CAP_AGENT
        path = _write_agent(self.root, "helper", desc)
        buf = io.StringIO()
        with redirect_stdout(buf):
            validate_repo.check_agent(path)
        self.assertEqual(len(validate_repo.FAILURES), 1)
        self.assertTrue(buf.getvalue().isascii())

    def test_total_budget_failure_names_catalog_and_stays_ascii(self):
        (self.root / ".claude-plugin").mkdir(parents=True)
        (self.root / ".claude-plugin" / "plugin.json").write_text(json.dumps(
            {"name": "t", "version": "0", "description": "t"}), encoding="utf-8")
        (self.root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
            {"name": "t", "owner": "t", "plugins": []}), encoding="utf-8")
        _write_skill(self.root, "one", "Use when one. " + "a" * 40)
        _write_skill(self.root, "two", "Use when two. " + "b" * 40)
        validate_repo.CATALOG_BUDGET = 50   # force the total over budget
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = validate_repo.main()
        self.assertEqual(rc, 1)
        out = buf.getvalue()
        self.assertIn("FAIL catalog", out)
        self.assertIn("top 3 contributors", out)
        self.assertTrue(out.isascii())


class CheckJsonTests(unittest.TestCase):
    def setUp(self):
        self._root = validate_repo.ROOT
        self._failures = validate_repo.FAILURES
        validate_repo.FAILURES = []
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        validate_repo.ROOT = self.root

    def tearDown(self):
        validate_repo.ROOT = self._root
        validate_repo.FAILURES = self._failures
        self.tmp.cleanup()

    def test_manifest_with_utf8_bom_passes(self):
        """PowerShell 5.1 Set-Content writes a BOM; a valid manifest must not
        fail CI for it (every other reader in the repo uses utf-8-sig)."""
        path = self.root / "plugin.json"
        path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"name": "x"}).encode())
        with redirect_stdout(io.StringIO()):
            data = validate_repo.check_json(path, ["name"])
        self.assertEqual(data, {"name": "x"})
        self.assertEqual(validate_repo.FAILURES, [])

    def test_unreadable_manifest_fails_cleanly(self):
        """An unreadable file must be a normal FAIL, not a traceback."""
        path = self.root / "plugin.json"
        path.mkdir()   # reading a directory raises OSError on every platform
        with redirect_stdout(io.StringIO()):
            data = validate_repo.check_json(path, ["name"])
        self.assertIsNone(data)
        self.assertEqual(len(validate_repo.FAILURES), 1)


class CheckSkillRefsTests(unittest.TestCase):
    def setUp(self):
        self._root = validate_repo.ROOT
        self._failures = validate_repo.FAILURES
        validate_repo.FAILURES = []
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        validate_repo.ROOT = self.root

    def tearDown(self):
        validate_repo.ROOT = self._root
        validate_repo.FAILURES = self._failures
        self.tmp.cleanup()

    def test_skill_body_missing_reference_file_fails_ascii(self):
        p = _write_skill(self.root, "demo", "Use when testing refs.")
        p.write_text(p.read_text(encoding="utf-8")
                     + "\nRead DENYLIST.md in this skill's folder first.\n",
                     encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            validate_repo.check_skill(p)
        self.assertEqual(len(validate_repo.FAILURES), 1)
        self.assertIn("DENYLIST.md", buf.getvalue())
        self.assertTrue(buf.getvalue().isascii())

    def test_skill_body_existing_reference_file_passes(self):
        p = _write_skill(self.root, "demo", "Use when testing refs.")
        p.write_text(p.read_text(encoding="utf-8")
                     + "\nRead DENYLIST.md in this skill's folder first.\n",
                     encoding="utf-8")
        # reference file: plain prose, no frontmatter, no UNTRUSTED DRAFT
        (p.parent / "DENYLIST.md").write_text("- never `rm -rf`\n",
                                              encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            validate_repo.check_skill(p)
        self.assertEqual(validate_repo.FAILURES, [])

    def test_skill_body_whitelisted_tokens_ignored(self):
        p = _write_skill(self.root, "demo", "Use when testing refs.")
        p.write_text(p.read_text(encoding="utf-8")
                     + "\nSee SKILL.md, CLAUDE.md, and README.md.\n",
                     encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            validate_repo.check_skill(p)
        self.assertEqual(validate_repo.FAILURES, [])

    def test_agent_body_repo_relative_reference_checked(self):
        p = _write_agent(self.root, "helper", "Runs chores.")
        p.write_text(p.read_text(encoding="utf-8")
                     + "\nRead skills/ollama-shell/DENYLIST.md first.\n",
                     encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            validate_repo.check_agent(p)
        self.assertEqual(len(validate_repo.FAILURES), 1)
        validate_repo.FAILURES = []
        ref = self.root / "skills" / "ollama-shell" / "DENYLIST.md"
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text("- base list\n", encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            validate_repo.check_agent(p)
        self.assertEqual(validate_repo.FAILURES, [])


if __name__ == "__main__":
    unittest.main()
