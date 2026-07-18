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

## Requirements

- [Ollama](https://ollama.com) running locally (tested with 0.32) and at least one model
- Python 3.9+ (standard library only — nothing to pip install)
- git, Claude Code 2.x

## Install

From GitHub (after this repo is published):

```
/plugin marketplace add <owner>/claude-ollama-skills
/plugin install ollama-skills@claude-ollama-skills
```

From a local clone:

```
/plugin marketplace add D:\path\to\claude-ollama-skills
/plugin install ollama-skills@claude-ollama-skills
```

Manual install without the plugin system: see [docs/ADVANCED.md](docs/ADVANCED.md) §1.

Then paste the routing block from
[templates/CLAUDE.md-snippet.md](templates/CLAUDE.md-snippet.md) into your project's
CLAUDE.md — research shows delegation only happens reliably when CLAUDE.md says when
to delegate.

## Quick start

Check the setup, then just ask Claude in plain words:

| You say | What runs |
|---|---|
| "check the local model setup" | `ollama-ask` skill → `health` |
| "commit my staged changes, use the local model" | `ollama-commit` skill (diff never enters Claude's context) |
| "pre-commit is failing, fix it" | `ollama-precommit` skill (deterministic fixers first) |
| "zip the logs folder" | `ollama-shell` skill (drafted command + safety check + permission prompt) |
| "write a small parser for X with the local model" | `ollama-code` skill (draft → line-by-line review) |

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
```

(`python3` on macOS/Linux.)

## Models used during development

These are the models that were installed on the development machine and used while
building and testing this project:

- `qwen3:8b` — default quality pick for shell/code/general tasks
- `llama3.2:1b` — fast lane, pulled during development for quick tasks and tests
- `devstral:latest` — present on the machine but **disabled by default here**: at
  14 GB it does not fit in 16 GB RAM and timed out in every test

**If you clone this, model choice is yours.** Set models in `.ollama-skills.json`
(copy `config/.ollama-skills.example.json`) or env vars — any Ollama model works.
With no config at all, the script auto-detects sensible models per task from what
you have installed (`python scripts/ollama_ask.py models` shows the result and why).

## Measured speed (development machine: CPU-only, 16 GB RAM, no GPU)

Real numbers from `tests/e2e_local.py` and the design-phase measurements — so you
can set expectations before you wait:

| Operation | llama3.2:1b | qwen3:8b |
|---|---|---|
| Model load (cold start) | ~6 s | ~27–34 s |
| `ask` (tiny prompt, warm) | 3.0 s | ~9 s |
| `commit-msg` (small staged change) | 5.4 s | ~30 s |
| `draft-command` | 7.2 s | ~30–60 s |
| Large prompt (~2,700 tokens) | not advised | **7–10+ minutes** (CPU prefill ~7 tok/s) |
| `devstral:latest` (14 GB) | — | timed out (larger than free RAM) |

That last row is why the input budget defaults to 2,500 chars and why `commit-msg`
sends a compact diff summary instead of full hunks. GPU owners can raise budgets in
config ([docs/ADVANCED.md](docs/ADVANCED.md) §6 has per-hardware advice).

## Configuration

Resolution order for the model of each task:
`--model` flag → `OLLAMA_SKILLS_MODEL_<TASK>` env (`COMMIT|SHELL|CODE|GENERAL`) →
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
| `tasks.<task>.model` | auto | model per task (`commit`, `shell`, `code`, `general`) |
| `tasks.<task>.max_tokens` | per task | output cap |
| `tasks.<task>.temperature` | per task | 0.0 for commands, 0.4 for commit messages |

Exit codes: `0` ok · `2` bad usage / over budget · `3` Ollama unreachable ·
`4` model missing · `5` stall/timeout · `6` output failed validation.
Skills use these to fall back: **if the local model fails, Claude does the task
itself and says so** — a failed delegation never blocks work.

## Safety model (short version)

- Local model output is always an **untrusted draft**; Claude reviews before acting.
- Drafted shell commands pass a static deny-list and a scope check, then still go
  through Claude Code's normal permission prompt. Nothing here bypasses permissions.
- Lint fixes are suggest-only and must touch just the flagged lines.
- These rules are behavior-tested against small models: [docs/skill-tests.md](docs/skill-tests.md).
- Full threat model: [docs/SECURITY.md](docs/SECURITY.md).

## Repo map

```
.claude-plugin/    plugin + marketplace manifests
skills/            five SKILL.md folders (ask, commit, precommit, shell, code)
agents/            three subagents (coder, git, ops) — model: haiku
scripts/           ollama_ask.py (the one runtime file) + validate_repo.py
config/            example config
templates/         CLAUDE.md routing snippet
tests/             unit tests (fake Ollama server) + opt-in real e2e
docs/              DESIGN, PLAN (for simpler-model agents), RESEARCH, ADVANCED,
                   SECURITY, skill-tests
.github/workflows  CI: unit tests (Ubuntu+Windows), validation, opt-in e2e
```

## Development

```bash
python -m unittest discover -s tests -v   # unit tests (no Ollama needed)
python scripts/validate_repo.py           # manifest + frontmatter checks
RUN_OLLAMA_E2E=1 python tests/e2e_local.py  # real e2e (needs local Ollama)
```

The step-by-step build/extension plan — written so agents on simpler models
(Opus/Sonnet/Haiku) can execute it — is in [docs/PLAN.md](docs/PLAN.md).

License: [MIT](LICENSE). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
