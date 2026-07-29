# Changelog

All notable changes to this project are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [Unreleased]

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
