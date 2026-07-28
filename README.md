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

## What's new in v0.2

- **`summarize`** — a new subcommand that digests logs, Kubernetes events, `kubectl describe`
  output, or a git range into a short verdict + fact bullets, entirely on the local model.
  Big raw text is piped in over stdin and never enters Claude's context; only the digest
  returns. Small input is one call; large input is chunked map-reduce with visible progress
  and per-chunk drop markers.
- **Three new skills:** `ollama-docker` (read state, summarize container logs, draft docker /
  Dockerfile / Compose), `ollama-k8s` (read state, triage failing pods, draft kubectl /
  manifests, with a context+namespace echo and a clean no-context stop), and
  `ollama-git-history` (read-only history; a local summary only when asked). Each drafts
  read-only commands freely, makes changes only when your words clearly ask, refuses
  destructive / cluster-scoped commands, and treats every draft as an untrusted draft Claude checks.

## Requirements

- [Ollama](https://ollama.com) running locally (tested with 0.32) and at least one model
- Python 3.9+ (standard library only — nothing to pip install)
- git, Claude Code 2.x

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
| "explain why this container keeps crashing" | `ollama-docker` skill (logs → local summarize, checked) |
| "why is this pod crashlooping?" | `ollama-k8s` skill (describe+events+logs → local summarize; context echoed) |
| "what changed on this branch this week?" | `ollama-git-history` skill (compact log → local summarize) |

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

## Models used during development

These are the models that were installed on the development machine and used while
building and testing this project:

- `qwen2.5-coder:1.5b` — coder pick: commit messages, shell drafts, small code
- `gemma2:2b` — general + summarize pick (the one small model that satisfies
  every task's preference list by itself)
- `devstral-small-2:latest` — 15 GB; auto-detect **skips it on this machine**
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

That last row is why the input budget defaults to 2,500 chars and why `commit-msg`
sends a compact diff summary instead of full hunks. GPU owners can raise budgets in
config ([docs/ADVANCED.md](docs/ADVANCED.md) §6 has per-hardware advice).

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
`4` model missing · `5` stall/timeout · `6` output failed validation ·
`7` protected branch refused · `8` git command failed.
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
skills/            eight SKILL.md folders (ask, commit, precommit, shell, code, docker, k8s, git-history)
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

Both commands above are what CI runs. The design and the measurements behind the
default budgets are in [docs/DESIGN.md](docs/DESIGN.md); how to add a skill is in
[CONTRIBUTING.md](CONTRIBUTING.md).

License: [MIT](LICENSE). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
