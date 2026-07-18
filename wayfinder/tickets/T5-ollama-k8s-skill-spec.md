---
id: T5
title: "Spec the ollama-k8s skill"
type: grilling
status: open
assignee: ""
blocked-by: [T1]
---

## Question

Lock the ollama-k8s SKILL.md content: read verbs (get, describe, logs, events,
top ...), gated mutations (apply, scale, rollout restart, patch ...), deny-list
(delete namespace/pvc, drain, cordon on prod nodes, anything cluster-scoped ...),
**context guardrails** (always echo current context + namespace before any gated
command; clean error path when no context is configured — true on the dev machine
today), the triage flow (describe + events + logs → summarize), and manifest
drafting via draft-code. Feed the copy/avoid list from T1.
