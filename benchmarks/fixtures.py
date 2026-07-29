#!/usr/bin/env python3
"""Deterministic fixtures for the A/B token benchmark. Stdlib only.

Usage: python benchmarks/fixtures.py commit <dest>
       python benchmarks/fixtures.py log <dest>

Both builds are byte-deterministic (no clocks, no randomness in file
content), so with-vs-without arms and repeated trials see identical inputs.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROMPT_COMMIT = ("Commit the staged changes in this repository with an "
                 "appropriate one-line commit message. Do not push.")
PROMPT_SUMMARIZE = ("Read app.log and summarize what went wrong: the main "
                    "failure patterns and the most likely root cause. "
                    "Keep it under 15 lines.")

# Tune ONLY this constant if the staged-diff size test falls outside its
# 8,000-12,000 char band (each pad line adds ~50 chars to the diff).
DOC_PAD_LINES = 64

_MODULES = {
    "reader": ["open_source", "iter_lines", "close_source", "peek", "rewind"],
    "parser": ["parse_line", "split_fields", "detect_format", "coerce_types",
               "parse_batch"],
    "filters": ["by_level", "by_time_range", "by_pattern", "invert", "chain"],
    "formatter": ["to_text", "align_columns", "colorize", "truncate_long",
                  "header"],
    "sinks": ["to_stdout", "to_file", "rotate", "flush_all", "close_all"],
    "config": ["load", "defaults", "merge", "validate", "as_dict"],
    "stats": ["count_by_level", "rate_per_minute", "top_patterns",
              "percentiles", "summary"],
    "cli": ["build_args", "main", "run_pipeline", "print_help", "version"],
}

_FEATURE_TOUCHES = ["cli", "formatter", "filters", "config", "stats"]


def _module_body(name: str, funcs) -> str:
    lines = [f'"""logpipe.{name} - part of the logpipe sample project."""', ""]
    for i, fn in enumerate(funcs):
        lines += [
            f"def {fn}(value=None, options=None):",
            f'    """{name}.{fn}: deterministic sample implementation."""',
            f"    result = ('{name}', '{fn}', {i})",
            "    if options:",
            "        result = result + (len(options),)",
            "    return result",
            "",
            "",
        ]
    return "\n".join(lines)


def _feature_block(name: str) -> str:
    return "\n".join([
        "",
        f"def {name}_to_json(records, severity=None):",
        f'    """New in the JSON-output feature: {name}-side JSON support."""',
        "    kept = [r for r in records",
        "            if severity is None or r and r[0] == severity]",
        f"    return {{'module': '{name}', 'count': len(kept), 'items': kept}}",
        "",
    ])


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=AB Bench", "-c", "user.email=ab@bench.local"]
        + list(args), cwd=repo, check=True, capture_output=True)


def make_commit_fixture(dest: Path) -> Path:
    repo = Path(dest)
    (repo / "logpipe").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "logpipe" / "__init__.py").write_text(
        '"""logpipe sample project."""\n__version__ = "0.9.0"\n',
        encoding="utf-8")
    for name, funcs in _MODULES.items():
        (repo / "logpipe" / f"{name}.py").write_text(
            _module_body(name, funcs), encoding="utf-8")
    for tname in ("parser", "filters", "stats"):
        body = "\n".join([
            f"from logpipe.{tname} import {_MODULES[tname][0]}",
            "",
            "",
            f"def test_{tname}_first():",
            f"    assert {_MODULES[tname][0]}()[0] == '{tname}'",
            "",
        ])
        (repo / "tests" / f"test_{tname}.py").write_text(body, encoding="utf-8")
    (repo / "README.md").write_text(
        "# logpipe\n\nA small sample log pipeline used for benchmarking.\n",
        encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 0.9.0\n- initial sample release\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "logpipe"\nversion = "0.9.0"\n', encoding="utf-8")
    _run_git(repo, "init", "-q")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", "chore: initial logpipe sample")

    # ---- the staged-but-uncommitted feature change (the thing under test) --
    pad = "\n".join(
        f"    note {i:02d}: json output preserves field order and severity."
        for i in range(DOC_PAD_LINES))
    (repo / "logpipe" / "json_out.py").write_text("\n".join([
        '"""logpipe.json_out - JSON output support (new feature).',
        "",
        pad,
        '"""',
        "import json",
        "",
        "",
        "def dumps_records(records, severity=None):",
        "    kept = [r for r in records",
        "            if severity is None or (r and r[0] == severity)]",
        "    return json.dumps({'count': len(kept), 'items': kept})",
        "",
        "",
        "def write_json(path, records, severity=None):",
        "    text = dumps_records(records, severity)",
        "    with open(path, 'w', encoding='utf-8') as fh:",
        "        fh.write(text)",
        "    return len(text)",
        "",
    ]), encoding="utf-8")
    (repo / "tests" / "test_json_out.py").write_text("\n".join([
        "from logpipe.json_out import dumps_records",
        "",
        "",
        "def test_dumps_records_counts():",
        "    assert '\"count\": 2' in dumps_records([('a',), ('b',)])",
        "",
        "",
        "def test_dumps_records_severity_filter():",
        "    out = dumps_records([('ERROR',), ('INFO',)], severity='ERROR')",
        "    assert '\"count\": 1' in out",
        "",
    ]), encoding="utf-8")
    for name in _FEATURE_TOUCHES:
        path = repo / "logpipe" / f"{name}.py"
        path.write_text(path.read_text(encoding="utf-8")
                        + _feature_block(name), encoding="utf-8")
    readme = repo / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\n".join([
        "",
        "## JSON output (new)",
        "",
        "Every stage can now emit JSON via `<module>_to_json(records)` and",
        "`logpipe.json_out` writes filtered record sets to disk.",
        "",
    ]), encoding="utf-8")
    changelog = repo / "CHANGELOG.md"
    changelog.write_text(changelog.read_text(encoding="utf-8") + "\n".join([
        "",
        "## Unreleased",
        "- add JSON output across cli, formatter, filters, config, stats",
        "- new module logpipe.json_out with severity filtering",
        "",
    ]), encoding="utf-8")
    _run_git(repo, "add", ".")
    return repo


_TRACEBACK = [
    "Traceback (most recent call last):",
    '  File "/srv/logpipe/router.py", line 214, in route_batch',
    "    shard = shard_map[record.tenant]",
    "KeyError: 'shard_map'",
]


def make_log_fixture(dest: Path) -> Path:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    lines = []
    for i in range(4000):
        ts = (f"2026-07-14T{(i // 3600) % 24:02d}:"
              f"{(i // 60) % 60:02d}:{i % 60:02d}Z")
        if 1500 <= i < 1500 + len(_TRACEBACK):
            lines.append(f"{ts} ERROR {_TRACEBACK[i - 1500]}")
        elif i == 2200:
            lines.append(f"{ts} CRITICAL worker-3 killed: Out of memory "
                         "(OOM) rss=2147MB")
        elif i % 30 == 0:
            lines.append(f"{ts} ERROR connection refused to db-primary:5432 "
                         f"(attempt {i // 30})")
        elif i % 97 == 0:
            lines.append(f"{ts} WARN retry storm: backoff exhausted for "
                         f"job-{i % 400}")
        else:
            lines.append(f"{ts} INFO request handled "
                         f"path=/api/v1/items/{i % 50} status=200 "
                         f"dur_ms={(i * 7) % 140}")
    (dest / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("commit", "log"):
        print("usage: fixtures.py commit|log <dest>", file=sys.stderr)
        return 2
    dest = Path(argv[1])
    made = make_commit_fixture(dest) if argv[0] == "commit" else make_log_fixture(dest)
    print(made)
    return 0


if __name__ == "__main__":
    sys.exit(main())
