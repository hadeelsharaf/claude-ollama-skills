"""Report the plugin's always-on catalog cost (skill/agent descriptions).

Descriptions are billed into every Claude Code session; bodies only on
invocation. `--budget` enforces the caps shared with scripts/validate_repo.py.
Stdlib only; safe in CI.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from validate_repo import (CATALOG_BUDGET, DESC_CAP_AGENT, DESC_CAP_SKILL,
                           parse_frontmatter)


def catalog_rows(root: Path) -> list[dict]:
    rows = []
    for skill_md in sorted((root / "skills").glob("*/SKILL.md")):
        try:
            fields, body = parse_frontmatter(skill_md)
        except ValueError:
            fields, body = {}, skill_md.read_text(encoding="utf-8-sig")
        desc = fields.get("description", "")
        rows.append({"kind": "skill", "name": skill_md.parent.name,
                     "desc_chars": len(desc), "body_chars": len(body)})
    for agent_md in sorted((root / "agents").glob("*.md")):
        try:
            fields, body = parse_frontmatter(agent_md)
        except ValueError:
            fields, body = {}, agent_md.read_text(encoding="utf-8-sig")
        desc = fields.get("description", "")
        rows.append({"kind": "agent", "name": agent_md.stem,
                     "desc_chars": len(desc), "body_chars": len(body)})
    return rows


def catalog_total(rows: list[dict]) -> int:
    return sum(r["desc_chars"] for r in rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", action="store_true",
                        help="exit 1 when a cap or the total budget is exceeded")
    args = parser.parse_args(argv)

    rows = catalog_rows(REPO_ROOT)
    over = []
    print(f"{'kind':6} {'name':22} {'desc':>5} {'~tok':>5} {'body':>7}")
    for r in rows:
        cap = DESC_CAP_SKILL if r["kind"] == "skill" else DESC_CAP_AGENT
        mark = ""
        if r["desc_chars"] > cap:
            mark = f"  OVER cap {cap}"
            over.append(f"{r['name']}: {r['desc_chars']} > {cap}")
        print(f"{r['kind']:6} {r['name']:22} {r['desc_chars']:5}"
              f" {r['desc_chars'] // 4:5} {r['body_chars']:7}{mark}")
    total = catalog_total(rows)
    print(f"\ncatalog total: {total} chars (~{total // 4} tokens);"
          f" budget {CATALOG_BUDGET}")
    if total > CATALOG_BUDGET:
        over.append(f"total {total} > budget {CATALOG_BUDGET}")
    if over and args.budget:
        for line in over:
            print(f"BUDGET FAIL: {line}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
