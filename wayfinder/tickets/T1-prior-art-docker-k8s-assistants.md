---
id: T1
title: "Prior art: local-LLM assistants for Docker and Kubernetes"
type: research
status: closed
assignee: "research-agent-T1"
blocked-by: []
---

## Question

What do existing AI/local-LLM assistants for Docker and Kubernetes actually do,
and what should we copy or avoid? Survey at least: kubectl-ai (Google),
k8sgpt, Docker's "Ask Gordon" AI agent, aiac, kube-copilot, and any Ollama-based
docker/k8s helpers. For each: which daily activities it covers (command drafting,
log/event triage, manifest generation), what safety gates it uses around mutating
commands, prompt patterns for small models, and known failure modes. End with:
a short copy/avoid list feeding the ollama-docker (T4) and ollama-k8s (T5) specs.

## Resolution

Surveyed kubectl-ai, k8sgpt, Docker Ask Gordon, aiac, kube-copilot, plus adjacent
prior art (kagent, HolmesGPT, DockerGen AI, and general small-model tool-calling
research). Full findings, per-tool breakdown, comparison table, and sources in
[research/T1-prior-art.md](../research/T1-prior-art.md).

- **Copy — approval-before-mutate, always**: Docker Gordon shows every command/
  file-mod/Docker-op before running it (session-scoped, no lingering trust);
  kagent's k8s-agent system prompt bakes in an explicit "read-only tools before
  modification tools" rule. Both map directly onto this project's own
  read-free, mutate-gated posture.
- **Copy — ground drafts in real local state before generating**: Gordon reads
  running containers/compose files/images before answering, which cuts down
  hallucinated flags/names — the same failure class that turns into a
  namespace-typo disaster in kubectl.
- **Copy — prefer single-shot generation over long agent loops on small
  models**: aiac (single-shot) vs. kube-copilot/kagent (agent loops); research
  shows even 95%-reliable-per-call small models compound to ~66% success over
  an 8-step loop, and kubectl-ai needs a "tool-use shim" just to get small
  models emitting parseable tool calls at all.
- **Copy — one cheap prompt line prevents the worst loop failure**: adding
  "never repeat the same failing tool call more than once" fixed a documented
  destructive-retry-loop failure (30k tokens burned repeating one failing
  command) in third-party small-model testing.
- **Avoid — partial safety filters**: k8sgpt's `--anonymize` only masks 9 of 14
  analyzers and leaves Events/Logs/Pods unmasked, an acknowledged gap left open
  for a long time — a filter that isn't complete gives false confidence.
- **Avoid — credential inheritance as the safety boundary**: kube-copilot and
  the general guardrail literature agree that letting an assistant run under
  the engineer's own kubeconfig/cluster-admin (instead of a scoped identity) is
  the single most common and most dangerous shortcut.
- **Avoid — generate-then-write with no review step**: aiac's non-interactive
  (`-q`/`--output-file`) mode writes straight to disk with zero gate; every
  mutating draft in T4/T5 should have a review step before touching disk or a
  cluster.
- **Avoid — inconsistent gating across one tool's own command surface**:
  kube-copilot gates `generate`→apply but not its own `execute` mode, despite
  `execute` being the more autonomous, action-taking path.

Findings file: [wayfinder/research/T1-prior-art.md](../research/T1-prior-art.md)
(19 sources).
