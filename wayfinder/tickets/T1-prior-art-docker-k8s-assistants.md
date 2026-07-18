---
id: T1
title: "Prior art: local-LLM assistants for Docker and Kubernetes"
type: research
status: open
assignee: ""
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
