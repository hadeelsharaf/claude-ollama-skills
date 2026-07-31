# Changelog

All notable changes to this project are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Changed
- Merged `ollama-logs` + `ollama-git-history` into `ollama-digest` — same
  workflows and safety rules, one catalog entry instead of two.
- Trimmed every skill and agent description; the always-on catalog drops from
  4,553 to 2,583 chars (~1,140 → ~645 tokens per session).
- `validate_repo.py` now enforces per-description caps and a total catalog
  budget (2,700 chars) so the overhead cannot silently regrow.

### Removed
- `ollama-k8s` (skill, kind e2e harness, `RUN_K8S_E2E`) — parked until
  local-delegation cost savings are proven; last shipped in 0.4.0
  (tag `ollama-skills--v0.4.0`). The kubectl safety deny-list entries in
  `ollama-shell` and the ops agent remain.

### Added
- `benchmarks/measure_catalog.py` — stdlib report of what the plugin adds to
  every session; `--budget` gate used in validation.
- README: 0.5.0 changes table and a "Scoping the install" section (enable per
  project; disable for headless/CI).
- Re-measured neutral A/B after the catalog cut, published as
  `benchmarks/results/ab-published-0.5.0.json`: first positive deltas
  (+8.2% commit, +9.9% summarize; successful runs only, n=3, read as sign
  not magnitude — summarize saved without delegating).

## [0.4.0] - 2026-07-31

### Added

- Usage ledger: every local model call appends a counts-only line (real Ollama
  token counts, estimated chars avoided, delivered flag) to a per-repo
  `.ollama-skills-usage.jsonl`; opt out with `OLLAMA_SKILLS_NO_USAGE=1` or
  `"usage_log": false`.
- `stats` subcommand: per-command table of local tokens used and estimated
  cloud tokens avoided, with `--json`, `--since DAYS`, and `--reset`.
- Commit drafts get deterministic context: the staged file mix is classified
  (docs / tests / CI / config) into the prompt with a suggested type, excerpts
  are demoted to reference-only, and wrong-type or filename-scoped drafts are
  rejected with corrective feedback before Claude reviews them.
- `commit-msg --type <t>` and `--hint "<one line>"`: the caller passes the type
  and intent it already knows; the semantic gate enforces the stated type.
  Excerpts now lead with the highest-churn file, length rejections state the
  measured character count, and hinted drafts are marked `"hinted": true` in
  the usage ledger.
- `ollama-logs` skill: plain log/text-file digests via `summarize --file` —
  the A/B benchmark exposed the gap (the README claimed log digests but only
  docker/k8s/git wrappers existed).
- A/B benchmark suite: `benchmarks/measure_ab.py` (three arms — without /
  with / directed — with honest, measured results published in the README)
  plus `evals/` quality cases for `claude plugin eval --ablation
  with-without`.

### Changed

- `commit-msg` now exits 6 when a draft still contradicts the stated or
  suggested type after one corrective retry, instead of printing it;
  scope-only defects are retried once, then the draft is printed for Claude
  to edit.
- `ollama-commit` and the `ollama-git` agent now commit in the same turn the
  message is approved — the permission prompt on the git command is the
  user's approval; they no longer stop to ask "shall I commit?" first.

## [0.3.0] - 2026-07-29

### Added

- Free-RAM gate in model auto-detect: candidates larger than free RAM are skipped;
  `models` reports each skip (`skipped <model> for <tasks> (<size> > <free> free RAM)`)
  and `--json` gains a `skipped` array. Explicit `--model` / env / config picks are
  never gated. When every matching candidate is gated, the task fails with exit 4
  naming the model, its size, and free RAM.
- `ollama-pr` skill + `pr-desc`/`pr-create` subcommands: the local model drafts a PR
  title/description from commit subjects (never patches), Claude reviews, and one
  gated step opens a **draft** PR/MR via gh or glab (picked from the remote URL).
  `--ready` is the only escalation; force/web/edit flags cannot be smuggled in.

### Changed

- Preference lists: `gemma2` joins every task list directly after `gemma3`; the gemma
  family joins `shell`; `qwen2.5-coder` becomes the last-resort floor for `general`.
- Example config, README fleet + measured-speed tables, e2e default model, and the
  two pull hints now match the 2026-07 development fleet (`qwen2.5-coder:1.5b`,
  `gemma2:2b`, `devstral-small-2:latest`).
- `ollama-git-history` now always passes `--no-verdict` to `summarize`: on commit-log
  input the VERDICT line invites invented error/warning counts (observed live); plain
  fact bullets have nothing to invent.

## [0.2.0] - 2026-07-18

### Added

- `summarize` subcommand in `scripts/ollama_ask.py`: map-reduce digest of log / Kubernetes
  events / `kubectl describe` / git text on the local model, stdin-in / digest-out. Adds a
  dedicated `summarize` task profile and `num_ctx` support in `generate()`.
- Three skills: `ollama-docker`, `ollama-k8s`, `ollama-git-history`.
- kubectl and docker output fixtures under `tests/fixtures/`, plus fixture-driven unit tests.
- RED→GREEN skill probes for the three new skills in `docs/skill-tests.md`.
- Opt-in real k8s e2e (`tests/e2e_k8s.py`, gated by `RUN_K8S_E2E=1`) and a `scripts/kind-up.sh`
  helper that captures the kubectl fixtures from a throwaway kind cluster.
- Example config gains a `tasks.summarize` entry.

### Changed

- Base deny-list in the `ollama-shell` skill and the `ollama-ops` agent now refuses
  destructive Docker, Kubernetes, and git-history command families.
- `tests/e2e_local.py` gains a `summarize` step.

## [0.1.0] - 2026-07-18

### Added

- Core CLI `scripts/ollama_ask.py` (Python 3.9+, standard library only):
  `health`, `models`, `warmup`, `ask`, `commit-msg`, `draft-command`, `draft-code`, `fix-lint`.
- Five skills: `ollama-ask`, `ollama-commit`, `ollama-precommit`, `ollama-shell`, `ollama-code`.
- Three subagents on haiku: `ollama-coder`, `ollama-git`, `ollama-ops`.
- Plugin + marketplace manifests (installable with two commands).
- CLAUDE.md routing template.
- Docs: design, plan, research, advanced options, security notes.
- Unit tests with a fake Ollama server; opt-in real e2e script.
- GitHub Actions: unit tests (Ubuntu + Windows), repo validation, opt-in e2e.
