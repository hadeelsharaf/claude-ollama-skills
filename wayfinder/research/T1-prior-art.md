---
label: wayfinder:research
ticket: T1
created: 2026-07-18
---

# T1 — Prior art: local-LLM assistants for Docker and Kubernetes

## Scope and method

Surveyed the five named tools (kubectl-ai, k8sgpt, Docker "Ask Gordon", aiac,
kube-copilot) plus adjacent prior art that surfaced repeatedly during research
(kagent, HolmesGPT, DockerGen AI, and general findings on small-model tool-calling
reliability and Kubernetes-agent guardrails). For each named tool: daily
activities covered, safety gates around mutating actions, prompt patterns
(especially for small/local models), and known failure modes. Research done via
web search and README/docs fetches; no tools were installed or run locally.
16 sources cited at the end.

This research feeds the **ollama-docker** (T4) and **ollama-k8s** (T5) specs for
claude-ollama-skills, whose posture is already decided at the map level:
**read-free, mutate-gated** (read-only commands draft freely; mutations only on
clear user request; destructive ops deny-listed), running tiny local models on a
CPU-only, 16 GB RAM box.

---

## 1. kubectl-ai (Google Cloud Platform)

**What it is**: A kubectl plugin / standalone CLI that turns natural language into
kubectl actions. Not an officially supported Google product.

**Daily activities covered**:
- **Command drafting**: "check logs for nginx app in hello namespace" → drafts and
  runs the matching kubectl command.
- **Log/event triage**: multi-turn "how's nginx app doing in my cluster?" style
  status/health assessment across pods, logs, events.
- **Manifest generation**: creates resource definitions from intent (lightly
  documented, less of a focus than the other two activities).
- Runs as an interactive shell holding conversational context across turns —
  closer to "an expert with hands on your terminal" than a one-shot query tool.

**Safety gates around mutating commands**:
- Approval-by-default: requests user confirmation before any cluster-modifying
  action; a `skipPermissions` config flag (default `false`) is the escape hatch
  for users who want to skip confirmation.
- Roadmap (issue #265) explicitly lists unfinished safety work as P2: "isolated
  exec (pods, containers, drop permissions...)" and command-restriction
  mechanisms — i.e. **today's confirmation prompt is the only gate; sandboxing
  and command allowlisting are still aspirational**, not shipped.

**Prompt patterns for small models**:
- `--enable-tool-use-shim` (config: `enableToolUseShim`) exists specifically
  because "models require special prompting to enable tool calling." It rewrites
  the prompt so smaller/local models emit tool calls in a format the harness can
  parse, rather than relying on native function-calling.
- Confirmed used with small local models via Ollama, e.g. `gemma3:4b` with
  `enableToolUseShim: true`, and `gemma3:12b-it-qat` as a documented example
  model. Also documented against Qwen (`qwen-plus`) via OpenAI-compatible
  endpoints.
- Supports `promptTemplateFilePath` / `extraPromptPaths` for customizing the
  system prompt per deployment — confirms prompt tuning is expected/necessary
  per-model, not a one-size-fits-all prompt.

**Known failure modes**:
- The tool-use-shim requirement itself is evidence that small/local models
  don't reliably emit correctly-shaped tool calls without extra scaffolding.
- No enumerated failure catalog in the README; MCP/HTTP auth "still evolving."
- General community concern (not kubectl-ai-specific, but directly relevant):
  namespace typos in destructive kubectl commands are a well-known catastrophic
  failure class in the wider kubectl ecosystem — exactly the class an LLM
  drafting commands can reproduce or worsen if it hallucinates a namespace/name.

Sources: [GoogleCloudPlatform/kubectl-ai](https://github.com/GoogleCloudPlatform/kubectl-ai) · [kubectl-ai Roadmap issue #265](https://github.com/GoogleCloudPlatform/kubectl-ai/issues/265) · [Running Ollama + kubectl-ai Locally](https://medium.com/h7w/running-ollama-kubectl-ai-locally-9c61be90c01d) · [K8sGPT vs kubectl-ai comparison](https://www.linkedin.com/pulse/k8sgpt-vs-kubectl-ai-which-tool-should-you-use-swapnil-kulkarni-jxegf)

---

## 2. k8sgpt (CNCF Sandbox project)

**What it is**: A read-only cluster scanner with built-in "SRE-experience"
analyzers, optionally enriched by an LLM explanation pass.

**Daily activities covered**:
- **Log/event triage** is effectively its whole product: analyzers for Pods,
  Services, Deployments, StatefulSets, Jobs, Ingresses, Nodes, CronJobs, PDBs,
  HPAs, NetworkPolicies, webhooks. `k8sgpt analyze` scans, `--explain` sends
  findings to the configured AI backend for a plain-English explanation +
  suggested fix.
- **No command drafting, no manifest generation** — this is diagnosis-only, by
  design. (A comparison piece frames the split cleanly: "k8sgpt tells you what's
  wrong, kubectl-ai does things for you" — diagnosis vs. prescription.)

**Safety gates around mutating commands**:
- Not applicable in the usual sense — k8sgpt **never mutates the cluster**. Its
  "safety gate" is architectural: read-only by construction, not an approval
  prompt around a write path.
- Its actual safety concern is data exfiltration to the LLM backend, not cluster
  mutation: it ships an `--anonymize` flag that masks sensitive fields before
  sending to a cloud AI backend, and documents recommending **a local model in
  critical production environments** specifically to avoid sending cluster data
  off-box.

**Prompt patterns for small models**: minimal documentation. Supports Ollama and
LocalAI as backends via `k8sgpt auth add` / `k8sgpt auth default -p ollama`, but
no small-model-specific prompt tuning is documented (unlike kubectl-ai's shim).

**Known failure modes**:
- Anonymization is **incomplete and inconsistent**: only 9 of 14 analyzers mask
  data; Pod, ReplicaSet, PVC, Logs, and Events analyzers do not, and raw Event
  messages can leak identifying strings (e.g. project/pod names) even with
  `--anonymize` on — acknowledged by the maintainers as a gap "scheduled in the
  near future," not yet fixed.
- API keys/credentials for the configured backend are stored in **plaintext** in
  `k8sgpt.yaml`.
- Only one remote cache backend configurable at a time (an operational
  limitation, not a safety one, but worth knowing).

Sources: [k8sgpt-ai/k8sgpt](https://github.com/k8sgpt-ai/k8sgpt) · [k8sgpt.ai](https://k8sgpt.ai/) · [K8sGPT vs kubectl-ai](https://www.linkedin.com/pulse/k8sgpt-vs-kubectl-ai-which-tool-should-you-use-swapnil-kulkarni-jxegf)

---

## 3. Docker "Ask Gordon"

**What it is**: Docker's first-party AI agent, bundled with Docker Desktop
(4.74+) and available via `docker ai` CLI. Backend runs on Docker's servers
(not local/Ollama) — proprietary, closed model.

**Daily activities covered** (broadest of all surveyed tools):
- **Command drafting**: "clean up unused images," "stop everything running,"
  "pull and run nginx" — plain-English → Docker CLI actions.
- **Log/event triage**: "my container keeps exiting" → reads logs, traces root
  cause (missing env var, bad base image, bad mount), grounded in the actual
  running environment rather than generic docs.
- **Manifest generation**: "containerize this app and set up a dev environment
  with Postgres" → drafts a Dockerfile, builds a docker-compose file, runs the
  stack. Also does **Dockerfile optimization**: multi-stage build conversion,
  layer reordering for cache hits, slimmer base image swap, added health checks.
- Ambient context gathering: reads running containers, images, compose files,
  and working-directory contents **before being asked**, so answers are
  grounded rather than generic.

**Safety gates around mutating commands** (the most fully-specified of any tool
surveyed):
- **Approval-first, no exceptions in the default mode**: "every shell command,
  every file modification, every Docker operation is shown to you before it
  runs. You approve, you reject, or you redirect."
- **Session-scoped permissions**: approvals/trust do not persist across
  sessions — "permissions reset when you close the session. No lingering
  access."
- Optional **auto-approve mode** for trusted/repeated workflows exists as an
  explicit opt-in trade (convenience vs. friction), not the default.
- No mention of allowlist/denylist logic, rate limiting, or audit logging beyond
  the per-action approval UI — the safety model is entirely human-in-the-loop,
  not policy-as-code.

**Prompt patterns for small models**: not applicable — Gordon's backend is
Docker's own hosted model, not a small local model. (Relevant mainly as a
**counter-example**: its context-gathering strategy — read compose files, image
list, container state before answering — is a pattern worth copying regardless
of model size, since it reduces hallucination by grounding the prompt in real
local state rather than asking the model to guess.)

**Known failure modes** (from a hands-on third-party review, not Docker's own
docs):
- **Excessive verbosity / generic-first responses**: reviewer noted that for a
  crashing Node.js container, Gordon gave generic "check container logs / check
  status" troubleshooting steps rather than directly reading the visible logs
  and naming the missing dependency — i.e., it can default to a generic
  checklist instead of using the context it has access to.
- Requires user technical judgement to act on output; "won't replace a seasoned
  engineer."
- No documented hallucination incidents in this review, but also no systematic
  adversarial testing reported.

Sources: [Meet Gordon: AI Agent for Container Workflows](https://www.docker.com/blog/meet-gordon-dockers-ai-agent-for-your-entire-container-workflow/) · [Meet Gordon: An AI Agent for Docker](https://www.docker.com/blog/meet-gordon-an-ai-agent-for-docker/) · [Testing Docker's Gordon — Kubesimplify](https://blog.kubesimplify.com/testing-docker-ais-gordon-how-smart-is-it)

---

## 4. aiac (Firefly, gofireflyio)

**What it is**: A CLI/Go library that generates IaC and adjacent artifacts
(Terraform, Pulumi, CloudFormation, Dockerfiles, K8s manifests, CI/CD pipelines,
OPA policies, scripts, even DB queries) from a one-line natural-language ask, via
a configurable LLM backend including Ollama.

**Daily activities covered**:
- **Manifest/config generation only** — this is a generator, not an
  interactive/agentic assistant. No log triage, no cluster/daemon interaction.
- Prompt style is terse and imperative: `aiac terraform for a highly available
  eks`, `aiac dockerfile for secured nginx`, `aiac get kubectl commands to ...`.
  The tool strips filler words like "get"/"generate" from the ask.

**Safety gates around mutating commands**:
- **None documented.** With `--output-file`, output is written directly to disk;
  with `-q` (non-interactive/quiet), there is no review step at all before
  saving. Interactive mode allows eyeballing before save, but that's a UX
  courtesy, not an enforced gate. This is the **weakest safety posture of any
  tool surveyed** — appropriate given aiac never touches a live cluster/daemon
  (it only emits text/files), but a clear "what not to copy" if the artifact in
  question ever gets piped straight into `kubectl apply` or `docker run` by the
  user without a look.

**Prompt patterns for small models**:
- Ollama is a first-class backend: configured via TOML with just the API URL
  (defaults to `http://localhost:11434/api`) and model name. No shim or special
  prompt template is documented for small models — same prompt shape regardless
  of backend. Given the small-model tool-calling research below, this is
  plausibly why aiac stays a single-shot generator rather than an agent loop:
  a single well-templated generation request is far more reliable on a small
  model than multi-step tool orchestration.

**Known failure modes**:
- Chat-only models supported now (completion-style models dropped).
- Invalid model names **fail silently** at the API level — no upfront
  validation/verification.
- Provider-side rate limiting has no client-side mitigation.
- No hallucination/quality safeguards of any kind documented (e.g., no lint pass
  on generated Terraform/K8s YAML, no dry-run).

Sources: [gofireflyio/aiac](https://github.com/gofireflyio/aiac) · [aiac README](https://github.com/gofireflyio/aiac/blob/main/README.md)

---

## 5. kube-copilot (feiskyer)

**What it is**: A Kubernetes-focused CLI copilot supporting OpenAI, Azure
OpenAI, Anthropic Claude, Gemini, and other OpenAI-compatible backends (no
explicit Ollama mention, but "OpenAI-compatible" backends generally cover an
Ollama OpenAI-compatibility endpoint).

**Daily activities covered**:
- **Diagnose**: `kube-copilot diagnose --name <pod>` — LLM-assisted issue
  identification for a named resource.
- **Audit**: security-vulnerability scan via integrated `trivy`.
- **Generate**: manifest generation from natural-language instructions.
- **Execute**: open-ended `kube-copilot execute --instructions <text>` — the
  most autonomous mode, performs actions per free-text instruction, with an
  agent loop capped by `--max-iterations` (default 30).
- Also has MCP integration for pulling in external tools.

**Safety gates around mutating commands**:
- Only one explicit gate documented: after `generate`, "you will be prompted to
  confirm whether you want to apply" the generated manifests. This is the
  **only** confirmation step called out in the docs — `execute` and `diagnose`
  have no documented approval step despite `execute` being explicitly
  action-taking. Relies entirely on the ambient kubeconfig's existing RBAC as
  the safety boundary, not on anything kube-copilot itself enforces.

**Prompt patterns for small models**: not documented — README doesn't expose
the internal ReAct/agent prompt, tool-call format, or any small-model-specific
tuning. `--max-tokens` (default 2048) is the only tunable that hints at
resource-constrained use, but it's a length cap, not a reliability aid.

**Known failure modes**:
- No documented error-recovery strategy for failed tool calls within the
  `execute` loop.
- No hallucination guardrails around generated manifests (no dry-run/diff shown
  before the apply-confirmation, per the docs).
- `trivy` is a soft dependency ("only required for `audit`") with no documented
  fallback behavior if missing.

Sources: [feiskyer/kube-copilot README](https://github.com/feiskyer/kube-copilot/blob/master/README.md) · [feisky.xyz/kube-copilot](https://feisky.xyz/kube-copilot/)

---

## 6. Adjacent prior art (beyond the five named tools)

### kagent (CNCF Sandbox, Solo.io) — the most fully-specified safety design seen

kagent is a Kubernetes-native framework for deploying AI agents as CRDs, with
multi-LLM support **including Ollama**. Its published k8s-agent system prompt
(persona "KubeAssist") is the clearest concrete example of a production system
prompt for this exact domain, and worth mirroring structurally:

- **Explicit "Read Before Write" rule in the system prompt itself**: "Always use
  informational tools first before modification tools." Tools are split into a
  **Read-only set** (GetResources, DescribeResource, GetEvents, GetPodLogs,
  GetResourceYAML, GetClusterConfiguration, CheckServiceConnectivity,
  ExecuteCommand) and a **Modification set** (CreateResource, ApplyManifest,
  PatchResource, DeleteResource, Label/Annotate + removal variants) — the
  read/write split is a first-class, named distinction in the prompt, not just
  an implementation detail.
- Enforces a fixed **response shape**: Initial Assessment → Information
  Gathering → Analysis → Recommendations → Action Plan → Verification →
  Knowledge Sharing. A rigid structure like this is itself a reliability aid
  for smaller models, since it gives them a template to fill rather than an
  open-ended answer to compose.
- Requires explicit user confirmation before destructive actions and expects
  the agent to maintain a rollback plan.
- Platform-level features beyond the prompt: **tool approval gates**,
  "agent-initiated questions," and "cascading HITL" (human-in-the-loop) as
  first-class framework primitives — i.e., approval isn't bolted on by each
  agent author, it's a platform feature.

Source: [kagent.dev/agents/k8s-agent](https://kagent.dev/agents/k8s-agent) · [kagent-dev/kagent](https://github.com/kagent-dev/kagent) · [kagent.dev](https://kagent.dev/)

### HolmesGPT (Robusta / CNCF Sandbox, joint with Microsoft)

An agentic root-cause-investigation tool for cloud-native infra (Prometheus
queries, K8s events/logs, pod specs, deployment history), LLM-agnostic including
Ollama. Its own docs are the single most direct, citable warning about running
this class of tool on small local models:

> "Ollama support is experimental... tool-calling capabilities are limited and
> may produce inconsistent results." Users are explicitly told to validate
> against a hosted provider (Claude/OpenAI) first, then attempt Ollama.

Two integration paths are documented for Ollama: direct LiteLLM integration
(`OLLAMA_API_BASE` + `ollama_chat/` model prefix) or a fallback through Ollama's
OpenAI-compatible `/v1` endpoint "when users encounter compatibility issues with
specific models" — i.e., even the OpenAI-compatible-endpoint route is a
documented workaround for tool-calling breakage, not a nicety.

Source: [HolmesGPT Ollama docs](https://holmesgpt.dev/dev/ai-providers/ollama/) · [robusta-dev/holmesgpt](https://github.com/robusta-dev/holmesgpt)

### DockerGen AI (community project, Ollama-based Dockerfile generator)

A small, illustrative community tool: pulls `llama3.2:1b` via Ollama and uses a
single terse directive prompt: *"ONLY Generate an ideal Dockerfile for
{language} with best practices. Do not provide any description"* — explicitly
asking the model to suppress commentary and emit only the artifact. No safety
checks of any kind (no validation, no confirmation, prints straight to
console/file). Useful as a minimal real-world example of a single-shot,
budget-model prompt template, and as a cautionary example of skipping review
entirely.

Source: [DockerGen AI — devops.dev](https://blog.devops.dev/dockergen-ai-streamline-dockerfile-generation-with-ollama-llm-8b3d7dd727ba)

### General research: why small/local models break in agent loops

Independent of any single tool, a hands-on benchmark testing 7 local models in
a tool-calling coding-agent loop found three distinct, recurring failure
patterns directly relevant to designing ollama-docker/ollama-k8s:

1. **Refusal-to-act**: a model (qwen2.5:7b) called a read tool correctly, then
   asked permission to make the edit instead of proceeding — even though the
   system prompt explicitly said "ACT, DON'T ASK." Small models don't reliably
   follow imperative system-prompt instructions that conflict with their
   default cautious behavior.
2. **Format confusion**: a model (qwen2.5-coder:14b) emitted a tool call as
   plain-text JSON inside a markdown code block instead of using the real
   function-calling channel — output that "almost works," which the author
   flags as *worse* than a clean failure because it's tempting to build brittle
   parsing workarounds around it rather than fixing the prompt/model choice.
3. **Destructive retry loops**: a model (qwen3:14b) repeated an identical
   failing shell command 10 times across 30,000 tokens with no strategy change.
   A single added system-prompt line — "NEVER repeat the same failing tool call
   more than once" — fixed this specific model, cutting it to 9,000 tokens with
   a successful outcome. **Model generation mattered more than parameter
   count**: all qwen3 variants passed, all qwen2.5 variants struggled,
   regardless of 7B/8B/14B size.

Separately, broader small-model literature puts a rough **practical floor
around 7B parameters** for any viable tool-calling behavior at all (sub-7B
showing near-zero reliable invocation), and notes that even at a generous 95%
success rate *per call*, an 8-step agent loop only succeeds ~66% of the time
end-to-end because failures compound multiplicatively — a strong argument for
keeping tool/step counts low and preferring single-shot generation (aiac's
model) over long agent loops (kube-copilot/kagent's model) when the local model
is small.

Sources: [What Happens When Local LLMs Fail at Tool Calling](https://dev.to/kuroko1t/what-happens-when-local-llms-fail-at-tool-calling-testing-7-models-with-a-rust-coding-agent-cep) · [Best Local Models for Tool Calling in 2026](https://www.promptquorum.com/power-local-llm/best-local-models-tool-calling-2026)

### General research: guardrail architecture for AI agents against Kubernetes

Two independent write-ups (Red Hat Developer; an independent "Your AI Agent
Should Not Have Direct kubectl Access" piece) converge on the same architecture,
worth treating as consensus best practice regardless of which named tool you
compare it to:

- Put a **harness** between the model and kubectl/docker — never exec an
  LLM-produced command string directly. Parse it; check verb + resource against
  an explicit allowlist; reject anything else.
- **Never inherit the human's/engineer's credentials.** Dedicated
  service-account / minimal-identity per agent, scoped to only the
  namespaces/resources it needs. Cluster-admin "just to get it working" is
  called out by name, repeatedly, as the most common and most dangerous
  shortcut teams take.
- Treat **cluster/container data itself as untrusted input**, not just the
  user's prompt — annotations, labels, ConfigMap values, and log content can
  carry prompt-injection payloads that reach the model when it reads them as
  "context." This is a distinct risk from the user typing a bad instruction.
- Tiered risk model: auto-execute reads, rate-limit/log writes, require human
  approval for anything destructive or credential-adjacent (mirrors Gordon's
  approval-first design and kagent's read-before-write rule independently).
- Log what the model *asked* for vs. what the harness actually *allowed* —
  audit trail of the gate itself, not just the final action.

Sources: [Your AI Agent Should Not Have Direct kubectl Access](https://dev.to/mike_anderson_d01f52129fb/your-ai-agent-should-not-have-direct-kubectl-access-b1o) · [Red Hat Developer: Build resilient guardrails for AI agents on Kubernetes](https://developers.redhat.com/articles/2026/04/09/build-resilient-guardrails-openclaw-ai-agents-kubernetes)

---

## Cross-cutting comparison table

| Tool | Command drafting | Log/event triage | Manifest gen | Mutation safety gate | Local/Ollama support | Agent loop or single-shot |
|---|---|---|---|---|---|---|
| kubectl-ai | Yes (core) | Yes | Light | Confirm-before-run; `skipPermissions` escape hatch; sandboxing still roadmap | Yes, first-class (+ tool-use shim) | Agent loop (multi-turn) |
| k8sgpt | No | Yes (core, read-only) | No | N/A — never mutates; gate is anonymization of outbound data, and it's incomplete | Yes (`ollama` backend) | Single-shot scan + explain |
| Docker Ask Gordon | Yes (core) | Yes (core) | Yes (core) | Approval-first on every action; session-scoped trust; optional auto-approve | No (hosted backend only) | Agent loop |
| aiac | Light (command snippets) | No | Yes (core) | None | Yes, first-class | Single-shot generation |
| kube-copilot | Yes (`execute`) | Yes (`diagnose`) | Yes (`generate`) | Only on `generate` → apply; `execute` has none documented | Not explicit (OpenAI-compatible generically) | Agent loop (`execute`, max-iterations 30) |
| kagent (adjacent) | Yes | Yes | Yes | Read-before-write rule baked into system prompt; platform-level HITL/approval gates | Yes, first-class | Agent loop, CRD-managed |
| HolmesGPT (adjacent) | No | Yes (core) | No | N/A — investigate-only | Yes, but docs call it "experimental," tool-calling "limited/inconsistent" | Agent loop |

---

## Copy / avoid list

### Copy

1. **Approval-before-mutate, every time, no silent auto-execute of writes** —
   Gordon's model (every shell command/file mod/Docker op shown before running)
   and kagent's "read-before-write" prompt rule are the two clearest, most
   copyable safety patterns. Maps directly onto the project's already-decided
   **read-free, mutate-gated** posture.
2. **Split tools/commands into an explicit read-only set vs. a modification
   set, and name that split in the system prompt itself** (kagent) — don't
   leave the read/write distinction implicit in code; state it as a rule the
   model can reference.
3. **Ground the prompt in real local state before drafting** (Gordon's ambient
   context: running containers, compose files, images, working dir) — reduces
   hallucinated flags/names/paths, which is the exact failure class that turns
   into a namespace/container-name typo disaster.
4. **Prefer single-shot generation over long agent loops when the model is
   small** (aiac's design, versus kube-copilot/kagent's loop). Combined with
   the "8 steps at 95% ≈ 66% success" compounding-failure math, this is a
   strong architectural argument for T4/T5: keep each skill invocation to one
   or two model calls (draft, maybe one summarize pass), not a multi-step
   autonomous loop.
5. **Use a tool-use shim / rewritten prompt for small models that struggle
   with native function-calling** (kubectl-ai's `enableToolUseShim`) — expect
   to need a similar adapter/format constraint rather than assuming a small
   Ollama model will emit clean structured tool calls unaided.
6. **A concrete "don't repeat a failing action" instruction in the system
   prompt** — the single line that fixed the destructive-retry-loop failure
   mode in third-party testing. Cheap to add, empirically effective.
7. **Anonymize/mask before any data leaves the box, if ever sending to a
   non-local backend** (k8sgpt) — less relevant if this project is Ollama-only,
   but worth stating as a rule in case a cloud fallback is ever added.
8. **Terse, artifact-only prompt style for generation tasks** (aiac's "get
   terraform for X"; DockerGen AI's "ONLY generate... do not provide any
   description") — for manifest/Dockerfile drafting on small models, explicitly
   suppressing commentary keeps output parseable and token-cheap.

### Avoid

1. **Don't rely on kubeconfig/engineer-credential inheritance as the safety
   boundary** (kube-copilot's implicit approach, and the #1 mistake called out
   in both guardrail write-ups). Never let the assistant run with
   broader-than-necessary ambient permissions "because it's easier."
2. **Don't ship a generate-then-write-with-no-review path** (aiac's `-q` /
   `--output-file` non-interactive mode) — every mutating draft should have a
   review step before it touches disk or a cluster, matching this project's own
   mutate-gated decision.
3. **Don't leave anonymization/masking partial and call it done** (k8sgpt: 9 of
   14 analyzers masked, Events/Logs/Pods not, acknowledged gap left unfixed for
   an extended period). If a safety filter is added, it needs to cover 100% of
   paths that reach the model or it's a false sense of security.
4. **Don't assume small local models will just refuse dangerous requests
   correctly, or just follow "ACT, DON'T ASK"/"don't ask permission" style
   instructions reliably** — third-party testing found models doing the
   opposite of both instructions depending on model family. Verify empirically
   per-model rather than trusting one prompt line to hold under all local
   models this project might target.
5. **Don't build brittle parsing workarounds for "almost-working" tool-call
   output** (the qwen2.5-coder markdown-JSON case) — if a small model can't hit
   the tool-call format cleanly and reliably, that's a signal to change prompt
   design or narrow the model list, not a signal to add regex scaffolding.
6. **Don't give the assistant an open-ended, uncapped agentic `execute`-style
   mode with no per-step confirmation** (kube-copilot's `execute` has no
   documented gate, unlike its own `generate` command) — inconsistent gating
   across a tool's own command surface is itself a design smell to avoid
   repeating.
7. **Don't treat log/event/annotation content read *by* the assistant as safe
   just because it's local, not user-typed** — prompt-injection-style payloads
   in pod logs, labels, or ConfigMaps are a documented risk class distinct from
   a malicious user prompt, and apply even fully offline/on-prem.

---

## Sources

1. [GoogleCloudPlatform/kubectl-ai (GitHub)](https://github.com/GoogleCloudPlatform/kubectl-ai)
2. [kubectl-ai Roadmap — Issue #265](https://github.com/GoogleCloudPlatform/kubectl-ai/issues/265)
3. [Running Ollama + kubectl-ai Locally (Medium)](https://medium.com/h7w/running-ollama-kubectl-ai-locally-9c61be90c01d)
4. [k8sgpt-ai/k8sgpt (GitHub)](https://github.com/k8sgpt-ai/k8sgpt)
5. [K8sGPT vs kubectl-ai: Which Tool Should You Use (LinkedIn)](https://www.linkedin.com/pulse/k8sgpt-vs-kubectl-ai-which-tool-should-you-use-swapnil-kulkarni-jxegf)
6. [Meet Gordon: Docker's AI Agent for Your Entire Container Workflow (Docker blog)](https://www.docker.com/blog/meet-gordon-dockers-ai-agent-for-your-entire-container-workflow/)
7. [Meet Gordon: An AI Agent for Docker (Docker blog)](https://www.docker.com/blog/meet-gordon-an-ai-agent-for-docker/)
8. [Testing Docker AI's Gordon — How Smart Is It (Kubesimplify)](https://blog.kubesimplify.com/testing-docker-ais-gordon-how-smart-is-it)
9. [gofireflyio/aiac (GitHub)](https://github.com/gofireflyio/aiac)
10. [feiskyer/kube-copilot README (GitHub)](https://github.com/feiskyer/kube-copilot/blob/master/README.md)
11. [kagent.dev — Kubernetes AI Agent System Prompt](https://kagent.dev/agents/k8s-agent)
12. [kagent-dev/kagent (GitHub)](https://github.com/kagent-dev/kagent)
13. [HolmesGPT — Ollama provider docs](https://holmesgpt.dev/dev/ai-providers/ollama/)
14. [robusta-dev/holmesgpt (GitHub)](https://github.com/robusta-dev/holmesgpt)
15. [DockerGen AI: Streamline Dockerfile Generation with Ollama LLM (devops.dev)](https://blog.devops.dev/dockergen-ai-streamline-dockerfile-generation-with-ollama-llm-8b3d7dd727ba)
16. [What Happens When Local LLMs Fail at Tool Calling (DEV Community)](https://dev.to/kuroko1t/what-happens-when-local-llms-fail-at-tool-calling-testing-7-models-with-a-rust-coding-agent-cep)
17. [Best Local Models for Tool Calling in 2026 (PromptQuorum)](https://www.promptquorum.com/power-local-llm/best-local-models-tool-calling-2026)
18. [Your AI Agent Should Not Have Direct kubectl Access (DEV Community)](https://dev.to/mike_anderson_d01f52129fb/your-ai-agent-should-not-have-direct-kubectl-access-b1o)
19. [Red Hat Developer: Build resilient guardrails for AI agents on Kubernetes](https://developers.redhat.com/articles/2026/04/09/build-resilient-guardrails-openclaw-ai-agents-kubernetes)
