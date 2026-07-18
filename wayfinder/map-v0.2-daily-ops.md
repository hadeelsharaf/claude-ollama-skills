---
label: wayfinder:map
created: 2026-07-18
---

# Map: v0.2 daily-ops skills (Docker, Kubernetes, git history)

## Destination

A **locked spec plus PLAN.md-style build tasks** for three new skills —
`ollama-docker`, `ollama-k8s`, `ollama-git-history` — and one new core subcommand
(`summarize`), such that any later session (including Haiku/Sonnet agents) can build
v0.2 without making a single new decision. This map plans; it does not build.

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

- Destination fixed (this charting session): locked spec + plan, not built skills.
- Activities fixed: draft commands · summarize logs/status · draft config files ·
  git historian. (Cleanup/prune deselected — see Out of scope.)
- Architecture fixed: 3 new skills + 1 core `summarize` subcommand + deny-list
  extensions to ollama-shell/ollama-ops.
- Safety posture fixed: read-free, mutate-gated, destructive-denied.

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
