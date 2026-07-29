"""Hermetic tests for the A/B benchmark tooling. No network, no paid calls."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "scripts"))

import fixtures  # noqa: E402


def rmtree_force(path: str) -> None:
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=onerror)


def worktree_bytes(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if ".git" in p.parts or not p.is_file():
            continue
        out[str(p.relative_to(root))] = p.read_bytes()
    return out


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="ab_fixture_")

    def tearDown(self):
        rmtree_force(self._tmp)

    def test_commit_fixture_deterministic_worktree(self):
        a = fixtures.make_commit_fixture(Path(self._tmp) / "a")
        b = fixtures.make_commit_fixture(Path(self._tmp) / "b")
        self.assertEqual(worktree_bytes(a), worktree_bytes(b))

    def test_commit_fixture_shape(self):
        repo = fixtures.make_commit_fixture(Path(self._tmp) / "r")
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=repo, capture_output=True, text=True,
            check=True).stdout.splitlines()
        self.assertGreaterEqual(len(tracked), 14)
        commits = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], cwd=repo,
            capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(commits, "1")
        diff = subprocess.run(
            ["git", "diff", "--cached"], cwd=repo, capture_output=True,
            text=True, check=True).stdout
        self.assertGreaterEqual(len(diff), 8000)
        self.assertLessEqual(len(diff), 12000)
        unstaged = subprocess.run(
            ["git", "diff", "--name-only"], cwd=repo, capture_output=True,
            text=True, check=True).stdout.strip()
        self.assertEqual(unstaged, "")   # everything is staged, nothing loose

    def test_log_fixture_planted_facts(self):
        dest = fixtures.make_log_fixture(Path(self._tmp) / "logs")
        text = (dest / "app.log").read_text(encoding="utf-8")
        lines = text.splitlines()
        self.assertEqual(len(lines), 4000)
        self.assertIn("connection refused to db-primary:5432", text)
        self.assertIn("KeyError: 'shard_map'", text)
        self.assertIn("worker-3 killed: Out of memory", text)
        self.assertGreaterEqual(text.count("connection refused"), 100)
