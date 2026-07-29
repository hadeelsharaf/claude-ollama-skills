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

## What's new in v0.3

- **Draft PRs from your branch** — the `ollama-pr` skill: the local model drafts the
  title and description from commit subjects (never patches), Claude reviews, and one
  gated step opens a **draft** PR via gh or glab. `--ready` only when you say so.
- **Free-RAM gate in model auto-detect** — a model bigger than free RAM is skipped
  (and `models` tells you why); explicit picks are never gated.
- **GPU-measured model fleet** — defaults, docs, and speed tables refreshed against
  measured numbers (`qwen2.5-coder:1.5b`, `gemma2:2b`, RTX 4050 Laptop).

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
| "explain why this container keeps crashing" | `ollama-docker` skill (logs → local summarize, checked) |
| "why is this pod crashlooping?" | `ollama-k8s` skill (describe+events+logs → local summarize; context echoed) |
| "what changed on this branch this week?" | `ollama-git-history` skill (compact log → local summarize) |
| "open a PR for this branch" | `ollama-pr` skill (local model drafts the description; created as a draft PR via gh/glab) |

Skills can also be invoked directly: `/ollama-skills:ollama-commit`.
Background agents (run on cheap haiku): `@agent-ollama-skills:ollama-coder`,
`@agent-ollama-skills:ollama-git`, `@agent-ollama-skills:ollama-ops`.

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
- `devstral-small-2:latest` — 15.2 GB; auto-detect **skips it on this machine**
  (bigger than free RAM — the `models` command shows the skip and why). On a
  machine where it fits, it is auto-picked for code tasks.

**If you clone this, model choice is yours.** Set models in `.ollama-skills.json`
(copy `config/.ollama-skills.example.json`) or env vars — any Ollama model works.
With no config at all, the script picks a model per task from a tested preference
list — or tells you clearly when nothing installed fits, instead of guessing
(`python scripts/ollama_ask.py models` shows the result and why).

## Measured speed (development machine: 16 GB RAM, NVIDIA GeForce RTX 4050 Laptop GPU, 6 GB VRAM)

Real numbers from `tests/e2e_local.py` and the design-phase measurements — so you
can set expectations before you wait. The small models in the table (qwen2.5-coder:1.5b,
gemma2:2b) ran 100% on the GPU; devstral-small-2 (15.2 GB) does not fit in 6 GB VRAM
and is split across CPU/GPU (see its row below).

| Operation | qwen2.5-coder:1.5b | gemma2:2b |
|---|---|---|
| Model load (cold start) | 6.4 s | 6.2 s |
| `ask` (tiny prompt, warm) | 2.4–2.6 s | 2.5–2.8 s |
| `commit-msg` (small staged change) | 2.6–2.8 s | — |
| `draft-command` | 3.4 s | — |
| `summarize` (single-shot, ~3k chars) | — | 8.0–8.3 s |
| `devstral-small-2:latest` (15.2 GB) | slow but works, with cold-stall risk (64–68 s cold, 5.2 s warm; one cold attempt stalled > 120 s) | |

The 2,500-char input budget, and `commit-msg` sending a compact diff summary instead
of full hunks, both trace back to the original CPU-only prefill measurements in
[docs/DESIGN.md](docs/DESIGN.md) §3 (~7 tok/s prefill on a ~2,758-token prompt) — not
to the devstral row above. GPU owners can raise budgets in config
([docs/ADVANCED.md](docs/ADVANCED.md) §6 has per-hardware advice).

## Track what it saves you

Every local model call appends one line of **counts only** to
`.ollama-skills-usage.jsonl` in the repo root (or `~/.ollama-skills-usage.jsonl`
outside a repo). The file is kept out of git automatically via
`.git/info/exclude`. No prompt content, file paths, or repo names are ever
recorded — a unit test enforces that.

```json
{"v": 1, "ts": "2026-07-29T21:04:00+00:00", "cmd": "commit-msg", "task": "commit",
 "model": "qwen2.5-coder:1.5b", "prompt_tokens": 412, "output_tokens": 18,
 "duration_s": 2.7, "returned_chars": 52, "avoided_chars": 9184, "delivered": true}
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
(config). Move the file with `"usage_log_path": "<path>"`.

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
skills/            nine SKILL.md folders (ask, commit, precommit, shell, code, docker, k8s, git-history, pr)
agents/            three subagents (coder, git, ops) — model: haiku
scripts/           ollama_ask.py (the one runtime file) + validate_repo.py
config/            example config
templates/         CLAUDE.md routing snippet
tests/             unit tests (fake Ollama server) + opt-in real e2e
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
