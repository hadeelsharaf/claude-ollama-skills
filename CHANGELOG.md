# Changelog

All notable changes to this project are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Changed
- Homepage: a "New in v0.8.0" section — on-demand guardrail loading (with the
  measured shell common-path drop), `--outcome` folding, and the stats/models
  feedback lines. Copy only; numbers trace to the 0.8.0 accounting.

## [0.8.0] - 2026-08-07

### Added
- A project homepage at <https://hadeelsharaf.github.io/claude-ollama-skills/>,
  built from `site/` — one hand-written `index.html` plus `style.css`, with no
  build step and no dependencies, matching the rest of the repo. Deployed by
  `.github/workflows/pages.yml`, which uploads the directory as-is and fails
  the run if `package.json`/`Gemfile`/`_config.yml` ever appear under `site/`.
  It triggers on push to `main`, not the default `draft` branch, so the public
  page describes the version installed users actually have; that also means
  homepage copy ships at release time, and the page's hard-coded version
  string is now part of a release bump.
- README hero block with an animated terminal (`assets/hero.svg`). Two rules
  keep the card from ever rendering blank: every animated element carries its
  final state as a plain attribute, so a SMIL-stripping renderer shows the
  full transcript, and the animation itself starts on that completed frame —
  it holds, clears, retypes, and lands back on it, making keyTime 0 and 1
  identical. Caught by rendering it: the first version screenshotted empty.
- The homepage leads with the privacy property rather than token savings, and
  its "Honest limits" section repeats — with a link to the A/B data — that
  five measured rounds show no reliable cloud-token saving for unattended
  neutral-prompt sessions. The one figure it does headline (176x less text
  into cloud context) is labelled as a single recorded ledger call, not an
  average.
- Progressive disclosure: the shell/ops deny list, the docker deny-list
  additions, and the digest git-history path now live in per-skill reference
  files (`DENYLIST.md`, `GIT-HISTORY.md`) read only when their branch fires;
  read-only commands and file/log digests no longer load them at all.
  `validate_repo.py` now fails on a pointer to a missing reference file.
- Outcome folding: every delegating subcommand accepts
  `--outcome <used-as-is|edited|replaced|model-failed>` (plus
  `--outcome-task <task>`) to record the previous draft's fate on the next
  call with no extra round trip; `record-outcome` stays as the session-final
  fallback. Ledger rows are identical in shape and remain counts-only.
- `stats` prints counts-only `suggestion:` lines when a task's recent drafts
  keep failing; `models` prints `hint:` lines when a higher-preference model
  is not installed. `stats --json` gains a machine-readable `suggestions`
  key and `models --json` gains a `hints` key. `docs/ADVANCED.md` gains a
  model-tier routing section.
- `benchmarks/measure_catalog.py` reports per-skill common-path load (body
  only) vs full-path load (body plus reference files).
- Re-measured neutral A/B, fifth consecutive round, published as
  `benchmarks/results/ab-published-0.8.0.json`: commit -10.9%, summarize
  +0.9% (successful runs only, n=3, read as sign not magnitude — both
  deltas sit inside within-arm noise).

## [0.7.0] - 2026-08-01

One combined release: 0.6.0 was prepared but never shipped (its release gate
failed on the cost re-measure); its entries ship here together with the
trust-tier wave that answered them.

### Removed
- `summarize --kind events|describe` and the kubectl describe pre-filter —
  remnants of the kubernetes support parked in 0.5.0. kubectl output still
  digests through the generic `log`/`text` kinds. Orphaned kubectl test
  fixtures removed with them.

### Fixed
- The remote-host privacy warning can no longer be silenced by a hostname
  prefix (`localhost.attacker.example`, `127.0.0.1.evil.example`): loopback is
  now decided by exact hostname or a genuine loopback/unspecified IP literal,
  and bracketed IPv6 (`http://[::1]`) no longer false-warns.
- `summarize` rejects a negative `--tail` as a usage error instead of silently
  dropping the first N lines, and the reduce loop stops with a best-effort
  summary when a pass no longer shrinks the text (it could previously loop
  forever with `--chunk-chars` below the model's output size).
- `pr-desc`/`pr-create` resolve the PR base from the remote the PR actually
  targets (`--remote`, else the branch upstream) instead of a hardcoded
  `origin`.
- `validate_repo.py` reads manifests BOM-tolerantly (`utf-8-sig`) and reports
  unreadable files as clean FAILs; it also now pins the README exit-code list
  against the script's constants and docstring, and the README gained the
  missing `1`/`130` rows.
- The base skill documents the `summarize` task profile.

### Changed
- Internal deepening, no change to exit codes or stdout (two commands' "not a
  git repository" error text is now unified, and drafting failure paths now
  print a uniform raw-output dump, truncated to 300 chars, to stderr): git
  preflight checks and the one-corrective-retry drafting policy now each live
  in one place inside `ollama_ask.py` (the duplicated copies had already
  drifted in wording); the test fake server routes canned responses through a
  declared marker table with a collision guard; `measure_catalog.py` shares
  `validate_repo.py`'s frontmatter parser instead of carrying its own.
- `ask --json-object` now uses the shared one-corrective-retry policy — the
  last hand-rolled copy; the helper genuinely owns all six drafting paths.
- Skill-craft pass: ollama-ask's description now routes setup/stats checks;
  the CLAUDE.md routing snippet reuses each skill's leading words and gains
  the missing ollama-docker bullet; every skill names its loop
  (ground -> draft -> judge); fallback and flag rules are word-identical
  across all skills and agents; ollama-docker's Dockerfile/compose drafting
  reference moved to DRAFTING.md, loaded only on that branch.
- Digest quality, measured then fixed twice: the final digest budget rises
  from 200 to 400 tokens (the reduce step was the bottleneck), the probe cap
  settles at three, map and reduce prompts prioritize rare single-occurrence
  events ("an event that appears only once outranks repeated traffic"), and
  a digest that passes its checks is the deliverable — the transcript audit
  and the first-ever 3/3 digest validation round both ship in the README.

### Added
- `tests/test_validate_repo.py` — pins the description-cap and catalog-budget
  failure paths, including that validator output stays ASCII.
- Trust tiers: every drafting path now has an explicit gate. `draft-command`
  gains a script-side classifier (deny-list refusal on exit 6, read-only
  drafts marked `classification: read-only` on stderr); `summarize` prints a
  counts-only `coverage:` line and writes fragment-style chunk notes with a
  120-token map budget (was 80, which truncated every note); `pr-desc`
  refuses oversized changesets (exit 2); plain `ask` and plain commit style
  gain a minimal length/non-empty judge; new `record-outcome` subcommand
  records draft fates in the usage ledger (counts only).
- Skills and agents encode the tiers as canonical pinned sentences:
  conventional hinted commit drafts are used verbatim on exit 0, digests are
  judged against the coverage line plus at most three probes, code drafts are
  test-gated, and read-only classified commands run without review.

## [0.5.0] - 2026-07-31

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
