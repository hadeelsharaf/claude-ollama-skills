# Design: Model fleet refresh + RAM-gated auto-detect

Status: approved in brainstorming (2026-07-28)
Machine of record: Windows 11, 16 GB RAM (~7.5 GB free at measurement), no GPU, Ollama 0.32.4

## 1. Context

The repo's model auto-detection, example config, and every published measurement were
built around a fleet that no longer exists on the development machine. Installed today:

| Model | Size | Status vs repo assumptions |
|---|---|---|
| `qwen2.5-coder:1.5b` | 1.0 GB | matches `qwen2.5-coder` / `qwen2.5` prefixes; never measured |
| `gemma2:2b` | 1.6 GB | matches **no** prefix in any list (`PREFERENCES` only knows `gemma3`) |
| `devstral-small-2:latest` | 15.2 GB | matches the `devstral` prefix in `code`; larger than free RAM |

Observed breakage (`python scripts/ollama_ask.py models`):

1. **`general` dead-ends** — no installed model matches its list, so `ollama-ask` and
   plain `warmup` fail with exit 4 on this machine.
2. **`summarize` auto-picks a coder model** (`qwen2.5-coder:1.5b`) for digesting logs
   while a better-suited general model (`gemma2:2b`) sits installed.
3. **Latent 15 GB trap** — on a machine without `qwen2.5-coder`, `code` auto-picks
   `devstral-small-2:latest` (position 3), which exceeds free RAM and burns up to 480 s
   before failing with exit 5. `health` warns about this; `resolve_model()` is blind to it.
4. Every doc table, the example config, and the e2e workflow name models
   (`qwen3:8b`, `llama3.2:1b`, `devstral:latest`) that are gone.

## 2. Goals

- `general` resolves on this machine; no task dead-ends against the current fleet.
- `summarize` auto-picks `gemma2:2b`, not a coder model.
- Auto-detect never picks a model larger than free RAM; explicit pins still win.
- `devstral-small-2` is used automatically **on machines where it fits** (it stays at
  its current position in the `code` list; the gate handles the rest).
- Measured numbers for the new fleet replace the stale ones in shipped docs.
- `qwen2.5-coder` is preferred where a coder model is the right tool (commit, shell,
  code) and available as a last resort for `general`.

## 3. Non-goals

- No redesign of selection (no capability registry, no size-class matching). The
  prefix-list mechanism stays; this was explicitly declined in brainstorming.
- No new CLI flags, no new exit codes, no config schema changes.
- No rewriting of historical records (`docs/RESEARCH.md` citations,
  `docs/skill-tests.md` probe records, CHANGELOG entries, DESIGN's original measured
  table and decision log — see §7).

## 4. Design

### 4.1 Preference-list changes (`scripts/ollama_ask.py`, `PREFERENCES`)

Rules applied: `gemma2` is inserted immediately after `gemma3` wherever it appears
(family adjacency — it inherits gemma3's documented reasoning); the gemma family is
appended to `shell` so a gemma-only machine cannot dead-end there; `qwen2.5-coder` is
appended **last** to `general` (a general instruct model should beat a coder model for
free-form prompts; the coder is a floor, not a preference).

```python
PREFERENCES = {
    "code": ["qwen3-coder", "qwen2.5-coder", "devstral", "deepseek-coder",
             "codegemma", "qwen3", "llama3.1", "gemma3", "gemma2", "llama3.2", "mistral"],
    "commit": ["qwen2.5-coder", "llama3.1", "llama3.2", "qwen3", "gemma3", "gemma2"],
    "shell": ["qwen3", "llama3.1", "llama3.2", "qwen2.5", "gemma3", "gemma2"],
    "general": ["qwen3", "llama3.1", "gemma3", "gemma2", "llama3.2", "mistral",
                "qwen2.5-coder"],
    "summarize": ["llama3.2", "gemma3", "gemma2", "qwen2.5", "llama3.1", "mistral",
                  "qwen3"],
}
```

Notes:
- `qwen2.5` (in `shell`, `summarize`) already prefix-matches `qwen2.5-coder:*` via
  `str.startswith` — no separate entry needed there.
- In `summarize`, `gemma2` lands **before** `qwen2.5`, so log digests go to the general
  model, fixing breakage #2. The existing "qwen3 last" rule (decision D12) is untouched.
- The comment block above `PREFERENCES` (embedding-models-must-lose, summarize-fast-lane)
  is kept and extended with one line explaining gemma2 adjacency.

Resulting resolution on the machine of record:

| task | auto-pick |
|---|---|
| commit | `qwen2.5-coder:1.5b` |
| shell | `qwen2.5-coder:1.5b` |
| code | `qwen2.5-coder:1.5b` (devstral gated out, see 4.2) |
| general | `gemma2:2b` (was: exit 4) |
| summarize | `gemma2:2b` (was: coder model) |

### 4.2 RAM gate in auto-detect (`resolve_model()`)

**Placement.** Inside the auto-detect branch only. The `flag → env → config` returns
happen before it, so an explicit pin is an absolute override (this is the escape hatch;
no new flag). `warn_if_remote`-style loudness is not needed — `health` already warns
about oversized models generally.

**Mechanics.**

- When auto-detect populates `installed_cache["models"]` (names, unchanged shape), it
  also populates `installed_cache["sizes"]` (`{name: size_bytes}`) from the same
  `/api/tags` response, and `installed_cache["free_ram"]` via one call to
  `free_ram_bytes()`. One read per cache means the five rows of `models` can never
  disagree with each other about free RAM.
- In the preference scan, a candidate whose known size exceeds known free RAM is
  skipped: a record `{"task", "model", "size", "free_ram"}` is appended to
  `installed_cache.setdefault("skipped", [])` and the scan continues.
- **The gate stands down silently** (single `debug()` line) whenever it lacks data:
  `free_ram_bytes()` returned `None`, or the cache was seeded without a `"sizes"` key
  (which is exactly what existing tests like
  `test_resolve_model_summarize_qwen3_is_last_resort` do — they keep passing unmodified).
- `resolve_model()`'s signature and `(model, source)` return are unchanged. Zero churn
  in `generate()`, `cmd_warmup`, or any other caller.

**Failure shape.** If the scan ends with no pick but at least one candidate was gated,
raise the existing `EXIT_NO_MODEL` (4) with a message naming the concrete blocker and
both remedies:

> `devstral-small-2:latest matches the 'code' preference list but is 15.2 GB with only
> 7.5 GB free RAM. Free memory, or pin a smaller model with --model or
> tasks.code.model in .ollama-skills.json.`

If nothing matched at all, the two existing exit-4 messages are unchanged. No new exit
code anywhere; skills already treat exit 4 as "Claude does the task itself and says so,"
so the fallback contract is untouched.

### 4.3 `models` output

Human output gains skip lines after the table, one per gated candidate:

```
skipped devstral-small-2:latest for code (15.2 GB > 7.5 GB free RAM)
```

`models --json` gains a top-level `"skipped"` array of the records from 4.2. `health`
is unchanged (its size-vs-RAM warning already exists and stays the single source of
that wording).

### 4.4 Stale pull hints

The two hardcoded `Try: ollama pull llama3.2:1b` strings
(`ollama_ask.py` — `resolve_model` no-models error and `cmd_health`) become
`Try: ollama pull gemma2:2b` — the one small model that satisfies **all five** task
lists by itself.

## 5. Benchmark protocol

Reuses `tests/e2e_local.py` verbatim (it prints `E2E <name> <seconds>s` per step and
honours `OLLAMA_SKILLS_MODEL`). Decision D4 (never two local models loaded at once)
applies: `ollama stop <model>` between runs, `ollama ps` to confirm.

Per small model (`qwen2.5-coder:1.5b`, then `gemma2:2b`):

1. `ollama stop` anything loaded; confirm with `ollama ps`.
2. Cold load: time `python scripts/ollama_ask.py warmup --task general --model <m>`.
3. `RUN_OLLAMA_E2E=1` + `OLLAMA_SKILLS_MODEL=<m>` → `python tests/e2e_local.py`;
   record every step timing.

**devstral probe (neutral — record what happens, no scripted conclusion):**

```
python scripts/ollama_ask.py ask "Reply with the single word: OK" \
  --model devstral-small-2:latest --timeout 120 --stall-seconds 120
```

Record exit code and wall time. If it stalls/times out (exit 5), the docs row says
"did not answer within 120 s at 7.5 GB free (15.2 GB model)". If it answers, the row
reports the real latency and the RAM-gate story in the docs is adjusted to say the gate
is about *predicted* fit, with `--model` as the informed override.

**Quality gate (explicit rule):** the e2e runs are pass/fail on output format, not just
timers. If a model repeatedly fails format validation — `commit-msg` exiting 6 on the
Conventional-Commit check, `draft-command` failing JSON validation, summarize breaking
the digest contract — that is a **finding that reorders or removes the model from that
task's preference list before any docs are written**. The published speed table contains
only models that passed. Raw timings and pass/fail results are written to a scratch
notes file so the doc-refresh task can run mechanically from them.

## 6. Documentation refresh

Rewrite (current-claims files):

| File | Change |
|---|---|
| `README.md` §"Models used during development" | current three-model fleet, with devstral-small-2's measured status |
| `README.md` §"Measured speed" | new table: `qwen2.5-coder:1.5b` and `gemma2:2b` columns; devstral row from the probe |
| `config/.ollama-skills.example.json` | `commit`/`shell`/`code` → `qwen2.5-coder:1.5b`; `general`/`summarize` → `gemma2:2b`; other keys unchanged |
| `docs/DESIGN.md` §11 model lists | updated to match 4.1 exactly |
| `docs/ADVANCED.md` per-hardware table | add both measured small models to the "No GPU, 16 GB RAM" row |
| `.github/workflows/e2e.yml` | pull + `OLLAMA_SKILLS_MODEL` → `qwen2.5-coder:1.5b` |
| `tests/e2e_local.py`, `tests/e2e_k8s.py` docstrings | model suggestions updated |
| `CLAUDE.md` model-resolution paragraph | note the RAM gate in one sentence |

Append, never overwrite (history-preserving):

- `docs/DESIGN.md` measured-facts table and decision log: existing rows stay, labelled
  with their machine/date. A new dated subsection carries the 2026-07-28 fleet numbers,
  plus one new decision row: *D14 — free-RAM gate in auto-detect; explicit pins bypass;
  gate stands down without size/RAM data.*
- `CHANGELOG.md`: new `## [Unreleased]` section — Added: free-RAM gate in auto-detect
  with skip reporting in `models`; Changed: preference lists (gemma2 family,
  `qwen2.5-coder` floor for general), example config models, measured numbers,
  e2e default model, pull hints. `plugin.json` stays 0.2.0; the gate is a behaviour
  addition, so the release that ships it becomes 0.3.0.

Leave alone (records, not claims): `docs/RESEARCH.md` (cites external literature),
`docs/skill-tests.md` (records which model a live probe actually ran on), all existing
CHANGELOG entries.

## 7. Limitations (stated, not fixed here)

- **The gate is a lenient proxy.** File size > free RAM is the same test `health` uses
  (consistency is deliberate), but true memory need is size *plus* KV cache and runtime
  overhead. A 7 GB model with 7.5 GB free passes the gate and may still thrash. Do not
  "improve" the gate into an estimator without new measurements; today it exists to
  catch the clear-cut case (15.2 GB vs 7.5 GB).
- **Free RAM is volatile** (measured 7.1 and 7.5 GB minutes apart). For borderline
  models the auto-pick can differ between runs. Mitigation: the skip line prints both
  numbers, so `models` always explains the choice it made.
- Benchmark numbers are one machine, one day. The tables say so, as they already do.

## 8. Testing

All new tests go in `tests/test_ollama_ask.py` against the existing fake-server
harness; no network, stdlib only.

**Determinism first:** `setUp` pins `ollama_ask.free_ram_bytes` to a lambda returning
8 GB (restored in `tearDown`), insulating the *entire* suite — old tests included —
from the CI runner's real memory. `setUp` also clears `ollama_ask._TAGS_CACHE`: the
module caches `/api/tags` per host and every test shares one host, so without this a
swapped per-test tag response (see `test_models_reports_skips`) would silently be
served stale data.

New cases (direct `resolve_model()` calls with seeded caches, following the existing
`test_resolve_model_summarize_qwen3_is_last_resort` pattern — `FAKE_MODELS` is not
mutated, because `test_health_reports_models` and the commit auto-detect test assert
against it):

| Test | Asserts |
|---|---|
| `test_resolve_model_general_matches_gemma2` | `general` resolves against a `["qwen2.5-coder:1.5b", "gemma2:2b"]` fleet → `gemma2:2b` (regression for breakage #1) |
| `test_resolve_model_summarize_prefers_gemma2_over_coder` | same fleet, `summarize` → `gemma2:2b` (breakage #2) |
| `test_ram_gate_skips_oversized_auto` | oversized model earlier in preference is skipped, smaller one picked, skip recorded in the cache |
| `test_ram_gate_all_gated_exits_4` | only oversized candidates → `CliError` code 4, message contains model name, size, and free RAM |
| `test_ram_gate_pinned_model_bypasses` | `--model <oversized>` → returned with source `flag`, no gating |
| `test_ram_gate_no_sizes_no_gate` | cache seeded without `"sizes"` → no gating (also proves existing seeded tests' path) |
| `test_models_reports_skips` | `models` human output contains the skip line; `--json` contains `"skipped"` — via a swappable class-level models list on `FakeOllamaHandler`, restored in `tearDown` |

No prose-pinning tests change: skills never name models and no safety wording moves.

## 9. Implementation tasks and model assignment

Instructions for plan execution: **each task names its model tier explicitly; the
executor must set that model per subagent — do not inherit the session default model
for any task.** Assignments are by complexity: haiku for mechanical edits with exact
content given in this spec, sonnet for logic/tests/judged writing, opus where results
must be interpreted and decisions made.

| # | Task | Model | Depends on | Why this tier |
|---|---|---|---|---|
| T1 | `PREFERENCES` edit + two pull-hint strings (§4.1, §4.4) | **haiku** | — | exact replacement content is in this spec |
| T2 | RAM gate + skip reporting in `resolve_model()` / `cmd_models` (§4.2, §4.3) | **sonnet** | T1 | ~25 lines of logic in the one runtime file; fully specified but touches the cache contract |
| T3 | Unit tests incl. the `free_ram_bytes` pin in `setUp` (§8) | **sonnet** | T2 | test design against an existing harness; must not disturb seeded-cache tests |
| T4 | Benchmark runs, devstral probe, quality-gate judgment; write raw numbers + pass/fail to a scratch notes file (§5) | **opus** | T1, T2 | interprets ambiguous outcomes (partial stalls, format failures) and may reorder preference lists — a decision, not an edit |
| T5 | Doc refresh from T4's notes: README fleet + speed table, example config, `e2e.yml`, e2e docstrings, ADVANCED row, CLAUDE.md sentence (§6 rewrite list) | **haiku** | T4 | mechanical once the numbers exist |
| T6 | History-preserving DESIGN.md append (dated subsection + D14) and CHANGELOG `[Unreleased]` (§6 append list) | **sonnet** | T4 | must extend records without falsifying them; judgment about wording |
| T7 | Final verification (§10) | **sonnet** | T3, T5, T6 | runs the checks and diagnoses any failure |

T4 can run in parallel with T3 (e2e pins models via env, bypassing resolution).

## 10. Verification

1. `python -m unittest discover -s tests -v` — green, including the seven new tests.
2. `python scripts/validate_repo.py` — all OK.
3. `python scripts/ollama_ask.py models` on the machine of record: five resolved rows,
   zero `none` rows, `general` = `gemma2:2b`, `summarize` = `gemma2:2b`, and a
   `skipped devstral-small-2:latest` line.
4. `python scripts/ollama_ask.py warmup --task general` succeeds (the previously broken
   path).
5. One full `RUN_OLLAMA_E2E=1` pass per small model completed during T4 with all steps
   passing format validation.
6. Grep sweep: `qwen3:8b`, `llama3.2:1b`, `devstral:latest` appear in **no** rewrite-list
   file from §6 (CHANGELOG, RESEARCH, skill-tests, and DESIGN's historical sections
   exempt as records).
