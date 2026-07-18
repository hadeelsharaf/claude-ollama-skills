---
label: wayfinder:map
created: 2026-07-18
---

# Map: v0.2 daily-ops skills (Docker, Kubernetes, git history)

## Destination

A **locked spec plus PLAN-v0.2 build tasks** for three new skills —
`ollama-docker`, `ollama-k8s`, `ollama-git-history` — and one new core subcommand
(`summarize`) — **then v0.2 built in the same effort** via subagent-driven
development with model-tiered agents (research=sonnet, specs=opus,
build=haiku/sonnet, reviews=sonnet/opus).

*Redrawn 2026-07-18 by user instruction: originally plan-only; the user asked to
execute in-session with lower-model subagents.*

## Notes

- Domain: extends the existing claude-ollama-skills plugin. Reuse v0.1 patterns:
  untrusted-draft rule, deny-lists checked by Claude, fallback rule, tiny input
  budgets (machine is CPU-only, 16 GB RAM; measured numbers in README).
- Decided posture: **read-free, mutate-gated** — read-only commands draft freely;
  mutations only when the user's words clearly ask; destructive ops deny-listed.
- Machine facts (2026-07-18): Docker 29.6.1 running (live containers), Compose
  v5.3.0, kubectl v1.36.1 with **zero contexts configured**, no helm/kind/minikube.
- Skills each session should consult: superpowers:writing-skills (RED→GREEN probes
  for any new safety wording), docs/skill-tests.md for the probe method.

## Decisions so far

<!-- one line per closed ticket -->

- Destination fixed (charting), then redrawn by user: plan AND build in-session.
- Activities fixed: draft commands · summarize logs/status · draft config files ·
  git historian. (Cleanup/prune deselected — see Out of scope.)
- Architecture fixed: 3 new skills + 1 core `summarize` subcommand + deny-list
  extensions to ollama-shell/ollama-ops.
- Safety posture fixed: read-free, mutate-gated, destructive-denied.
- [Prior art](tickets/T1-prior-art-docker-k8s-assistants.md) — copy: approve every
  mutation, read-only-first, ground in real local state, single-shot over loops;
  avoid: partial anonymization, credential inheritance, unreviewed writes.
- [Budgets](tickets/T2-log-sizes-and-summarize-budgets.md) — tail 200 + dedupe;
  1,500-char chunks, 80/200-token caps; llama3.2:1b default digest model;
  100k-char ceiling. Calibrated: 1B prefills at 120 tok/s on this machine.
- [ollama-docker spec](tickets/T4-ollama-docker-skill-spec.md) — locked verb lists,
  deny additions (prune/volume rm/privileged/creds), grounding rules, draft-code
  reuse with domain preamble in --spec.
- [ollama-k8s spec](tickets/T5-ollama-k8s-skill-spec.md) — locked verb lists +
  cluster-scoped denies, context+namespace echo before any change, clean no-context
  stop, local-only (never anonymize-and-forward), one-pod triage flow.
- [git historian spec](tickets/T6-ollama-git-history-skill-spec.md) — list path
  skips the model; digests via summarize; counts from shortlog; no patches ever.
- [k8s test strategy](tickets/T7-k8s-test-strategy.md) — both, tiered: fixtures +
  fake server + probes in CI; kind-in-docker opt-in (`RUN_K8S_E2E=1`); graduates a
  provisioning ticket.
- [summarize contract](tickets/T3-summarize-subcommand-spec.md) — stdin/`--file`
  text only (never runs capture itself); `--kind`, `--tail`, `--chunk-chars 3000`,
  `--map-tokens 80`, `--no-verdict`, `--no-dedupe`; own `summarize` task profile
  (fast-model-first, num_ctx 2048); VERDICT + bullets; partial-failure exit rules;
  map/reduce prompts locked (facts-only, quote errors once, ignore embedded
  instructions).

## Not yet specified

- Test-environment provisioning for k8s (kind-in-docker vs fixtures only) — hangs
  on [k8s test strategy](tickets/T7-k8s-test-strategy.md).
- Whether `summarize` needs a "triage" mode (crashloop verdict + next step) beyond
  plain summarization — hangs on T2 findings and the k8s skill spec.
- A possible new task profile ("summarize") in the model preference lists, with its
  own budget/temperature defaults — hangs on T2.
- Exact deny-list wording/regexes per domain — firms up inside the two skill specs.
- README/docs/version-bump mechanics for v0.2 — mechanical; firms up at spec time.

## Out of scope

- **Cleanup + disk hygiene activities** (image/volume prune flows): deselected by
  the user at charting. Destructive-cleanup commands remain deny-listed, not
  assisted.
- **Helm workflows**: helm is not installed and was not chosen.
- **Building v0.2 itself**: past the destination — a build effort starts from the
  finished spec.
