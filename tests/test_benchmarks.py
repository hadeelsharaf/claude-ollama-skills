"""Hermetic tests for the A/B benchmark tooling. No network, no paid calls."""
from __future__ import annotations

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
import measure_ab  # noqa: E402
import measure_catalog  # noqa: E402


def fake_usage(consumed=1000, cache_read=0, cost=0.5):
    return {"usage": {"input_tokens": consumed - 100,
                      "cache_creation_input_tokens": 50,
                      "output_tokens": 50,
                      "cache_read_input_tokens": cache_read},
            "total_cost_usd": cost, "duration_ms": 1234,
            "result": "db-primary connection refused repeatedly; "
                      "worker-3 OOM killed; KeyError shard_map"}


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


class RunnerTests(unittest.TestCase):
    def setUp(self):
        # run_matrix() calls tempfile.mkdtemp("ab_<task>_<arm>_") for each
        # fixture, outside self._tmp - snapshot what's already there so
        # tearDown can remove only what THIS test created, not other
        # processes' leftovers.
        self._pre_ab_dirs = set(Path(tempfile.gettempdir()).glob("ab_*"))
        self._tmp = tempfile.mkdtemp(prefix="ab_runner_")
        self._orig = measure_ab.run_claude

    def tearDown(self):
        measure_ab.run_claude = self._orig
        rmtree_force(self._tmp)
        for path in (set(Path(tempfile.gettempdir()).glob("ab_*"))
                     - self._pre_ab_dirs):
            if path.is_dir():
                rmtree_force(str(path))

    def test_tokens_consumed_metric(self):
        row = measure_ab.usage_row(fake_usage())
        self.assertEqual(row["tokens_consumed"], 1000)
        self.assertEqual(row["cache_read"], 0)
        self.assertEqual(row["cost_usd"], 0.5)

    def test_usage_row_missing_keys_is_zero_not_crash(self):
        row = measure_ab.usage_row({"result": "x"})
        self.assertEqual(row["tokens_consumed"], 0)

    def test_validate_summarize(self):
        good = "db-primary refused connections; worker-3 out of memory"
        self.assertTrue(measure_ab.validate_summarize(good))
        self.assertFalse(measure_ab.validate_summarize("all fine, no issues"))

    def test_validate_commit_detects_new_commit(self):
        repo = fixtures.make_commit_fixture(Path(self._tmp) / "r")
        self.assertFalse(measure_ab.validate_commit(repo))   # still staged
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@e.st",
                        "commit", "-q", "-m", "feat: add json output"],
                       cwd=repo, check=True, capture_output=True)
        self.assertTrue(measure_ab.validate_commit(repo))

    def test_matrix_uses_boundary_and_aggregates(self):
        calls = []

        def stub(prompt, cwd, with_plugin):
            calls.append((prompt[:20], with_plugin))
            return fake_usage(consumed=2000 if not with_plugin else 800)

        measure_ab.run_claude = stub
        agg = measure_ab.run_matrix(runs=1, tasks=["summarize"],
                                    arms=["without", "with"],
                                    out_dir=Path(self._tmp) / "out")
        self.assertEqual(len(calls), 2)
        cells = agg["cells"]
        self.assertEqual(cells["summarize"]["without"]["tokens_mean"], 2000)
        self.assertEqual(cells["summarize"]["with"]["tokens_mean"], 800)
        self.assertAlmostEqual(cells["summarize"]["with"]["savings_pct"], 60.0)
        table = measure_ab.render_table(agg)
        self.assertIn("summarize", table)
        self.assertIn("savings", table)
        out_files = list((Path(self._tmp) / "out").glob("ab-*.json"))
        self.assertEqual(len(out_files), 1)

    def test_matrix_no_savings_claim_without_successes_on_both_sides(self):
        def stub(prompt, cwd, with_plugin):
            if with_plugin:
                bad = fake_usage(consumed=800)
                bad["result"] = "no planted facts here"   # fails validation
                return bad
            return fake_usage(consumed=2000)

        measure_ab.run_claude = stub
        agg = measure_ab.run_matrix(runs=1, tasks=["summarize"],
                                    arms=["without", "with"],
                                    out_dir=Path(self._tmp) / "out2")
        cell = agg["cells"]["summarize"]
        self.assertEqual(cell["with"]["ok"], 0)
        self.assertNotIn("savings_pct", cell["with"])   # never an absurd 100%

    def test_matrix_directed_arm_prompt_and_plugin(self):
        seen = []

        def stub(prompt, cwd, with_plugin):
            seen.append((prompt, with_plugin))
            return fake_usage(consumed=500 if with_plugin else 2000)

        measure_ab.run_claude = stub
        agg = measure_ab.run_matrix(runs=1, tasks=["summarize"],
                                    arms=["without", "directed"],
                                    out_dir=Path(self._tmp) / "out3")
        neutral, directed = seen[0], seen[1]
        self.assertFalse(neutral[1])
        self.assertTrue(directed[1])                    # plugin loaded
        self.assertIn("ollama-digest", directed[0])     # prompt names the skill
        self.assertNotEqual(neutral[0], directed[0])
        cell = agg["cells"]["summarize"]
        self.assertEqual(cell["directed"]["savings_pct"], 75.0)
        self.assertIn("directed savings vs without",
                      measure_ab.render_table(agg))


class EvalCaseTests(unittest.TestCase):
    def test_eval_cases_reuse_shared_prompts(self):
        eval_texts = "\n".join(
            p.read_text(encoding="utf-8")
            for p in (ROOT / "evals").rglob("*")
            if p.is_file() and p.suffix in (".yaml", ".yml", ".md"))
        self.assertIn(fixtures.PROMPT_COMMIT, eval_texts)
        self.assertIn(fixtures.PROMPT_SUMMARIZE, eval_texts)


class CatalogTests(unittest.TestCase):
    """benchmarks/measure_catalog.py — catalog size accounting."""

    def _make_tree(self, tmp, skill_desc, agent_desc):
        skill = tmp / "skills" / "demo" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: demo\ndescription: " + skill_desc +
            "\n---\nbody line\n", encoding="utf-8")
        agent = tmp / "agents" / "helper.md"
        agent.parent.mkdir(parents=True)
        agent.write_text(
            "---\nname: helper\ndescription: " + agent_desc +
            "\n---\nagent body\n", encoding="utf-8")

    def test_catalog_rows_counts_desc_and_body(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            self._make_tree(tmp, "Skill words. Use when needed.", "Agent words.")
            rows = measure_catalog.catalog_rows(tmp)
        kinds = sorted((r["kind"], r["name"]) for r in rows)
        self.assertEqual(kinds, [("agent", "helper"), ("skill", "demo")])
        skill_row = next(r for r in rows if r["kind"] == "skill")
        self.assertEqual(skill_row["desc_chars"], len("Skill words. Use when needed."))
        self.assertGreater(skill_row["body_chars"], 0)

    def test_catalog_total_sums_descriptions_only(self):
        rows = [{"kind": "skill", "name": "a", "desc_chars": 100, "body_chars": 9000},
                {"kind": "agent", "name": "b", "desc_chars": 50, "body_chars": 4000}]
        self.assertEqual(measure_catalog.catalog_total(rows), 150)
