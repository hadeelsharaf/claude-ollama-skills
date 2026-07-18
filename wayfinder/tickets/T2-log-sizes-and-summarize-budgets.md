---
id: T2
title: "Log/status output sizes and small-model summarization budgets"
type: research
status: closed
assignee: "research-agent-T2"
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

## Resolution

Full findings, measurements, and sourcing:
[wayfinder/research/T2-budgets.md](../research/T2-budgets.md).

Grounded in: real local measurement (`docker logs --tail 50/200/500` on a live
container — 20.4 KB at `--tail 200`; full `git log` on this repo in
`--oneline`/default/`--stat`/`-p` form), this project's own recorded speeds
(qwen3:8b ~7 tok/s CPU prefill, 2.7k tokens = 7-10+ min; llama3.2:1b small
calls 3-7 s), and its existing `max_input_chars: 2500` / `stall_seconds: 90` /
`total_timeout_seconds: 480` config. kubectl sizes could not be measured
(zero contexts configured on this machine) — those numbers are estimates,
flagged for re-measurement once T7 stands up a real cluster.

### Recommended default budgets

| Parameter | Default |
|---|---|
| `docker logs` / `kubectl logs` tail | `--tail 200` (+ dedupe near-identical lines before chunking — measured: ~185 of 200 real tail lines were repeat health-check pings) |
| `kubectl describe pod` | whole output; prefer Conditions/Status/Events over Env/Volume dumps if over budget |
| `kubectl get events` | `--sort-by=.lastTimestamp`, last ~50 (events self-expire at 1h TTL) |
| `git log` | `--oneline -n 50` default; `--stat` opt-in; **`-p` never by default** (unbounded — measured ~4.7 KB/commit and climbing with change size) |
| Chunk size / overlap | **1,500 chars (~430 tokens)**, ~10% overlap by whole lines (never mid-line) |
| Per-chunk (map) output cap | **80 tokens** |
| Reduce / single-shot output cap | **200 tokens** |
| Chunk-summaries per reduce call before recursing | ~8 (else recurse: "reduce of reduces") |
| Pre-chunk hard input ceiling | **100,000 chars** — refuse + ask to narrow scope beyond this, `--force` to override (mirrors existing `check_budget()`) |
| `num_ctx` | pin to **2048** (don't rely on Ollama's dynamic 2048-4096 default) |
| Temperature | 0.2 |
| **Model per tier** | ≤1,500 chars (1 call): **llama3.2:1b** default, qwen3:8b optional-quality; 1,500-20,000 chars (2-13 chunks): **llama3.2:1b** map+reduce, qwen3:8b optional for final reduce only if ≤~6 chunk-summaries; 20,000-100,000 chars (many chunks, hierarchical reduce): **llama3.2:1b only, no exceptions** — qwen3:8b's ~7 tok/s prefill makes it unaffordable at scale on this machine |

Worked example from real measurement: today's `docker logs --tail 200`
(20,200 chars) chunks into ~14 pieces ≈ 1.5-3 minutes total (map + recursive
reduce) on llama3.2:1b — or, with the dedupe pre-filter applied first
(collapsing the repeat health-check lines actually observed), likely drops to
a single call, ~5-10 seconds. Worst case at the 100,000-char hard ceiling ≈
9.5 minutes, bounded and shows chunk progress — versus today's unbounded
qwen3:8b single-call behavior (7-10+ min, no chunking, no progress, and per
this research already close to its own 90s stall-timeout margin).

### Chunking algorithm sketch

1. Capture the source with the bounded default above — never unbounded
   (no bare `docker logs`, no bare `git log`, never `-p` by default).
2. Structural pre-filter first: collapse repeated near-identical lines
   (logs); prefer Conditions/Status/Events over Env/Volume dumps
   (`describe pod`); prefer `--oneline`/`--stat` over `-p` (git). Cheapest
   possible saving — runs before the model sees anything.
3. Hard-cap check (100,000 chars) on the post-filter text; over budget fails
   fast asking the user to narrow scope or pass `--force`.
4. Single-chunk shortcut: if it fits in one 1,500-char chunk, skip the map
   stage and call the model once with the final-answer prompt (200-token cap).
5. Otherwise split into whole-line chunks of ≤1,500 chars, each new chunk
   opening with the last ~10% of the previous chunk's lines (line-based
   overlap, never mid-line).
6. Map: summarize each chunk independently, llama3.2:1b, 80-token cap, a
   system prompt that explicitly tells it to ignore any instructions found
   inside the excerpt (untrusted-input rule already used elsewhere in this
   project).
7. Reduce: concatenate chunk summaries; if that itself exceeds one chunk
   budget, recurse in batches of ~8 ("reduce of reduces") until one text
   remains.
8. Final call produces verdict + bullets (200-token cap) from the reduced
   text — llama3.2:1b by default; qwen3:8b only per the tier rules above,
   opt-in only.
9. Degrade per-chunk: a stalled/timed-out chunk gets dropped with a visible
   marker, not an aborted run — partial coverage beats total failure.
10. Output is always labeled an untrusted draft, same as every other skill
    here.

Open gaps for T3+: kubectl sizes are estimates pending a real cluster (T7);
llama3.2:1b has no measured large-prompt data point on this machine, so the
1,500-char chunk size is conservative-by-design, not calibrated — time one
real chunk-sized call before locking it in. Exact CLI flags/config-key names
are left to T3 to decide with the user.
