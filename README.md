# claude-ollama-skills

Claude Code skills and agents that hand small tasks to a **local Ollama model**:
commit messages, pre-commit fixes, simple shell chores, and small code drafts.
Claude stays the brain — it plans, checks, and applies. Your local model is the
worker.

**Why:**

- **Privacy** — your staged diff and code stay on your machine for delegated tasks.
  Only the small drafted result enters Claude's context.
- **Fewer cloud tokens** — bulk mechanical text work happens locally.
- **Offline subtasks** — the drafting part works without cloud access.

> **Honest limits, read first:** Claude Code itself still needs the internet — these
> skills make *subtasks* local, not Claude. Small local models are weak; every skill
> forces Claude to review their output as an untrusted draft before using it. And
> CPU-only machines are slow with big models — the defaults here are tuned for that
> (see the measured numbers below). Fully offline options: [docs/ADVANCED.md](docs/ADVANCED.md).

## What's new in v0.5

- **`ollama-digest` skill**: merges `ollama-logs` and `ollama-git-history` into
  one catalog entry for log/text-file and git-history digests — same
  workflows and safety rules as before.
- **Kubernetes support parked**: `ollama-k8s` removed until local-delegation
  cost savings are proven; last shipped in 0.4.0 (tag `ollama-skills--v0.4.0`).
- **Catalog trimmed and budget-enforced**: always-on skill/agent descriptions
  drop from 4,553 to 2,583 chars (~1,140 → ~645 tokens per session);
  `validate_repo.py` now enforces per-description caps and a total catalog
  budget so the overhead cannot silently regrow
  (`python benchmarks/measure_catalog.py` reports the current spend).

Earlier releases: see [CHANGELOG.md](CHANGELOG.md).

## Requirements

- [Ollama](https://ollama.com) running locally (tested with 0.32) and at least one model
- Python 3.9+ (standard library only — nothing to pip install)
- git, Claude Code 2.x
- Optional, for the PR skill: [gh](https://cli.github.com) (GitHub) or [glab](https://gitlab.com/gitlab-org/cli) (GitLab), authenticated

## Install

From GitHub:

```
/plugin marketplace add hadeelsharaf/claude-ollama-skills
/plugin install ollama-skills@claude-ollama-skills
```

From a local clone:

```
/plugin marketplace add D:\path\to\claude-ollama-skills
/plugin install ollama-skills@claude-ollama-skills
```

Manual install without the plugin system: see [docs/ADVANCED.md](docs/ADVANCED.md) §1.

Installs track the `main` release branch. Updates arrive with `/plugin update`
and only when a release bumps the plugin version — day-to-day development on
the `draft` branch never reaches installed users.

Then paste the routing block from
[templates/CLAUDE.md-snippet.md](templates/CLAUDE.md-snippet.md) into your project's
CLAUDE.md — research shows delegation only happens reliably when CLAUDE.md says when
to delegate.

## Scoping the install

Skill descriptions are loaded into every session's context (~645 tokens for
this plugin after 0.5.0; ~1,140 before). Two recommendations from our own
measurements:

- **Enable per project.** Enable the plugin at project scope
  (`claude plugin enable ollama-skills` with project/local settings scope) in
  the repos where you actually commit and digest logs, instead of globally.
- **Disable for headless/CI runs.** In our published A/B, one-shot
  `claude -p` sessions paid the catalog overhead without using the skills and
  came out net negative. If you script headless runs, disable the plugin for
  them.

## First-time setup (5 minutes, fresh machine)

1. Install [Ollama](https://ollama.com) and start it (`ollama serve`, or the desktop app).
2. Pull the two small models the docs' measured tables use:
   `ollama pull gemma2:2b` and `ollama pull qwen2.5-coder:1.5b`
   (any Ollama models work — these are the tested defaults).
3. Install the plugin (see Install above).
4. In Claude Code, say: **"check the local model setup"**. You should see the
   Ollama version, your installed models with sizes, and free RAM — with a
   warning next to any model too big for your machine.

## Everyday use

Just ask Claude in plain words:

| You say | What runs |
|---|---|
| "check the local model setup" | `ollama-ask` skill → `health` |
| "commit my staged changes, use the local model" | `ollama-commit` skill (diff never enters Claude's context) |
| "pre-commit is failing, fix it" | `ollama-precommit` skill (deterministic fixers first) |
| "zip the logs folder" | `ollama-shell` skill (drafted command + safety check + permission prompt) |
| "write a small parser for X with the local model" | `ollama-code` skill (draft → line-by-line review) |
| "summarize errors in app.log" / "what changed on this branch this week?" | `ollama-digest` skill (log file, text, or git range → local digest; Claude never reads the raw input) |
| "explain why this container keeps crashing" | `ollama-docker` skill (logs → local summarize, checked) |
| "open a PR for this branch" | `ollama-pr` skill (local model drafts the description; created as a draft PR via gh/glab) |

Skills can also be invoked directly: `/ollama-skills:ollama-commit`.
Background agents (run on cheap haiku): `@agent-ollama-skills:ollama-coder`,
`@agent-ollama-skills:ollama-git`, `@agent-ollama-skills:ollama-ops`.

### Changed in 0.5.0

| Before (≤0.4.0) | Now |
|---|---|
| `ollama-logs`, `ollama-git-history` | `ollama-digest` |
| `ollama-k8s` | removed — parked until local-delegation cost savings are proven; last shipped in 0.4.0 (tag `ollama-skills--v0.4.0`) |

Same workflows and safety rules for the merged skills; less than 60% of the
old always-on catalog cost.

Everything goes through one bundled script — you can drive it by hand too:

```powershell
python scripts/ollama_ask.py health
python scripts/ollama_ask.py models
python scripts/ollama_ask.py warmup --task commit
python scripts/ollama_ask.py commit-msg
python scripts/ollama_ask.py draft-command "show the five newest files"
python scripts/ollama_ask.py draft-code --spec "csv to json converter" --lang python
python scripts/ollama_ask.py pr-desc
python scripts/ollama_ask.py pr-create --title "feat: x" --body "..."
docker logs --tail 200 web 2>&1 | python scripts/ollama_ask.py summarize --kind log
```

(`python3` on macOS/Linux.)

## Commit and push with the local model

The local model writes your commit message. Your code diff stays on your machine.
This saves Claude's tokens.

Claude reads only the short commit message. Claude checks it, then runs one step
called `commit-push`. This one step commits your change and pushes it.

Some things can never happen: force-push, and deleting a remote branch. There is no
flag to turn these on. They are always blocked.

Pushing to `main` or `master` works differently. Claude will not push to these
branches unless you say yes first. Claude only adds `--allow-protected` after you
ask for it. Your OK is required every time.

Before it pushes, Claude always shows you the target, like this: `branch -> remote`.

When you (or Claude) already know what the change is, say so — the draft only
has to word it:

```bash
python scripts/ollama_ask.py commit-msg --type feat --hint "add retry helper"
```

## Open a PR with the local model

`pr-desc` reads your branch's commit subjects locally and drafts a PR title and
description. Claude reviews them, then one gated step — `pr-create` — opens the PR
with `gh` (GitHub) or `glab` (GitLab), picked from your remote URL.

PRs are created as **drafts** by default. Claude adds `--ready` only when you
explicitly ask for a ready-for-review PR. Force-push, `--web`, and editing existing
PRs are not possible through this path, and a PR can never be opened from `main` or
`master` as the head branch.

## Models used during development

These are the models that were installed on the development machine and used while
building and testing this project:

- `qwen2.5-coder:1.5b` — coder pick: commit messages, shell drafts, small code
- `gemma2:2b` — general + summarize pick (the one small model that satisfies
  every task's preference list by itself)

**If you clone this, model choice is yours.** Set models in `.ollama-skills.json`
(copy `config/.ollama-skills.example.json`) or env vars — any Ollama model works.
With no config at all, the script picks a model per task from a tested preference
list — or tells you clearly when nothing installed fits, instead of guessing
(`python scripts/ollama_ask.py models` shows the result and why).

## Measured speed (development machine: 16 GB RAM, NVIDIA GeForce RTX 4050 Laptop GPU, 6 GB VRAM)

Real numbers from `tests/e2e_local.py` and the design-phase measurements — so you
can set expectations before you wait. Both models in the table (qwen2.5-coder:1.5b,
gemma2:2b) ran 100% on the GPU.

| Operation | qwen2.5-coder:1.5b | gemma2:2b |
|---|---|---|
| Model load (cold start) | 6.4 s | 6.2 s |
| `ask` (tiny prompt, warm) | 2.4–2.6 s | 2.5–2.8 s |
| `commit-msg` (small staged change) | 2.6–2.8 s | — |
| `draft-command` | 3.4 s | — |
| `summarize` (single-shot, ~3k chars) | — | 8.0–8.3 s |

The 2,500-char input budget, and `commit-msg` sending a compact diff summary instead
of full hunks, both trace back to the original CPU-only prefill measurements in
[docs/DESIGN.md](docs/DESIGN.md) §3 (~7 tok/s prefill on a ~2,758-token prompt).
GPU owners can raise budgets in config
([docs/ADVANCED.md](docs/ADVANCED.md) §6 has per-hardware advice).

## Track what it saves you

Every local model call appends one line of **counts only** to
`.ollama-skills-usage.jsonl` in the repo root (or `~/.ollama-skills-usage.jsonl`
outside a repo). The file is kept out of git automatically via
`.git/info/exclude`. No prompt content, file paths, or repo names are ever
recorded — a unit test enforces that.

```json
{"ts": "2026-07-29T21:04:00+00:00", "task": "commit", "model": "qwen2.5-coder:1.5b",
 "prompt_tokens": 412, "output_tokens": 18, "duration_s": 2.7, "returned_chars": 52,
 "v": 1, "cmd": "commit-msg", "delivered": true, "avoided_chars": 9184}
```

See the numbers:

```bash
python scripts/ollama_ask.py stats            # per-command table + totals
python scripts/ollama_ask.py stats --json     # machine-readable
python scripts/ollama_ask.py stats --since 7  # last week only
python scripts/ollama_ask.py stats --reset    # archive to .bak and start over
```

Honesty rules, so the numbers stay trustworthy:

- Local token counts are **real** — Ollama reports them per call.
- Cloud figures are **estimates**: `chars / 4`, labeled as such. "Avoided" is a
  counterfactual (what Claude would have read without delegation), and net
  savings subtract the draft Claude reads back.
- Review overhead (Claude reading `--stat` output and skill text) is not
  counted, so the cloud-side cost is slightly underestimated.
- Rejected drafts count their local tokens but claim **zero** savings.

Opt out any time: `OLLAMA_SKILLS_NO_USAGE=1` (env) or `"usage_log": false`
(config). Move the file with `"usage_log_path": "<path>"` — note a custom path
is not auto-added to `.git/info/exclude`, so add it to your own ignore rules.

### Measured, honestly: an A/B experiment

We ran the same two tasks (commit a staged multi-file change; summarize a
4,000-line log) through headless Claude Opus in two identical projects — one
with this plugin loaded, one without. n=3 per cell, neutral prompts (nothing
says "use the local model"), 2026-07 pricing. Full data:
`benchmarks/results/ab-published-0.4.0.json`; reproduce with
`python benchmarks/measure_ab.py`.

```
task       arm      ok    tokens (mean)  cache read  cost USD  local tokens  delegated
commit     without  3/3          16,832     207,895    0.3039             0  -
commit     with     2/3          19,376     259,136    0.3721         1,836  2
commit     with savings vs without: -15.1% (mean tokens, successful runs only)
summarize  without  3/3          16,556     155,221    0.2801             0  -
summarize  with     3/3          19,397     176,775    0.3275             0  0
summarize  with savings vs without: -17.2% (mean tokens, successful runs only)
```

Yes — **negative**. In unattended, neutral-prompt sessions the plugin *cost*
15-17% more cloud tokens than it saved. Three reasons, all visible in the
data:

- Ten skill descriptions load into every session (~2-3k tokens) whether or
  not anything delegates.
- Left to itself, the model delegates inconsistently (commit 2/3,
  summarize 0/3 here) — and un-delegated runs pay the overhead for nothing.
- Without the plugin, Claude doesn't actually read whole inputs anyway: it
  greps and tails the 338k-char log strategically, so "Claude would have read
  everything" is not what unattended sessions do.

### The confirmation arm: skills invoked deliberately

We then added a third arm — same tasks, same model, but the prompt names the
skill ("Use the ollama-commit skill ...") — to test whether deliberate
invocation flips the result
(`benchmarks/results/ab-published-0.4.0-directed.json`, reproduce with
`python benchmarks/measure_ab.py --arms without,directed`):

```
task       arm      ok    tokens (mean)  cache read  cost USD  local tokens  delegated
commit     without  3/3          16,682     204,445    0.3041             0  -
commit     directed 1/3          15,850     215,193    0.3000         1,848  1
commit     directed savings vs without: 5.0% (mean tokens, successful runs only)
summarize  without  3/3          16,021     169,313    0.2756             0  -
summarize  directed 0/3               0           0    0.0000             0  0

All arms opus, cold folders; cache reads excluded from the consumed metric. The directed arm's prompt names the skill; the other two arms share one neutral prompt.
```

What directed invocation changed, measured with the SAME yardstick on both
arms (per-run rows in the published JSONs): runs that invoked the local
model rose from 3/6 to **5/6**, and runs with a delivered local draft from
3/6 to 4/6 — a modest engagement gain, not a transformation. Delegated
summarize runs consumed 14-15k tokens, below the 16k baseline, because the
338k-char log body stayed local. The uncomfortable other half: strict task
success FELL from 5/6 to 1/6 unattended — the 2B local model's digest
dropped one of three planted facts, and headless agents stalled
mid-workflow (drafted the message, never committed). At these input sizes
cloud-token deltas stay inside session noise (±3k on a ~16k baseline); the
commit cell's +5.0% directed savings is a single successful run sitting
inside that noise band, so we do not claim it. Deliberate invocation
improves engagement; it does not make unattended sessions reliable.

So when IS it worth it? Interactively — a person directing the work across a
session with several delegations, which is how this plugin is actually used.
This repo's own development ledger shows that picture: at publication time,
47 delegated calls, ~36,700 real local tokens, roughly 33,000 cloud tokens
avoided net — and counting, since every dogfooded commit (including the one
that shipped this section) adds to it. Plus the part no token count
captures: **the diff and log bodies never entered cloud context at all**.
That privacy property, and full-coverage digests of files an unattended
model would only sample, are the honest headline.

### Making local delegation cost-effective

Four levers, in the order we'd reach for them (levers 1-2 and 4 are
measured; lever 3 is expected, not yet measured):

1. **Invoke skills explicitly** instead of hoping for auto-delegation
   (`/ollama-skills:ollama-commit`, `@agent-ollama-skills:ollama-git`, or a
   prompt that names the skill). Un-delegated sessions pay the catalog
   overhead and save nothing — deliberate invocation is what makes the local
   model actually get used (invoked 5/6 vs 3/6 here; see the directed arm
   above).
2. **Batch several delegations per session.** The ~2-3k-token skill catalog
   loads once per session; five commits in one session amortize it five ways.
3. **Drive delegation-heavy workflows from the bundled haiku agents**, not a
   frontier model — most of the with-arm's cost above is the frontier model
   itself, not the delegation.
4. **Watch your own ledger.** `python scripts/ollama_ask.py stats` shows the
   per-command net; if a command is negative for your usage (tiny inputs),
   stop delegating that one.

## Configuration

Resolution order for the model of each task:
`--model` flag → `OLLAMA_SKILLS_MODEL_<TASK>` env (`COMMIT|SHELL|CODE|GENERAL|SUMMARIZE`) →
`OLLAMA_SKILLS_MODEL` env → `./.ollama-skills.json` → `~/.ollama-skills.json` →
auto-detect from installed models.

`.ollama-skills.json` keys (see `config/.ollama-skills.example.json`):

| Key | Default | Meaning |
|---|---|---|
| `host` | `http://localhost:11434` | Ollama address (`OLLAMA_HOST` env also works) |
| `keep_alive` | `30m` | how long the model stays loaded after a call |
| `stall_seconds` | `90` | abort when no token arrives for this long |
| `total_timeout_seconds` | `480` | hard cap per call |
| `max_input_chars` | `2500` | input budget (CPU-friendly; raise on GPU) |
| `usage_log` | `true` | set `false` to disable the counts-only usage ledger |
| `usage_log_path` | per-repo | redirect the ledger to a custom path (not auto-excluded from git) |
| `tasks.<task>.model` | auto | model per task (`commit`, `shell`, `code`, `general`, `summarize`) |
| `tasks.<task>.max_tokens` | per task | output cap |
| `tasks.<task>.temperature` | per task | 0.0 for commands, 0.4 for commit messages |
| `tasks.<task>.num_ctx` | per task | context window size; only `summarize` sets one by default (2048) |

Exit codes: `0` ok · `2` bad usage / over budget · `3` Ollama unreachable ·
`4` model missing / none fits free RAM · `5` stall/timeout · `6` output failed validation ·
`7` protected branch refused · `8` git/gh/glab command failed.
Skills use these to fall back: **if the local model fails, Claude does the task
itself and says so** — a failed delegation never blocks work.

## Safety model (short version)

- Local model output is always an **untrusted draft**; Claude reviews before acting.
- Drafted shell commands pass a static deny-list and a scope check, then still go
  through Claude Code's normal permission prompt. Nothing here bypasses permissions.
- Lint fixes are suggest-only and must touch just the flagged lines.
- These rules are behavior-tested with small-model (claude-haiku) probes:
  [docs/skill-tests.md](docs/skill-tests.md).
- Full threat model: [docs/SECURITY.md](docs/SECURITY.md).

## Repo map

```
.claude-plugin/    plugin + marketplace manifests
skills/            eight SKILL.md folders (ask, code, commit, digest, docker, pr, precommit, shell)
agents/            three subagents (coder, git, ops) — model: haiku
scripts/           ollama_ask.py (the one runtime file) + validate_repo.py
config/            example config
templates/         CLAUDE.md routing snippet
tests/             unit tests (fake Ollama server) + opt-in real e2e
benchmarks/        A/B token-consumption runner (paid, opt-in, never in CI);
                   measure_catalog.py (free, stdlib, safe anywhere)
evals/             claude plugin eval quality cases (paid, opt-in, never in CI)
docs/              DESIGN, RESEARCH, ADVANCED, SECURITY, skill-tests
.github/workflows  CI: unit tests (Ubuntu+Windows), validation, opt-in e2e
```

## Development

```bash
python -m unittest discover -s tests -v   # unit tests (no Ollama needed)
python scripts/validate_repo.py           # manifest + frontmatter checks
RUN_OLLAMA_E2E=1 python tests/e2e_local.py  # real e2e (needs local Ollama)
```

The first two commands are what CI runs on every push; the e2e run is manual
(workflow_dispatch). The design and the measurements behind the
default budgets are in [docs/DESIGN.md](docs/DESIGN.md); how to add a skill is in
[CONTRIBUTING.md](CONTRIBUTING.md).

License: [MIT](LICENSE). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
