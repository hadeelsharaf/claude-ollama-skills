---
id: T7
title: "k8s test strategy on a machine with no cluster"
type: grilling
status: closed
assignee: "spec-agent-opus"
blocked-by: [T5]
---

## Question

kubectl has zero contexts here. Decide how v0.2's k8s parts get tested: (a) kind
cluster inside the running Docker daemon (real e2e; needs a kind install task),
(b) canned kubectl output fixtures only (fast, no cluster, weaker), (c) both —
fixtures in CI, kind locally. Weigh RAM headroom (~6 GB free) against a kind
control plane (~500 MB–1 GB). The choice graduates the "test-environment
provisioning" fog into a task ticket or removes it.

## Resolution

Author: spec-agent-opus.

### Decision: (c) both — but tiered to the project's existing pattern

Fixtures + fake-server unit tests + RED→GREEN skill probes are the **default/CI tier**
(fast, deterministic, no cluster). kind-in-docker is an **opt-in local-only tier** that
does two jobs: real e2e, and the one-time source that CAPTURES the fixtures so they are
not hand-faked. CI never needs a cluster. This **graduates** the provisioning fog into a
task ticket (create **T9 — kind install + fixture capture**); it does not remove it.

### Rationale (5 lines)

1. The script never calls kubectl itself — kubectl output is INPUT to `summarize`; fixtures
   capture that input perfectly and deterministically, which is just the existing fake-Ollama-server pattern extended to kubectl.
2. The single most important k8s guardrail — the clean no-context stop (T5) — is the dev
   machine's DEFAULT state (zero contexts), so it needs NO cluster to test; probe it live, now.
3. Pure fixtures (option b) risk drifting from real kubectl v1.36 output and can never
   exercise the with-context echo path — so capture them ONCE from a real kind cluster to keep them honest (avoids the k8sgpt "false-sense-of-security" trap, T1 avoid #3).
4. A mandatory live cluster (option a) breaks CI and blows the RAM ceiling: ~6 GB free vs a
   kind control plane (~0.5–1 GB) PLUS a model — with `qwen3:8b` (~6 GB) that thrashes (DESIGN "never two models at once"), so kind e2e must be opt-in, `llama3.2:1b`-only, and run alone.
5. (c) puts fixture determinism where it is cheap (CI) and real-shape fidelity where it is
   cheap (one-time local capture), mirroring DESIGN §8's existing "unit tests everywhere + opt-in real e2e."

### Test artifacts the plan MUST include

1. **`tests/fixtures/kubectl/`** — canned outputs captured from real kubectl v1.36:
   `get-pods.txt`, `get-pods.json` (`-o json`), `describe-pod-crashloop.txt`, `events.txt`,
   `logs-crashloop.txt` (+ a `--previous` variant), and `no-context.txt` (empty /
   `error: current-context is not set`). These stand in for kubectl the way the fake server
   stands in for Ollama. Add a parallel `tests/fixtures/docker/` (`ps.txt`,
   `logs-crashloop.txt`, `compose-config.yaml`) for the docker skill's CI tests.
2. **Unit tests in `tests/test_ollama_ask.py`** (extend, same fake-server harness): pipe each
   fixture into `summarize` via stdin → assert output shape + budget-degradation on the big
   log; `draft-code --lang yaml` / `--lang dockerfile` emits fence-free artifact; exit codes.
   (Keep summarize assertions loose until T3 locks its output shape — depends on T3.)
3. **RED→GREEN skill probes** per `docs/skill-tests.md` (fresh haiku subagent, baseline vs
   full SKILL.md, 3+ reps): for BOTH ollama-docker and ollama-k8s — each deny-list item
   refused; each read verb allowed; mutate-gate requires explicit user words; and k8s-only:
   context echoed before any gated command, and the clean no-context stop (probe against the
   machine's real zero-context state). Record them alongside the existing scenarios.
4. **Opt-in real e2e: `tests/e2e_k8s.py`** gated by `RUN_K8S_E2E=1` (mirrors
   `RUN_OLLAMA_E2E`), requires a kind cluster + `llama3.2:1b`, runs alone (never with a
   second model loaded).
5. **A fixture-capture task (T9): `scripts/kind-up`** (or documented steps) that installs
   kind, creates a throwaway cluster in the running Docker daemon, deploys a deliberately
   crashlooping pod, captures the fixtures in (1) from real output, and tears down. This is
   the graduated "test-environment provisioning" ticket; it resolves the map's "Not yet
   specified: Test-environment provisioning for k8s" fog.
6. **CI (GitHub Actions):** fixtures + unit tests + frontmatter/manifest validation on
   ubuntu + windows with NO cluster; the kind e2e stays a manual/opt-in job only (mirrors
   DESIGN §8's existing optional manual e2e job). Docker e2e needs no provisioning task — the
   daemon already runs on the dev machine — so no docker equivalent of T9 is required.
