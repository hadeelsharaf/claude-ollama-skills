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

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CONVENTIONAL_MODELS = {"haiku", "sonnet", "opus", "fable", "inherit"}


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
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(path, f"invalid JSON: {exc}")
        return None
    missing = [key for key in required if key not in data]
    if missing:
        fail(path, f"missing keys: {missing}")
        return None
    ok(path)
    return data


def check_skill(path: Path) -> None:
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
    elif "use when" not in description.lower():
        fail(path, "description must say when to use the skill ('Use when ...')")
    elif "UNTRUSTED DRAFT" not in body:
        fail(path, "body must contain the untrusted-draft safety rule")
    elif name != path.parent.name:
        fail(path, f"name {name!r} must match folder {path.parent.name!r}")
    else:
        ok(path, f"skill '{name}'")


def check_agent(path: Path) -> None:
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
    if not fields.get("description"):
        problems.append("missing 'description'")
    model = fields.get("model", "")
    if not model:
        problems.append("missing 'model'")
    elif model not in CONVENTIONAL_MODELS and not model.startswith("claude-"):
        problems.append(f"unexpected model {model!r}")
    if not fields.get("tools"):
        problems.append("missing 'tools'")
    if "UNTRUSTED DRAFT" not in body:
        problems.append("body must contain the untrusted-draft safety rule")
    if problems:
        fail(path, "; ".join(problems))
    else:
        ok(path, f"agent '{name}'")


def main() -> int:
    check_json(ROOT / ".claude-plugin" / "plugin.json", ["name", "version", "description"])
    check_json(ROOT / ".claude-plugin" / "marketplace.json", ["name", "owner", "plugins"])

    example = ROOT / "config" / ".ollama-skills.example.json"
    if example.exists():
        check_json(example, ["host", "tasks"])

    skills_dir = ROOT / "skills"
    if skills_dir.is_dir():
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            check_skill(skill_md)
        for folder in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            if not (folder / "SKILL.md").exists():
                fail(folder, "skill folder without SKILL.md")

    agents_dir = ROOT / "agents"
    if agents_dir.is_dir():
        for agent_md in sorted(agents_dir.glob("*.md")):
            check_agent(agent_md)

    core = ROOT / "scripts" / "ollama_ask.py"
    if core.exists():
        try:
            py_compile.compile(str(core), doraise=True)
            ok(core, "compiles")
        except py_compile.PyCompileError as exc:
            fail(core, f"does not compile: {exc}")

    if FAILURES:
        print(f"\n{len(FAILURES)} problem(s) found.")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
