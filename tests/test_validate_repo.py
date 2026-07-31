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


if __name__ == "__main__":
    unittest.main()
