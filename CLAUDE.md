# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **Claude Code plugin** (`ollama-skills`) that delegates small, mechanical subtasks to a
local Ollama model: commit messages, shell command drafts, small code, lint-fix
suggestions, and log/text/git-history digests. Claude plans and reviews; the local model drafts.
The privacy win is the point — big private inputs (staged diffs, file bodies, container
logs) are read by the local script and never enter Claude's context; only a small drafted
result comes back.

There is **no build step and no dependency install**. One Python file
(`scripts/ollama_ask.py`, stdlib only, 3.9+) is the entire runtime; everything else is
markdown prompt contracts and JSON manifests.

## Commands

```powershell
python -m unittest discover -s tests -v     # full unit suite (fake Ollama server, no network)
python -m unittest tests.test_ollama_ask.OllamaAskTests.test_resolve_model_flag_wins -v   # one test
python scripts/validate_repo.py             # manifests + skill/agent frontmatter + compile check
```

Use `python` on Windows, `python3` on macOS/Linux. Both commands above must pass before a
PR — that is exactly what `.github/workflows/ci.yml` runs (Ubuntu + Windows).

Opt-in end-to-end runs need a real local Ollama and are gated by an env var:

```bash
RUN_OLLAMA_E2E=1 python tests/e2e_local.py          # real model; prints per-step timings
OLLAMA_SKILLS_DEBUG=1 python scripts/ollama_ask.py ...   # model/timeout/options trace on stderr
```

This e2e script exits 0 with a "skipped" message when its env var is unset, so it is
safe to run blind.

`benchmarks/measure_ab.py` is **PAID**: ~18 headless opus sessions at defaults; never run
it in tests or CI — pilot first with `--runs 1 --tasks summarize`.
`evals/` holds paid `claude plugin eval` cases, gated behind an early-access CLI feature.

## Architecture

Three layers, coupled by an **exit-code contract** rather than by imports:

1. **`scripts/ollama_ask.py`** — the only runtime code. Subcommands: `health`, `models`,
   `warmup`, `ask`, `commit-msg`, `commit-push`, `pr-desc`, `pr-create`, `stats`, `draft-command`, `draft-code`, `fix-lint`,
   `summarize`. All model calls funnel through `generate()` → `stream_generate()`
   (`POST /api/generate`, `stream: true`, `think: false`); the socket read timeout *is* the
   stall detector. Task profiles (`TASK_DEFAULTS` for `commit|shell|code|general|summarize`)
   set max tokens, temperature, and `num_ctx`.
2. **`skills/*/SKILL.md`** — eight skills. Each is a prompt contract telling Claude which
   subcommand to run, how to review the draft, which commands are deny-listed, and what to
   do on each exit code. Skills are the safety layer; the script only enforces what a
   script can (branch gating, input budgets, syntax checks).
3. **`agents/*.md`** — three background subagents (`ollama-coder`, `ollama-git`,
   `ollama-ops`), all `model: haiku`, each with a restricted `tools:` list. They duplicate
   the corresponding skill's workflow and safety wording on purpose.

`.claude-plugin/plugin.json` + `marketplace.json` make it installable; skills and agents
are discovered by directory convention, so adding a folder is all the wiring there is.
Skills reference the script as `${CLAUDE_PLUGIN_ROOT}/scripts/ollama_ask.py`
(`$OLLAMA_SKILLS_HOME/...` for manual installs) — keep both forms when editing.

### The exit-code contract

`0` ok · `2` bad usage / over budget · `3` Ollama unreachable · `4` model missing ·
`5` stall/timeout · `6` output failed validation · `7` protected branch refused ·
`8` git/gh/glab command failed · `1` unexpected · `130` interrupted.

These codes are how a failed delegation degrades gracefully: on 3/4/5/6 the skill tells
Claude to do the task itself and say so. The codes appear in **four** places that must
stay in sync — `ollama_ask.py` constants and module docstring, the README table, and each
skill's Troubleshooting/Fallback section. Never renumber one alone.

### Model resolution

`--model` flag → `OLLAMA_SKILLS_MODEL_<TASK>` → `OLLAMA_SKILLS_MODEL` →
`./.ollama-skills.json` → `~/.ollama-skills.json` → auto-detect via `PREFERENCES`
(first installed model whose name starts with a listed prefix). Auto-detect never falls
back to an arbitrary installed model — embedding models must lose. Auto-detect also skips any candidate whose file size exceeds free RAM (best-effort — it stands down when either number is unknown; explicit pins bypass the gate, and `models` prints what was skipped and why). In `PREFERENCES`,
`summarize` deliberately lists `qwen3` **last** because a digest makes many calls and a
slow 8B model would be unusable; don't "fix" that ordering. `python scripts/ollama_ask.py
models --json` prints the resolved model and its source for every task.

## Invariants that will break CI or the product if ignored

- **Standard library only**, at runtime and in tests. No pip packages.
- **Every `SKILL.md` and `agents/*.md` body must contain the literal string
  `UNTRUSTED DRAFT`** — `validate_repo.py` fails without it. Skill `description` must also
  contain "use when", and skill `name` must equal its folder name (agent `name` its
  filename).
- **Frontmatter stays single-line `key: value` pairs.** `validate_repo.py` ships a
  hand-rolled stdlib parser with no YAML support; lists or multi-line strings fail it.
- **Skill prose is unit-tested.** `test_denylist_covers_*`,
  `test_git_history_skill_bans_patches`, `test_digest_skill_bans_reading_the_file`,
  `test_digest_skill_keeps_both_privacy_rules`, `test_removed_skills_are_gone`,
  `test_push_safety_wording_present`, and `test_pr_skill_safety_wording_present` assert on
  exact substrings inside markdown files (`docker system prune`, `--privileged`,
  `kubectl drain`, `--force-with-lease`, `never the model`, `never shows patch content`,
  …). Rewording a skill's safety section is a test-touching change, by design — the tests
  exist so a silent reword can't quietly remove a guardrail.
- **Catalog budget is enforced, not aspirational.** The constants live in
  `validate_repo.py` (`DESC_CAP_SKILL`, `DESC_CAP_AGENT`, `CATALOG_BUDGET`) — never raise
  them casually; `python benchmarks/measure_catalog.py` reports the current spend per
  skill/agent and the total. Catalog text is also cache-priced: every description edit
  re-writes the cached system prompt for every user session, so batch description changes
  into releases rather than shipping them piecemeal.
- **Privacy invariant:** skills forbid Claude from reading what was delegated —
  no `git diff --cached` (only `--stat`), no `git log -p`/`--patch` in
  `ollama-digest`. Preserve that when editing workflows.
- **`commit-push` can never force-push or delete a branch.** Its argv is built from fixed
  literals plus `--message`/`--remote`/`--allow-protected` (and the ledger-only
  `--outcome`/`--outcome-task`); there is no flag that can
  smuggle in `--force` or a refspec. `main`/`master` require `--allow-protected`, which
  Claude may add only after the user explicitly insists. Keep it that way.
- **`pr-create` is draft-by-default.** Its argv is fixed literals plus
  `--title`/`--body`/`--base`/`--remote`/`--ready` (and the ledger-only
  `--outcome`/`--outcome-task`); `--ready` is the only escalation and
  the head branch can never be main/master. Keep it that way.
- **The usage ledger stores counts only** — never prompt content, paths, or repo
  names; ledger writes are best-effort and must never break a command.
- Nothing may bypass Claude Code's permission prompts.
- Conventional Commits for this repo's own history; every behavior change gets a test.
- **Trust tiers are enforced, not aspirational.** `draft-command` refuses
  deny-list matches (exit 6) and marks read-only drafts on stderr;
  `summarize` prints a counts-only `coverage:` line; `pr-desc` refuses
  oversized changesets (exit 2); `record-outcome` writes counts-only verdict
  rows. The canonical tier sentences in skills/agents are pin-tested -
  rewording them is a test-touching change, by design.

## Cross-platform details worth knowing

- Configs are read with `utf-8-sig` (Windows editors and PowerShell write BOMs);
  `main()` reconfigures stdin/stdout/stderr to UTF-8 because Claude Code pipes default to
  the ANSI codepage on Windows and crash on non-ASCII.
- Progress dots go to stderr and are suppressed automatically when stderr isn't a TTY.
- `.gitattributes` pins LF for everything except `.ps1/.cmd/.bat` (CRLF).
- In `build_parser()`, `--task` must **not** live on the shared `parents=[common]` parser:
  argparse shares the action object, so `set_defaults(task=...)` on one subparser would
  change the default for all of them.

## Adding things

**A new skill:** copy a `skills/*` folder, keep the "Rules (do not skip)" section's shared
rules word for word (untrusted draft, fallback on exit 3/4/5/6, only documented flags),
write a `description` that says what it does *and* when to use it, then run
`validate_repo.py`. If it introduces a deny-list, add a `test_denylist_covers_*`-style
assertion.

**A new subcommand:** add `cmd_*`, register it in `HANDLERS` and `build_parser()`, extend
the module docstring, add a task profile to `TASK_DEFAULTS`/`PREFERENCES` if it needs one,
and add contract tests against the fake Ollama server in `tests/test_ollama_ask.py`
(`FakeOllamaHandler` canned responses + `run_cli`/`run_stdin` helpers). Add an e2e step to
`tests/e2e_local.py` if it touches a real model path.

## Docs

`docs/` holds DESIGN (spec + measured CPU numbers that justify the small default budgets),
SECURITY (threat model), ADVANCED (fully-offline options, per-hardware budget advice),
RESEARCH, and skill-tests (RED→GREEN skill probes; note that Scenarios A–E are *predicted*
reasoning outcomes, only F was run live).

`site/` is the public homepage — one hand-written `index.html` plus `style.css`, **no
build step and no dependencies**, same as the rest of the repo; `.github/workflows/pages.yml`
uploads the directory as-is. It deploys on push to **`main`** (not the default `draft`
branch) so the public page describes the version installed users actually have, which
means homepage copy ships at release time, not on merge to draft. `assets/hero.svg` is the
README's animated banner; every animated element there carries its final state as a plain
attribute and animates *from* zero, so a renderer that strips SMIL still shows the whole
frame — preserve that when editing it. Version numbers and measured claims appear in
`site/index.html` too, so a release bump touches it alongside `plugin.json`.

`docs/PLAN.md` and `docs/PLAN-v0.2.md` are **gitignored internal planning docs** — they may
exist on a given machine but are not part of the repo, so never link to them from shipped
docs. `docs/superpowers/` (specs, plans, benchmark notes) is likewise local-only — gitignored, kept on disk, never linked from shipped docs.
Keep `plugin.json`'s `version` in step with the newest CHANGELOG entry when releasing.
