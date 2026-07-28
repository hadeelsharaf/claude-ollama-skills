# Fleet benchmark + dogfood notes — 2026-07-29

Machine: Windows 11, 16 GB RAM, NVIDIA GeForce RTX 4050 Laptop, 6 GB VRAM; small models
run 100% GPU. Ollama 0.32.4.
Raw data for the doc refresh (plan Task 5) and the dogfood evidence (spec §10.7).

> **Every number in this file is GPU-accelerated.** The repo's older published
> measurements were taken CPU-only on a machine without a usable GPU. The two sets are
> **not** like-for-like and must never be compared directly, averaged, or presented as a
> before/after of any code change. If a doc row changes because of this file, the reason is
> "re-measured on GPU hardware", not "the code got faster".

## Hardware

`nvidia-smi` (verbatim header block, 2026-07-29):

```
Wed Jul 29 00:43:37 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 572.40                 Driver Version: 572.40         CUDA Version: 12.8     |
|-----------------------------------------+------------------------+----------------------+
| GPU  Name                  Driver-Model | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 4050 ...  WDDM  |   00000000:01:00.0 Off |                  N/A |
| N/A   49C    P8              3W /   35W |    1215MiB /   6141MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+
```

`ollama ps` while each model was resident (PROCESSOR column is the evidence):

```
NAME                       ID              SIZE      PROCESSOR          CONTEXT    UNTIL
qwen2.5-coder:1.5b         d7372fd82851    1.2 GB    100% GPU           4096       29 minutes from now
gemma2:2b                  8ccf136fdd52    1.9 GB    100% GPU           4096       29 minutes from now
devstral-small-2:latest    24277f07f62d    15 GB     77%/23% CPU/GPU    4096       29 minutes from now
devstral-small-2:latest    24277f07f62d    15 GB     100% CPU           4096       29 minutes from now
```

Both small models are fully GPU-resident (VRAM total 6141 MiB; 1.2 GB and 1.9 GB fit
easily). devstral-small-2 (15 GB) cannot fit and Ollama splits it — and the split it
chooses is **not stable**: three loads landed on `77%/23% CPU/GPU`, one landed on
`100% CPU`. That instability is the whole story of the probe below.

`ollama --version` → `ollama version is 0.32.4`.

Free system RAM moved a lot during this session; each number below records the free RAM at
the moment it was taken rather than assuming one figure.

## Cold load

Procedure per DESIGN D4: `ollama stop` every model shown by `ollama ps`, confirm `ollama ps`
prints an empty table, then `python scripts/ollama_ask.py warmup --task general --model <m>`.
The `warmed <model> in <N>s` line is the cold-load number. Never two models loaded at once.

```
warmed qwen2.5-coder:1.5b in 6.4s (keep_alive 30m)
warmed gemma2:2b in 6.2s (keep_alive 30m)
```

Free RAM at the qwen cold load: 7.3 GB. Both are GPU loads (`100% GPU` in `ollama ps`
immediately afterwards).

**Caveat for Task 5 — quote 6.4s / 6.2s as the cold load, never an `E2E warmup` line.** The
in-suite warmup numbers are noisy for the reason below and are not cold loads.

Cold-load caveat for Task 5: the `E2E warmup` step inside each suite run below is **not** a
cold load — the model is already resident from this step, and the numbers there (3.2–7.0s)
are dominated by Ollama re-loading the model when the requested context size differs from
the resident one (`ollama ps` showed `CONTEXT 4096` after the warmup command and
`CONTEXT 2048` after a later suite step). Quote the 6.4s / 6.2s figures above as cold load,
not the in-suite warmup line.

## E2E qwen2.5-coder:1.5b

Command: `RUN_OLLAMA_E2E=1 OLLAMA_SKILLS_MODEL=qwen2.5-coder:1.5b python tests/e2e_local.py`

Run 1 (model resident from the cold load above), exit 0:

```
E2E health 4.3s
E2E warmup 3.6s
E2E ask 2.6s
  ask said: 'OK'
E2E commit-msg 2.8s
  commit-msg said: 'feat: Add notify function to send emails'
E2E draft-command 3.4s
  draft-command said: '{\n  "command": "Get-ChildItem -Path .\\\\ | Sort-Object LastWriteTimeDescending | Select-Object -First'...
E2E summarize 6.3s
  summarize said: 'VERDICT: 1 error\n\n- Connection refused to db attempt 0'...
E2E all green
```

Run 2 (warm repeat, taken to separate flake from pattern), exit 0:

```
E2E health 4.3s
E2E warmup 6.6s
E2E ask 2.4s
  ask said: 'OK'
E2E commit-msg 2.6s
  commit-msg said: 'fix: add notify function'
E2E draft-command 3.4s
  draft-command said: '{\n  "command": "Get-ChildItem -Path .\\\\ | Sort-Object LastWriteTimeDescending | Select-Object -First'...
E2E summarize 6.5s
  summarize said: 'VERDICT: 1 error\n\n- Connection refused to db attempt 0'...
E2E all green
```

Representative op for the docs: `ask` 2.4–2.6s, `commit-msg` 2.6–2.8s, `summarize`
6.3–6.5s (30-line log, map+reduce). GPU-accelerated.

Content observations (soft quality, no exit code attached — see the verdicts section):
- Run 2's commit type is wrong: adding a brand-new `notify.py` is a `feat`, not a `fix`.
  Format-valid, semantically mislabeled — the same failure mode as the dogfood tally.
- `summarize` reports "1 error" for a 30-error input in both runs. gemma2 gets this right
  (see below). The digest is not wrong about *what* the error is, only about the count.

## E2E gemma2:2b

Command: `RUN_OLLAMA_E2E=1 OLLAMA_SKILLS_MODEL=gemma2:2b python tests/e2e_local.py`
(`ollama stop qwen2.5-coder:1.5b` + empty `ollama ps` first.)

Run 1 (model resident from its cold load), exit 0:

```
E2E health 4.3s
E2E warmup 3.2s
E2E ask 2.8s
  ask said: 'OK'
E2E commit-msg 3.0s
  commit-msg said: 'feat: Add email notification functionality'
E2E draft-command 3.6s
  draft-command said: '{\n  "command": "Get-ChildItem -Path \'C:\\folder_path\' -Descending | Sort-Object CreationTime -Descend'...
E2E summarize 8.3s
  summarize said: 'VERDICT: There were 30 errors, with the most notable being a connection refused error to the databas'...
E2E all green
```

Run 2 (warm repeat), exit 0:

```
E2E health 4.3s
E2E warmup 7.0s
E2E ask 2.5s
  ask said: 'OK'
E2E commit-msg 2.8s
  commit-msg said: 'feat: Add email notification functionality to notify function'
E2E draft-command 3.6s
  draft-command said: '{\n  "command": "Get-ChildItem -Path \'C:\\folder_path\' -Descending | Sort-Object CreationTime -Descend'...
E2E summarize 8.0s
  summarize said: 'VERDICT: There were 30 errors, with one connection refused to db attempt.\n* "connection refused" err'...
E2E all green
```

Representative op for the docs: `ask` 2.5–2.8s, `commit-msg` 2.8–3.0s, `summarize`
8.0–8.3s. GPU-accelerated.

Content observations (soft quality):
- Both commit drafts get the type right (`feat` for a new file) — better than qwen's run 2.
- `summarize` counts the errors correctly ("30 errors") in both runs, where qwen said "1".
  This is consistent with `summarize`'s PREFERENCES putting gemma2 ahead of the coder.
- `draft-command` invents a `-Descending` flag on `Get-ChildItem` and a placeholder path
  `'C:\folder_path'` instead of the current folder. It is valid JSON (so the step passes)
  but the command would not run. Not a `shell`/`code` task owner, so no list change — but
  it is why `shell` should not prefer gemma2 over a coder model.

Cross-model timing note: gemma2:2b is ~25% slower than qwen2.5-coder:1.5b on `summarize`
(8.0–8.3s vs 6.3–6.5s) and roughly equal on the short ops. Both are single-digit seconds
per call on this GPU.

## devstral-small-2 probe

Command (per brief), free RAM 7.4 GB immediately before the first attempt, `ollama ps`
empty (gemma2 stopped) before each cold attempt:

```
python scripts/ollama_ask.py ask "Reply with the single word: OK" \
    --model devstral-small-2:latest --timeout 120 --stall-seconds 120
```

Raw results — **the outcome is not deterministic**, so all five attempts are recorded:

| attempt | state | exit | wall | `ollama ps` PROCESSOR |
|---|---|---|---|---|
| 1 | cold (`ps` empty) | 0 (answered `OK`) | not captured (timer tool missing; well under 120s) | 77%/23% CPU/GPU |
| 2 | warm (resident from #1) | 0 (answered `OK`) | 5.2s | 77%/23% CPU/GPU |
| 3 | cold (`ollama stop` first) | **5** (`Stalled: no output for 120s`) | 123.3s | **100% CPU** |
| 4 | cold (`ollama stop` first) | 0 (answered `OK`) | 64.1s | 77%/23% CPU/GPU |
| 5 | cold (`ollama stop` first) | 0 (answered `OK`) | 67.7s | 77%/23% CPU/GPU |

Attempt 1's wall time was lost to a missing timer utility, so **attempt 1 is qualitative
only** — it establishes "answered `OK` from cold, comfortably inside the 120 s guard" and
nothing more. Task 5 must take its cold latency figure from attempts 4 and 5 (64.1s / 67.7s),
never from attempt 1.

Verbatim failure line from attempt 3:

```
error: Stalled: no output for 120s from devstral-small-2:latest. Warm up first, shrink the input, or pick a smaller model.
COLD: exit=5 wall=123.3s
```

**Interpretation (no scripted conclusion — this is what actually happened).** A 15.2 GB
model on a 6 GB-VRAM GPU with ~7 GB free system RAM does *not* simply fail. Ollama splits
it, and the outcome follows which split it picks:

- When it manages a partial GPU offload (`77%/23% CPU/GPU`), the model answers a
  one-word prompt in **64–68 s cold** and **5.2 s warm**. That is a *slow success*, exit 0.
- When it falls back to `100% CPU`, it produces no first token inside 120 s and the
  stall guard fires: **exit 5 at 123.3 s**.

So 3 of 4 cold attempts succeeded slowly and 1 stalled out, from the identical command.
The docs must not claim devstral "cannot run" or "did not answer" on this machine — one
cold attempt did stall, but the majority answered. The accurate wording is: *devstral-small-2
(15.2 GB) does not fit in 6 GB VRAM + ~7 GB free RAM, so Ollama partially offloads it;
one-word answers take ~65 s cold / ~5 s warm when the split works, and a cold call can
stall past the 120 s guard (exit 5) when Ollama falls back to CPU-only.*

Per the brief's exit-0 branch, this also means the wording Task 5 copies is: **the RAM gate
is about *predicted* fit, not about the model being unusable.** `resolve_model` refuses to
auto-select a model larger than free RAM because ~65 s per call (and a real chance of a
120 s stall) is the wrong default for an interactive skill; `--model devstral-small-2:latest`
remains the informed override for a user who accepts that cost, and it works.

Second-order evidence that the gate is right — verbatim `python scripts/ollama_ask.py health`
captured in the same command as cold attempt 5, with devstral still resident:

```
Ollama 0.32.4 at http://localhost:11434 — OK
Installed models (3):
  qwen2.5-coder:1.5b       1.0 GB   WARNING: bigger than free RAM (0.4 GB) — will be slow or fail
  gemma2:2b                1.6 GB   WARNING: bigger than free RAM (0.4 GB) — will be slow or fail
  devstral-small-2:latest  15.2 GB   WARNING: bigger than free RAM (0.4 GB) — will be slow or fail
Free RAM: 0.4 GB
```

So holding devstral resident starves the machine to **0.4 GB free**, and at that point all
three models — including the 1.0 GB and 1.6 GB small ones — trip the oversize warning. That
is observed output above, not an inference from the size>free rule.

After `ollama stop devstral-small-2:latest`, `health` reported **Free RAM: 11.5 GB** and the
two small models no longer warn; devstral alone still does, and is still correctly gated
(15.2 GB > 11.5 GB free).

## Quality-gate verdicts

Gate rule applied (brief Step 5): FAIL = the step failed output validation (exit 6) on
**both** the original run and the single rerun. Only a FAIL demotes a model in that task's
`PREFERENCES` list.

**qwen2.5-coder:1.5b** — 2 runs, both exit 0:

| step | run 1 | run 2 | verdict |
|---|---|---|---|
| health | 0 | 0 | PASS |
| warmup | 0 | 0 | PASS |
| ask | 0 | 0 | PASS |
| commit-msg | 0 | 0 | **PASS** (valid Conventional Commit both times) |
| draft-command | 0 | 0 | PASS (valid JSON both times) |
| summarize | 0 | 0 | PASS |

**gemma2:2b** — 2 runs, both exit 0:

| step | run 1 | run 2 | verdict |
|---|---|---|---|
| health | 0 | 0 | PASS |
| warmup | 0 | 0 | PASS |
| ask | 0 | 0 | PASS |
| commit-msg | 0 | 0 | PASS |
| draft-command | 0 | 0 | PASS (valid JSON both times) |
| summarize | 0 | 0 | PASS |

**Verdict: all pass, lists unchanged.** `scripts/ollama_ask.py` PREFERENCES and
`tests/test_ollama_ask.py` were not touched by this task. `python -m unittest discover -s tests`
→ `Ran 63 tests ... OK` (baseline, unchanged).

### Recorded concern for the controller: commit-draft quality vs. the passing gate

There is a real tension worth escalating rather than acting on unilaterally. The dogfood
tally for this refresh shows **0 of 4 commit drafts used as-is** with
`qwen2.5-coder:1.5b` (task0 replaced / exit 6, task1 edited — untruthful about scope,
task2 model-failed / exit 6, task3 edited — mislabeled scope), and this task's own run 2
mislabeled a new-file diff as `fix:`. Yet the e2e `commit-msg` step passed 4/4 times across
both models.

Why both are true, and why I did **not** reorder:

1. The e2e fixture is a 5-line single-file diff with an obvious purpose. The dogfood diffs
   are multi-file changes mixing docs, features and tests, where the failure is *scope
   judgment* ("call it docs when it also adds a feature"), not format. The e2e step measures
   format validity; the tally measures semantic accuracy. They are not the same signal, and
   only the first is the gate.
2. `commit-msg` retries once internally on a format miss, so the e2e step's PASS is a pass
   of "produced a valid line within its own retry budget" — a weaker claim than "the first
   draft was good".
3. The gate demands hard evidence: exit 6 on the original run **and** the rerun of the same
   step. I have zero exit-6 e2e results across 4 suite runs. The dogfood exit-6s (task0,
   task2) are on ad-hoc real diffs, not the gated e2e step, and they are not reproducible
   on demand — that is soft evidence by the brief's own definition.
4. There is nowhere better to demote to. The candidate above `qwen2.5-coder` for `commit`
   would have to be `llama3.1`/`llama3.2`/`qwen3`/`gemma3`, none of which are installed;
   the only installed alternative is `gemma2:2b`, and while gemma2 got the commit *type*
   right in both e2e runs, two 5-line-diff samples is not a basis for promoting it over a
   coder model for `commit`. Reordering on that would be exactly the soft-evidence move the
   brief forbids.

Recommendation for the controller (not a change made here): treat the review step in the
dogfood loop as load-bearing rather than ceremonial — the local model's commit draft is a
starting point that needs a scope check on every multi-file change. If a future refresh
installs `llama3.1` or `qwen3`, re-run this gate with a **multi-file** commit fixture before
deciding whether `qwen2.5-coder` should keep the head of the `commit` list.

## Task 3 smoke

Live run against the real local Ollama on this machine (`python scripts/ollama_ask.py models`):

```
task       model                        source
commit     qwen2.5-coder:1.5b           auto
shell      qwen2.5-coder:1.5b           auto
code       qwen2.5-coder:1.5b           auto
general    gemma2:2b                    auto
summarize  gemma2:2b                    auto
skipped devstral-small-2:latest for code (15.2 GB > 6.7 GB free RAM)
```

`python scripts/ollama_ask.py models --json`:

```json
{
  "tasks": {
    "commit": {"model": "qwen2.5-coder:1.5b", "source": "auto"},
    "shell": {"model": "qwen2.5-coder:1.5b", "source": "auto"},
    "code": {"model": "qwen2.5-coder:1.5b", "source": "auto"},
    "general": {"model": "gemma2:2b", "source": "auto"},
    "summarize": {"model": "gemma2:2b", "source": "auto"}
  },
  "installed": ["qwen2.5-coder:1.5b", "gemma2:2b", "devstral-small-2:latest"],
  "skipped": [
    {"model": "devstral-small-2:latest", "size": 15177374099,
     "free_ram": 6731968512, "tasks": ["code"]}
  ]
}
```

Matches expectations: commit/shell/code = qwen2.5-coder:1.5b, general/summarize = gemma2:2b,
zero `none` rows, one skip line for devstral. Free RAM on this machine is 6.7 GB (not the
8.0 GB test fixture) — expected, since this is the live machine's real free RAM, not a pin.

## Dogfood tally

- 7eb0c29 task0: draft replaced (model failed exit code 6)
- 786e72f task1: draft edited (model focused only on docs, needed to highlight preferences + tests)
- 7a87635 task2: draft replaced (model-failed, exit 6: no valid Conventional Commit line)
- b45d274 task3: draft edited (model scoped it "docs" and omitted the RAM-gate feature entirely)
- 04e70bd task4: draft replaced (exit 0, valid format, but typed a docs-only change "fix:" and understated the scope as "GPU usage")
- 87ed13b task4-fix1: draft replaced (exit 0, valid format, but again typed a docs change "fix:" and named only the minor cold-load caveat, missing the main change)
