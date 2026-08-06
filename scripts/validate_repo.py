#!/usr/bin/env python3
"""Validate repo structure: manifests, skill frontmatter, agent frontmatter.

Run from anywhere: python scripts/validate_repo.py
Prints one line per checked file. Exits 1 if anything fails.
Standard library only.
"""
from __future__ import annotations

import json
import py_compile
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILURES: list[str] = []

# Always-on catalog budget: descriptions are billed into every Claude Code
# session. Measured 0.5.0 baseline: 2,583 chars. Raising these numbers is a
# product decision, not a formatting fix.
DESC_CAP_SKILL = 330
DESC_CAP_AGENT = 250
CATALOG_BUDGET = 2700

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CONVENTIONAL_MODELS = {"haiku", "sonnet", "opus", "fable", "inherit"}

# Reference files loaded at invocation time by a pointer in the body. A
# pointer at a missing file loads nothing and fails silently, so every
# UPPERCASE.md token in a skill body must exist in that skill's folder,
# and every skills/<name>/UPPERCASE.md token in an agent body must exist
# relative to the repo root. Self/doc mentions are whitelisted.
REF_TOKEN_SKILL = re.compile(r"\b([A-Z][A-Z0-9-]*\.md)\b")
REF_TOKEN_AGENT = re.compile(r"\bskills/[a-z0-9-]+/[A-Z][A-Z0-9-]*\.md\b")
REF_WHITELIST = {"SKILL.md", "CLAUDE.md", "README.md"}


def check_skill_refs(path: Path, body: str) -> list[str]:
    missing = []
    for token in set(REF_TOKEN_SKILL.findall(body)):
        if token in REF_WHITELIST:
            continue
        if not (path.parent / token).is_file():
            missing.append(token)
    return sorted(missing)


def check_agent_refs(body: str) -> list[str]:
    missing = []
    for token in set(REF_TOKEN_AGENT.findall(body)):
        if not (ROOT / token).is_file():
            missing.append(token)
    return sorted(missing)


def ok(path: Path, note: str = "") -> None:
    rel = path.relative_to(ROOT)
    print(f"OK   {rel}{(' - ' + note) if note else ''}")


def fail(path: Path, reason: str) -> None:
    rel = path.relative_to(ROOT)
    print(f"FAIL {rel}: {reason}")
    FAILURES.append(str(rel))


FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.DOTALL)


def parse_frontmatter(path: Path) -> tuple[dict, str]:
    """Parse simple single-line `key: value` frontmatter. Returns (fields, body).

    This repo intentionally keeps frontmatter to single-line `key: value` pairs
    (no YAML lists or multi-line strings) so this stdlib parser stays honest.
    """
    text = path.read_text(encoding="utf-8-sig")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("missing or unterminated frontmatter ('---' fences)")
    fields: dict[str, str] = {}
    for line in match.group(1).strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"frontmatter line is not 'key: value': {line!r}")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip("'\"")
    return fields, match.group(2)


def check_json(path: Path, required: list[str]) -> dict | None:
    if not path.exists():
        fail(path, "file missing")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        fail(path, f"invalid JSON: {exc}")
        return None
    except OSError as exc:
        fail(path, f"unreadable: {exc}")
        return None
    missing = [key for key in required if key not in data]
    if missing:
        fail(path, f"missing keys: {missing}")
        return None
    ok(path)
    return data


def check_skill(path: Path, desc_tracker: list[tuple[int, Path]] | None = None) -> None:
    try:
        fields, body = parse_frontmatter(path)
    except ValueError as exc:
        fail(path, str(exc))
        return
    name = fields.get("name", "")
    description = fields.get("description", "")
    if not name:
        fail(path, "frontmatter missing 'name'")
    elif len(name) > 64:
        fail(path, f"name longer than 64 chars ({len(name)})")
    elif not KEBAB.match(name):
        fail(path, f"name is not kebab-case: {name!r}")
    elif not description:
        fail(path, "frontmatter missing 'description'")
    elif len(description) > 1024:
        fail(path, f"description longer than 1024 chars ({len(description)})")
    elif len(description) > DESC_CAP_SKILL:
        fail(path, f"description longer than {DESC_CAP_SKILL} chars ({len(description)}) - the catalog bills every session; trim it")
    elif "use when" not in description.lower():
        fail(path, "description must say when to use the skill ('Use when ...')")
    elif "UNTRUSTED DRAFT" not in body:
        fail(path, "body must contain the untrusted-draft safety rule")
    elif name != path.parent.name:
        fail(path, f"name {name!r} must match folder {path.parent.name!r}")
    else:
        missing = check_skill_refs(path, body)
        if missing:
            fail(path, f"body references missing file(s): {missing}")
        else:
            ok(path, f"skill '{name}'")
            if desc_tracker is not None:
                desc_tracker.append((len(description), path))


def check_agent(path: Path, desc_tracker: list[tuple[int, Path]] | None = None) -> None:
    try:
        fields, body = parse_frontmatter(path)
    except ValueError as exc:
        fail(path, str(exc))
        return
    name = fields.get("name", "")
    problems = []
    if not name:
        problems.append("missing 'name'")
    elif not KEBAB.match(name):
        problems.append(f"name not kebab-case: {name!r}")
    elif name != path.stem:
        problems.append(f"name {name!r} must match filename {path.stem!r}")
    description = fields.get("description", "")
    if not description:
        problems.append("missing 'description'")
    elif len(description) > DESC_CAP_AGENT:
        problems.append(f"description longer than {DESC_CAP_AGENT} chars ({len(description)}) - the catalog bills every session; trim it")
    model = fields.get("model", "")
    if not model:
        problems.append("missing 'model'")
    elif model not in CONVENTIONAL_MODELS and not model.startswith("claude-"):
        problems.append(f"unexpected model {model!r}")
    if not fields.get("tools"):
        problems.append("missing 'tools'")
    if "UNTRUSTED DRAFT" not in body:
        problems.append("body must contain the untrusted-draft safety rule")
    missing = check_agent_refs(body)
    if missing:
        problems.append(f"body references missing file(s): {missing}")
    if problems:
        fail(path, "; ".join(problems))
    else:
        ok(path, f"agent '{name}'")
        if desc_tracker is not None and description:
            desc_tracker.append((len(description), path))


def check_exit_code_sync(script: Path, readme: Path) -> None:
    """CLAUDE.md: the exit-code contract lives in four places that must stay
    in sync. This pins the machine-checkable pair — the script's constants and
    module docstring against the README's exit-code list. The skills' fallback
    wording is covered by the prose tests."""
    src = script.read_text(encoding="utf-8-sig")
    doc = re.search(r"Exit codes:(.*?)\"\"\"", src, re.DOTALL)
    if not doc:
        fail(script, "module docstring lost its 'Exit codes:' section")
        return
    doc_codes = {int(n) for n in re.findall(r"\b(\d+)\b", doc.group(1))}
    const_codes = {int(n) for n in re.findall(r"(?m)^EXIT_[A-Z_]+ = (\d+)", src)}
    missing_in_doc = sorted(const_codes - doc_codes)
    if missing_in_doc:
        fail(script, f"exit codes missing from the module docstring: {missing_in_doc}")
        return
    readme_text = readme.read_text(encoding="utf-8-sig")
    para = re.search(r"Exit codes:(.*?)\n\r?\n", readme_text, re.DOTALL)
    if not para:
        fail(readme, "README lost its 'Exit codes:' list")
        return
    readme_codes = {int(n) for n in re.findall(r"`(\d+)`", para.group(1))}
    missing = sorted(doc_codes - readme_codes)
    if missing:
        fail(readme, f"exit codes missing from the README list: {missing}")
        return
    ok(readme, "exit codes in sync with the script")


def main() -> int:
    check_json(ROOT / ".claude-plugin" / "plugin.json", ["name", "version", "description"])
    check_json(ROOT / ".claude-plugin" / "marketplace.json", ["name", "owner", "plugins"])

    example = ROOT / "config" / ".ollama-skills.example.json"
    if example.exists():
        check_json(example, ["host", "tasks"])

    desc_tracker: list[tuple[int, Path]] = []

    skills_dir = ROOT / "skills"
    if skills_dir.is_dir():
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            check_skill(skill_md, desc_tracker)
        for folder in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            if not (folder / "SKILL.md").exists():
                fail(folder, "skill folder without SKILL.md")

    agents_dir = ROOT / "agents"
    if agents_dir.is_dir():
        for agent_md in sorted(agents_dir.glob("*.md")):
            check_agent(agent_md, desc_tracker)

    core = ROOT / "scripts" / "ollama_ask.py"
    if core.exists():
        try:
            py_compile.compile(str(core), doraise=True)
            ok(core, "compiles")
        except py_compile.PyCompileError as exc:
            fail(core, f"does not compile: {exc}")

    readme = ROOT / "README.md"
    if core.exists() and readme.exists():
        check_exit_code_sync(core, readme)

    # Check total catalog budget
    total_desc = sum(length for length, _ in desc_tracker)
    if total_desc > CATALOG_BUDGET:
        desc_tracker_sorted = sorted(desc_tracker, reverse=True)
        top3 = desc_tracker_sorted[:3]
        top3_str = "; ".join(f"{length} chars: {path.relative_to(ROOT)}" for length, path in top3)
        print(f"FAIL catalog: total descriptions {total_desc} exceed budget {CATALOG_BUDGET} - top 3 contributors: {top3_str}")
        FAILURES.append("catalog")

    if FAILURES:
        print(f"\n{len(FAILURES)} problem(s) found.")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
