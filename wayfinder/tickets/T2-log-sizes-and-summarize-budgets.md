---
id: T2
title: "Log/status output sizes and small-model summarization budgets"
type: research
status: open
assignee: ""
blocked-by: []
---

## Question

How big are the texts the `summarize` subcommand must digest, and what chunking
strategy fits a CPU-only machine? Establish: typical sizes of `docker logs --tail N`,
`kubectl describe pod`, `kubectl get events`, and `git log` ranges; proven
map-reduce / chunked summarization patterns for 1B–8B local models; sensible
defaults (tail lines, chunk chars, per-chunk output cap) given our measured speeds
(qwen3:8b prefill ~7 tok/s on CPU; llama3.2:1b ~3–7 s per small call). End with:
recommended default budgets + chunking algorithm sketch feeding the summarize
spec (T3).
