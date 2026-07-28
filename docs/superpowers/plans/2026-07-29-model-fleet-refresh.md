# Model Fleet Refresh + RAM-Gated Auto-Detect — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make model auto-detection work with (and benchmark against) the machine's current Ollama fleet — `qwen2.5-coder:1.5b`, `gemma2:2b`, `devstral-small-2:latest` — and add a free-RAM gate so auto-detect never picks a model bigger than free memory.

**Architecture:** All runtime changes land in the single script `scripts/ollama_ask.py` (`PREFERENCES` lists + a RAM gate inside `resolve_model()`'s auto-detect branch + skip reporting in `cmd_models`). Tests extend the existing fake-Ollama-server harness in `tests/test_ollama_ask.py`. Docs/config are refreshed from a benchmark notes file produced by real e2e runs.

**Tech Stack:** Python 3.9+ standard library only. `unittest`. No pip packages, ever.

**Spec:** `docs/superpowers/specs/2026-07-28-model-fleet-refresh-design.md` (approved). Task numbering below maps to spec §9: plan Task 1 = spec T1 (+ its two regression tests), plan Tasks 2–3 = spec T2+T3 reordered so tests exist before/with the gate code, plan Tasks 4–7 = spec T4–T7. Task 0 is pre-flight (uncommitted session work must land before per-task dogfood commits can stage cleanly).

## Global Constraints

- **Executor model per task is explicit — never inherit the session default.** The orchestrator passes `model: "haiku" | "sonnet" | "opus"` on every Agent dispatch, exactly as each task's header says (spec §9).
- **Local models:** delegated drafting uses whatever `resolve_model` picks (`qwen2.5-coder:1.5b` for `commit` after Task 1); each task's header lists the local models it exercises.
- Standard library only, runtime and tests. Python 3.9 compatible (no `match`, no `X | Y` type syntax in annotations at runtime).
- Exit-code contract is frozen: `0/2/3/4/5/6/7/8/1/130`. No new codes, no renumbering.
- Unit tests stay hermetic: fake server on 127.0.0.1 only. Never call a real model from `tests/test_ollama_ask.py` (spec §5.1 scope guard).
- Never two local models loaded at once (DESIGN decision D4): `ollama stop` + `ollama ps` between benchmark runs.
- Skill/agent safety wording is pinned by tests — this plan touches **no** `skills/*/SKILL.md` or `agents/*.md` files.
- Conventional Commits; every commit message ends with the trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Work directly on branch `draft` in this checkout — **no worktree isolation** — because the dogfood loop pushes `draft` to `origin/draft` after every task.
- Historical records are never rewritten: `docs/RESEARCH.md`, `docs/skill-tests.md`, existing `CHANGELOG.md` entries, and `docs/DESIGN.md`'s original measured table + decision rows D1–D13.

## Shared Procedure: DOGFOOD LOOP (spec §5.1)

Every task below ends with this loop for its own files. Run it with the **Bash tool** (multiline commit messages are painful in PowerShell). `<paths>` = only that task's files; `<notes>` = `docs/superpowers/notes/2026-07-29-fleet-benchmarks.md`.

1. `git add <paths>` — never `git add -A`.
2. `python scripts/ollama_ask.py commit-msg` — the local model drafts; the staged diff stays out of your context. **Do not run `git diff --cached` yourself** (only `--stat` is allowed, in step 3).
3. Review the printed draft: first line matches `type: summary` (type ∈ feat, fix, build, chore, ci, docs, style, refactor, perf, test; ≤ 72 chars), and it truthfully describes the files shown by `git diff --cached --stat`. Edit or replace a bad draft — you own what you approve.
4. Commit and push in one gated step (branch `draft` is not protected; `--allow-protected` must NOT appear):
   ```bash
   python scripts/ollama_ask.py commit-push --message "docs: your reviewed message here

   Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
   ```
5. On `commit-msg` exit 3/4/5/6: write the message yourself from the `--stat` output, still use `commit-push`, and record the failure. On `commit-push` exit 7: stop and report (should be impossible on `draft`). Exit 8: report the git error verbatim; do not retry blindly.
6. Append one line to the `## Dogfood tally` section of `<notes>` (create the section if missing):
   `- <commit hash> <task#>: draft used-as-is | edited | replaced | model-failed (<one-clause reason>)`
   Never amend a commit to include its own tally line — the tally line for commit N rides in commit N+1 (the last pending lines are committed by Task 7).

---

### Task 0: Land pending workspace changes

**Executor model: haiku** (explicit — do not inherit). **Local models exercised:** `qwen2.5-coder:1.5b` (commit draft; first live rep of the dogfood loop).

**Files:**
- Modify: none (they are already modified in the worktree: `.claude-plugin/plugin.json`, `CONTRIBUTING.md`, `README.md`, `docs/DESIGN.md`)
- Add (untracked): `CLAUDE.md`
- Create: `docs/superpowers/notes/2026-07-29-fleet-benchmarks.md`

**Interfaces:**
- Consumes: nothing.
- Produces: a clean worktree so later tasks stage only their own files; the notes file skeleton every later task appends to.

- [ ] **Step 1: Confirm the expected dirty state**

Run: `git status --porcelain`
Expected exactly: ` M .claude-plugin/plugin.json`, ` M CONTRIBUTING.md`, ` M README.md`, ` M docs/DESIGN.md`, `?? CLAUDE.md` (plus this plan file and the spec dir if not yet committed — include them in the same commit). Anything else: stop and report.

- [ ] **Step 2: Create the notes file skeleton**

Create `docs/superpowers/notes/2026-07-29-fleet-benchmarks.md`:

```markdown
# Fleet benchmark + dogfood notes — 2026-07-29

Machine: Windows 11, 16 GB RAM, no GPU, Ollama 0.32.4.
Raw data for the doc refresh (plan Task 5) and the dogfood evidence (spec §10.7).

## Cold load

## E2E qwen2.5-coder:1.5b

## E2E gemma2:2b

## devstral-small-2 probe

## Quality-gate verdicts

## Dogfood tally
```

- [ ] **Step 3: Sanity check**

Run: `python -m unittest discover -s tests` and `python scripts/validate_repo.py`
Expected: 56 tests OK; validator "All checks passed."

- [ ] **Step 4: DOGFOOD LOOP**

`<paths>` = `.claude-plugin/plugin.json CONTRIBUTING.md README.md docs/DESIGN.md CLAUDE.md docs/superpowers/notes/2026-07-29-fleet-benchmarks.md docs/superpowers/plans/2026-07-29-model-fleet-refresh.md`
Suggested message shape if the draft needs replacing: `chore: land plugin 0.2.0 bump, dead-link fixes, CLAUDE.md, fleet notes skeleton`.
Note: this first push publishes the two spec commits already sitting ahead on `draft` — that is intended (spec §5.1 targets `origin/draft`).

---

### Task 1: Preference lists + pull hints (spec §4.1, §4.4)

**Executor model: haiku** (explicit — do not inherit). **Local models exercised:** none at runtime (unit tests hit the fake server); `qwen2.5-coder:1.5b` in the dogfood loop.

**Files:**
- Modify: `scripts/ollama_ask.py` (the `PREFERENCES` dict ~line 67 and two pull-hint strings ~lines 217 and 500)
- Test: `tests/test_ollama_ask.py` (two new tests after `test_resolve_model_summarize_qwen3_is_last_resort`)

**Interfaces:**
- Consumes: `ollama_ask.resolve_model(task, cfg, flag_model, installed_cache) -> (model, source)` — existing signature, unchanged.
- Produces: the exact `PREFERENCES` lists below; Tasks 2–5 and the spec's resolution table depend on this ordering.

- [ ] **Step 1: Write the two failing regression tests**

Add to `tests/test_ollama_ask.py`, directly after `test_resolve_model_summarize_qwen3_is_last_resort`:

```python
    def test_resolve_model_general_matches_gemma2(self):
        """Regression: a coder+gemma2 fleet must not dead-end 'general'
        (it did before gemma2 joined PREFERENCES), and a coder-only fleet
        must still resolve via the qwen2.5-coder floor."""
        cfg = {"tasks": {}, "host": os.environ["OLLAMA_HOST"]}
        model, source = ollama_ask.resolve_model(
            "general", cfg, None,
            {"models": ["qwen2.5-coder:1.5b", "gemma2:2b"]})
        self.assertEqual(model, "gemma2:2b")
        self.assertEqual(source, "auto")
        model, _ = ollama_ask.resolve_model(
            "general", cfg, None, {"models": ["qwen2.5-coder:1.5b"]})
        self.assertEqual(model, "qwen2.5-coder:1.5b")

    def test_resolve_model_summarize_prefers_gemma2_over_coder(self):
        """summarize digests logs; the general model must beat the coder."""
        cfg = {"tasks": {}, "host": os.environ["OLLAMA_HOST"]}
        model, _ = ollama_ask.resolve_model(
            "summarize", cfg, None,
            {"models": ["qwen2.5-coder:1.5b", "gemma2:2b"]})
        self.assertEqual(model, "gemma2:2b")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m unittest tests.test_ollama_ask.OllamaAskTests.test_resolve_model_general_matches_gemma2 tests.test_ollama_ask.OllamaAskTests.test_resolve_model_summarize_prefers_gemma2_over_coder -v`
Expected: first ERRORs with `CliError` ("No installed model matches the 'general' preference list"); second FAILs asserting `'qwen2.5-coder:1.5b' != 'gemma2:2b'`.

- [ ] **Step 3: Replace the `PREFERENCES` dict**

In `scripts/ollama_ask.py`, replace the whole `PREFERENCES = {...}` block (keep the existing three comment lines above it, and add one) with:

```python
# First installed model whose name starts with a prefix wins (top first).
# Code prefers coder-specialized models, then falls back to curated general
# models — never to an arbitrary installed model (embedding models must lose).
# gemma2 rides directly after gemma3 everywhere: same family, same role.
PREFERENCES = {
    "code": ["qwen3-coder", "qwen2.5-coder", "devstral", "deepseek-coder",
             "codegemma", "qwen3", "llama3.1", "gemma3", "gemma2", "llama3.2",
             "mistral"],
    "commit": ["qwen2.5-coder", "llama3.1", "llama3.2", "qwen3", "gemma3",
               "gemma2"],
    "shell": ["qwen3", "llama3.1", "llama3.2", "qwen2.5", "gemma3", "gemma2"],
    # general wants an instruct model; the coder is a floor, not a preference.
    "general": ["qwen3", "llama3.1", "gemma3", "gemma2", "llama3.2", "mistral",
                "qwen2.5-coder"],
    # summarize runs many times per digest (map + reduce), so a fast model must
    # auto-win; qwen3 sits LAST -> the slow qwen3:8b is a last resort (prefer --model).
    "summarize": ["llama3.2", "gemma3", "gemma2", "qwen2.5", "llama3.1",
                  "mistral", "qwen3"],
}
```

- [ ] **Step 4: Update the two pull hints**

Same file, two exact string edits:
- In `resolve_model`: `"No Ollama models installed. Try: ollama pull llama3.2:1b"` → `"No Ollama models installed. Try: ollama pull gemma2:2b"`
- In `cmd_health`: `print("No models installed. Try: ollama pull llama3.2:1b")` → `print("No models installed. Try: ollama pull gemma2:2b")`

(`gemma2:2b` is the one small model matching all five task lists by itself — spec §4.4.)

- [ ] **Step 5: Run the two tests again, then the full suite**

Run: the Step-2 command, then `python -m unittest discover -s tests`
Expected: both PASS; full suite 58 OK (the existing `commit → llama3.2:1b` and summarize-last-resort tests must still pass — the new lists keep those orderings).

- [ ] **Step 6: DOGFOOD LOOP**

`<paths>` = `scripts/ollama_ask.py tests/test_ollama_ask.py` (+ the notes file if a tally line from Task 0 is pending).

---

### Task 2: Test-harness determinism (RAM pin, tag-cache clear, swappable tags)

**Executor model: sonnet** (explicit — do not inherit). **Local models exercised:** none at runtime; `qwen2.5-coder:1.5b` in the dogfood loop.

**Files:**
- Modify: `tests/test_ollama_ask.py` only (`FakeOllamaHandler` class attrs + `do_GET`, `setUp`, `tearDown`)

**Interfaces:**
- Consumes: `ollama_ask.free_ram_bytes()` (module-level function), `ollama_ask._TAGS_CACHE` (module-level dict keyed by host).
- Produces: for Task 3's tests — `FakeOllamaHandler.models_response` (class attr, list of `{"name", "size"}` dicts, reset to `FAKE_MODELS` each test) and a suite-wide pinned `free_ram_bytes() == 8_000_000_000`.

- [ ] **Step 1: Make the fake server's tag response swappable**

In `FakeOllamaHandler`, next to the existing `counters`/`last_payload` class attrs, add:

```python
    models_response: list = FAKE_MODELS
```

In `do_GET`, change `self._send_json(200, {"models": FAKE_MODELS})` to `self._send_json(200, {"models": FakeOllamaHandler.models_response})`.

- [ ] **Step 2: Pin free RAM and clear caches per test**

In `setUp`, after the existing `FakeOllamaHandler.counters.clear()` line, add:

```python
        FakeOllamaHandler.models_response = FAKE_MODELS
        ollama_ask._TAGS_CACHE.clear()
        self._orig_free_ram = ollama_ask.free_ram_bytes
        ollama_ask.free_ram_bytes = lambda: 8_000_000_000
```

In `tearDown`, before the environment restore, add:

```python
        ollama_ask.free_ram_bytes = self._orig_free_ram
```

Why: `_TAGS_CACHE` is keyed by host and every test shares one host — without the clear, a swapped `models_response` is silently served stale data. The 8 GB pin insulates the whole suite (old tests included) from the CI runner's real memory; `FAKE_MODELS`' biggest entry is 5 GB, so nothing gates and existing assertions are unaffected (spec §8).

- [ ] **Step 3: Run the full suite**

Run: `python -m unittest discover -s tests -v`
Expected: 58 tests OK. If `test_health_reports_models` output changed, it may only be the free-RAM line now reading `8.0 GB` — that test asserts model names, not RAM, so it must still pass.

- [ ] **Step 4: DOGFOOD LOOP**

`<paths>` = `tests/test_ollama_ask.py` (+ pending tally line in the notes file).

---

### Task 3: RAM gate in `resolve_model` + skip reporting in `models` (spec §4.2, §4.3)

**Executor model: sonnet** (explicit — do not inherit). **Local models exercised:** none at runtime; `qwen2.5-coder:1.5b` in the dogfood loop.

**Files:**
- Modify: `scripts/ollama_ask.py` (`resolve_model`, `cmd_models`, new helper `_oversized_report`)
- Test: `tests/test_ollama_ask.py` (five new tests)

**Interfaces:**
- Consumes: Task 1's `PREFERENCES`; Task 2's pinned `free_ram_bytes` and `FakeOllamaHandler.models_response`; existing `gb(num_bytes) -> str`, `debug(msg)`, `CliError`, `EXIT_NO_MODEL`, `TASKS`.
- Produces: `resolve_model` fills `installed_cache` keys `"models"` (list[str]), `"sizes"` (dict[str, int]), `"free_ram"` (int or None) and skips oversized auto candidates; `_oversized_report(cache) -> list` of `{"model": str, "size": int, "free_ram": int, "tasks": list[str]}`; `models` human output gains `skipped <model> for <tasks> (<size> > <free> free RAM)` lines and `--json` gains a top-level `"skipped"` array.

**Design note (reconciles spec §4.2 with §4.3/§10.3):** on the machine of record, `code` resolves at prefix `qwen2.5-coder` and the scan never *reaches* `devstral` — so scan-time skip records alone would print nothing, yet spec §10.3 requires a `skipped devstral-small-2:latest` line. Therefore: the scan-time gate exists for **correct picks and the exit-4 message**, while `models`' skip report is computed **standalone** by `_oversized_report` — every installed model that exceeds free RAM and matches at least one task's preference list, labeled with those tasks. Observable behavior matches the spec exactly; only the internal bookkeeping differs (no `installed_cache["skipped"]` writes from `resolve_model`).

- [ ] **Step 1: Write the five failing tests**

Add to `tests/test_ollama_ask.py` after the Task-1 tests. Also add one class-level constant next to the `resolved()` helper region:

```python
    DEVSTRAL = "devstral-small-2:latest"

    def test_ram_gate_skips_oversized_auto(self):
        """An oversized model earlier in preference is skipped; the scan
        continues to a model that fits."""
        cfg = {"tasks": {}, "host": os.environ["OLLAMA_HOST"]}
        cache = {
            "models": [self.DEVSTRAL, "gemma2:2b"],
            "sizes": {self.DEVSTRAL: 15_177_374_099,
                      "gemma2:2b": 1_629_518_495},
            "free_ram": 8_000_000_000,
        }
        model, source = ollama_ask.resolve_model("code", cfg, None, cache)
        self.assertEqual(model, "gemma2:2b")
        self.assertEqual(source, "auto")

    def test_ram_gate_all_gated_exits_4(self):
        cfg = {"tasks": {}, "host": os.environ["OLLAMA_HOST"]}
        cache = {
            "models": [self.DEVSTRAL],
            "sizes": {self.DEVSTRAL: 15_177_374_099},
            "free_ram": 8_000_000_000,
        }
        with self.assertRaises(ollama_ask.CliError) as ctx:
            ollama_ask.resolve_model("code", cfg, None, cache)
        self.assertEqual(ctx.exception.code, ollama_ask.EXIT_NO_MODEL)
        message = str(ctx.exception)
        self.assertIn(self.DEVSTRAL, message)
        self.assertIn("15.2 GB", message)
        self.assertIn("8.0 GB", message)
        self.assertIn("--model", message)

    def test_ram_gate_pinned_model_bypasses(self):
        """Explicit picks are never gated: pinning is the informed override."""
        cfg = {"tasks": {}, "host": os.environ["OLLAMA_HOST"]}
        cache = {
            "models": [self.DEVSTRAL],
            "sizes": {self.DEVSTRAL: 15_177_374_099},
            "free_ram": 8_000_000_000,
        }
        model, source = ollama_ask.resolve_model(
            "code", cfg, self.DEVSTRAL, cache)
        self.assertEqual((model, source), (self.DEVSTRAL, "flag"))

    def test_ram_gate_no_sizes_no_gate(self):
        """A cache seeded without sizes (how other tests seed it) never
        gates — the gate stands down without data."""
        cfg = {"tasks": {}, "host": os.environ["OLLAMA_HOST"]}
        model, source = ollama_ask.resolve_model(
            "code", cfg, None, {"models": [self.DEVSTRAL]})
        self.assertEqual(model, self.DEVSTRAL)
        self.assertEqual(source, "auto")

    def test_models_reports_skips(self):
        FakeOllamaHandler.models_response = FAKE_MODELS + [
            {"name": self.DEVSTRAL, "size": 15_177_374_099},
        ]
        code, out, err = self.run_cli("models")
        self.assertEqual(code, 0, msg=err)
        self.assertIn(
            "skipped devstral-small-2:latest for code "
            "(15.2 GB > 8.0 GB free RAM)", out)
        code, out, err = self.run_cli("models", "--json")
        self.assertEqual(code, 0, msg=err)
        data = json.loads(out)
        self.assertEqual(data["skipped"], [{
            "model": self.DEVSTRAL, "size": 15_177_374_099,
            "free_ram": 8_000_000_000, "tasks": ["code"]}])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m unittest tests.test_ollama_ask.OllamaAskTests.test_ram_gate_skips_oversized_auto tests.test_ollama_ask.OllamaAskTests.test_ram_gate_all_gated_exits_4 tests.test_ollama_ask.OllamaAskTests.test_ram_gate_pinned_model_bypasses tests.test_ollama_ask.OllamaAskTests.test_ram_gate_no_sizes_no_gate tests.test_ollama_ask.OllamaAskTests.test_models_reports_skips -v`
Expected: skips-oversized FAILs (returns devstral, no gate yet); all-gated FAILs (no exception raised); pinned and no-sizes may already PASS (they document existing behavior — fine); models-reports-skips FAILs (no skip line, KeyError `'skipped'`).

- [ ] **Step 3: Implement the gate in `resolve_model`**

Replace the auto-detect half of `resolve_model` (everything from `if "models" not in installed_cache:` to the end of the function) with:

```python
    if "models" not in installed_cache:
        tags = installed_models(cfg["host"])
        installed_cache["models"] = [m.get("name", "") for m in tags]
        installed_cache["sizes"] = {
            m.get("name", ""): int(m.get("size", 0)) for m in tags}
    if "free_ram" not in installed_cache:
        installed_cache["free_ram"] = free_ram_bytes()
    names = installed_cache["models"]
    sizes = installed_cache.get("sizes") or {}
    free = installed_cache["free_ram"]
    gated = []  # (name, size) matches skipped because they exceed free RAM
    for prefix in PREFERENCES.get(task, []):
        for name in names:
            if not name.startswith(prefix):
                continue
            size = sizes.get(name)
            if free is not None and size and size > free:
                debug(f"auto-detect skipped {name} for {task}: "
                      f"{gb(size)} > {gb(free)} free")
                gated.append((name, size))
                continue
            return name, "auto"
    if gated:
        name, size = gated[0]
        raise CliError(
            EXIT_NO_MODEL,
            f"{name} matches the '{task}' preference list but is {gb(size)} "
            f"with only {gb(free)} free RAM. Free memory, or pin a smaller "
            f"model with --model or tasks.{task}.model in .ollama-skills.json.",
        )
    if not names:
        raise CliError(EXIT_NO_MODEL,
                       "No Ollama models installed. Try: ollama pull gemma2:2b")
    wanted = ", ".join(PREFERENCES.get(task, []))
    raise CliError(
        EXIT_NO_MODEL,
        f"No installed model matches the '{task}' preference list ({wanted}). "
        f"Installed: {', '.join(names)}. Set tasks.{task}.model in "
        ".ollama-skills.json or pass --model.",
    )
```

Also extend the docstring's first line block with: `Auto-detect skips models bigger than free RAM (it stands down when sizes or free RAM are unknown); flag/env/config picks are never gated.`

- [ ] **Step 4: Implement `_oversized_report` and wire it into `cmd_models`**

Add directly above `cmd_models`:

```python
def _oversized_report(cache: dict) -> list:
    """Installed models auto-detect will never pick because they exceed free
    RAM, with the tasks whose preference lists they would otherwise serve."""
    free = cache.get("free_ram")
    sizes = cache.get("sizes") or {}
    if free is None:
        return []
    report = []
    for name in cache.get("models", []):
        size = sizes.get(name)
        if not size or size <= free:
            continue
        tasks = [t for t in TASKS
                 if any(name.startswith(p) for p in PREFERENCES.get(t, []))]
        if tasks:
            report.append({"model": name, "size": size,
                           "free_ram": free, "tasks": tasks})
    return report
```

In `cmd_models`, after the resolution loop, insert `skipped = _oversized_report(cache)`; change the `--json` print to include it (`{"tasks": resolved, "installed": cache.get("models", []), "skipped": skipped}`); and after the human table's `for task, info ...` loop add:

```python
    for rec in skipped:
        print(f"skipped {rec['model']} for {', '.join(rec['tasks'])} "
              f"({gb(rec['size'])} > {gb(rec['free_ram'])} free RAM)")
```

(When `--model` pins everything, the cache is never populated and the report is empty — correct: a pinned run has no auto-detect story to tell.)

- [ ] **Step 5: Run the five tests, then the full suite, then the validator**

Run: the Step-2 command; `python -m unittest discover -s tests`; `python scripts/validate_repo.py`
Expected: all five PASS; full suite 63 OK; validator all OK (it compiles `ollama_ask.py`).

- [ ] **Step 6: Live smoke test on this machine**

Run: `python scripts/ollama_ask.py models` and `python scripts/ollama_ask.py models --json`
Expected: five resolved rows — commit/shell/code = `qwen2.5-coder:1.5b`, general/summarize = `gemma2:2b`, zero `none` rows — plus `skipped devstral-small-2:latest for code (15.2 GB > <free> GB free RAM)`; JSON has the matching `skipped` entry. Paste the output into the notes file under a `## Task 3 smoke` heading.

- [ ] **Step 7: DOGFOOD LOOP**

`<paths>` = `scripts/ollama_ask.py tests/test_ollama_ask.py docs/superpowers/notes/2026-07-29-fleet-benchmarks.md`

---

### Task 4: Benchmarks, devstral probe, quality-gate judgment (spec §5)

**Executor model: opus** (explicit — do not inherit; this task interprets ambiguous outcomes and may reorder preference lists). **Local models exercised:** `qwen2.5-coder:1.5b`, `gemma2:2b`, `devstral-small-2:latest` — this is the task the whole fleet runs through.

**Files:**
- Modify: `docs/superpowers/notes/2026-07-29-fleet-benchmarks.md` (all measurement sections)
- Possibly modify: `scripts/ollama_ask.py` + `tests/test_ollama_ask.py` (ONLY if the quality gate demands a preference reorder — see Step 5)

**Interfaces:**
- Consumes: Task 3's working resolution (e2e also pins via `OLLAMA_SKILLS_MODEL`, so it can run even if resolution had a bug — but Task 3 must be merged first so the dogfood loop works).
- Produces: the notes file's `Cold load`, `E2E <model>`, `devstral-small-2 probe`, and `Quality-gate verdicts` sections — Task 5 fills every doc number from these, mechanically.

- [ ] **Step 1: Unload everything, then measure qwen2.5-coder:1.5b**

Run (PowerShell):
```powershell
ollama ps                                # note anything loaded
ollama stop devstral-small-2:latest      # for each loaded model shown by ps
ollama stop gemma2:2b
ollama stop qwen2.5-coder:1.5b
python scripts/ollama_ask.py warmup --task general --model qwen2.5-coder:1.5b
```
The script prints `warmed <model> in <N>s` — that N **is** the cold-load number. Record it under `## Cold load`.

- [ ] **Step 2: Full e2e for qwen2.5-coder:1.5b**

Run (PowerShell):
```powershell
$env:RUN_OLLAMA_E2E = "1"; $env:OLLAMA_SKILLS_MODEL = "qwen2.5-coder:1.5b"
python tests/e2e_local.py
Remove-Item Env:RUN_OLLAMA_E2E; Remove-Item Env:OLLAMA_SKILLS_MODEL
```
Copy every `E2E <name> <seconds>s` line verbatim under `## E2E qwen2.5-coder:1.5b`. If the script exits 1, record which step failed and why (this feeds Step 5); rerun once to separate flake from pattern.

- [ ] **Step 3: Repeat for gemma2:2b**

`ollama stop qwen2.5-coder:1.5b`, confirm with `ollama ps`, then repeat Steps 1–2 with `gemma2:2b` (cold load under `## Cold load`, steps under `## E2E gemma2:2b`).

- [ ] **Step 4: The devstral probe — record what happens, no scripted conclusion**

Run (PowerShell; stop gemma2 first, confirm `ollama ps` empty):
```powershell
$sw = [System.Diagnostics.Stopwatch]::StartNew()
python scripts/ollama_ask.py ask "Reply with the single word: OK" --model devstral-small-2:latest --timeout 120 --stall-seconds 120
$sw.Stop(); "exit=$LASTEXITCODE wall=$($sw.Elapsed.TotalSeconds)s"
ollama stop devstral-small-2:latest
```
Record exit code + wall time under `## devstral-small-2 probe`, plus current free RAM (`python scripts/ollama_ask.py health` prints it). Exit 5 → the docs row reads "did not answer within 120 s at <free> GB free (15.2 GB model)". Exit 0 → the row reports the real latency, and add a note that the RAM gate is about *predicted* fit with `--model` as the informed override (Task 5 copies this wording).

- [ ] **Step 5: Quality-gate verdicts**

For each small model, write PASS/FAIL per e2e step under `## Quality-gate verdicts`. FAIL = the step failed output validation (exit 6 — e.g. `commit-msg` Conventional-Commit check, `draft-command` JSON check) on **both** the original run and the single rerun. Any FAIL → that model is demoted below the passing alternative in that task's `PREFERENCES` list (edit `scripts/ollama_ask.py`, update any test the reorder breaks, rerun `python -m unittest discover -s tests`, and record the decision + reasoning in the verdicts section). No FAILs → write "all pass, lists unchanged".

- [ ] **Step 6: DOGFOOD LOOP**

`<paths>` = `docs/superpowers/notes/2026-07-29-fleet-benchmarks.md` (+ `scripts/ollama_ask.py tests/test_ollama_ask.py` if Step 5 reordered).

---

### Task 5: Doc + config refresh from the notes file (spec §6 rewrite list)

**Executor model: haiku** (explicit — do not inherit; every number is copied from the notes file, every text block is given below). **Local models exercised:** `qwen2.5-coder:1.5b` in the dogfood loop.

**Files:**
- Modify: `README.md`, `config/.ollama-skills.example.json`, `docs/ADVANCED.md`, `.github/workflows/e2e.yml`, `tests/e2e_local.py` (docstring), `tests/e2e_k8s.py` (docstring), `docs/DESIGN.md` (§11 lists + "Models used during development" lines only), `CLAUDE.md`
- Read: `docs/superpowers/notes/2026-07-29-fleet-benchmarks.md`

**Interfaces:**
- Consumes: notes-file sections from Task 4; final `PREFERENCES` from Task 1/4.
- Produces: shipped docs that name only the current fleet; Task 7 greps to verify.

- [ ] **Step 1: README — "Models used during development" section**

Replace the section's three model bullets (`qwen3:8b`, `llama3.2:1b`, `devstral:latest`) with:

```markdown
- `qwen2.5-coder:1.5b` — coder pick: commit messages, shell drafts, small code
- `gemma2:2b` — general + summarize pick (the one small model that satisfies
  every task's preference list by itself)
- `devstral-small-2:latest` — 15 GB; auto-detect **skips it on this machine**
  (bigger than free RAM — the `models` command shows the skip and why). On a
  machine where it fits, it is auto-picked for code tasks.
```

Keep the surrounding "If you clone this, model choice is yours" paragraph unchanged.

- [ ] **Step 2: README — measured-speed table**

Replace the table (keep the intro sentence and the paragraph after it, updating the model names in that paragraph if they appear). Fill `<...>` cells from the notes file's `Cold load` numbers and `E2E <name>` lines; use `—` where a step wasn't measured for that model:

```markdown
| Operation | qwen2.5-coder:1.5b | gemma2:2b |
|---|---|---|
| Model load (cold start) | <cold load> | <cold load> |
| `ask` (tiny prompt, warm) | <E2E ask> | <E2E ask> |
| `commit-msg` (small staged change) | <E2E commit-msg> | — |
| `draft-command` | <E2E draft-command> | — |
| `summarize` (single-shot, ~3k chars) | — | <E2E summarize> |
| `devstral-small-2:latest` (15.2 GB) | <probe row wording from notes §probe> | |
```

- [ ] **Step 3: Example config**

Replace `config/.ollama-skills.example.json` wholesale with:

```json
{
  "host": "http://localhost:11434",
  "keep_alive": "30m",
  "stall_seconds": 90,
  "total_timeout_seconds": 480,
  "max_input_chars": 2500,
  "tasks": {
    "commit":    { "model": "qwen2.5-coder:1.5b", "max_tokens": 96,  "temperature": 0.4 },
    "shell":     { "model": "qwen2.5-coder:1.5b", "max_tokens": 192, "temperature": 0.0 },
    "code":      { "model": "qwen2.5-coder:1.5b", "max_tokens": 512, "temperature": 0.2 },
    "general":   { "model": "gemma2:2b",          "max_tokens": 256, "temperature": 0.3 },
    "summarize": { "model": "gemma2:2b",          "max_tokens": 200, "temperature": 0.2, "num_ctx": 2048 }
  }
}
```

- [ ] **Step 4: e2e workflow + docstrings**

- `.github/workflows/e2e.yml`: `ollama pull llama3.2:1b` → `ollama pull qwen2.5-coder:1.5b`; `OLLAMA_SKILLS_MODEL: "llama3.2:1b"` → `OLLAMA_SKILLS_MODEL: "qwen2.5-coder:1.5b"`.
- `tests/e2e_local.py` docstring: `OLLAMA_SKILLS_MODEL=llama3.2:1b` → `OLLAMA_SKILLS_MODEL=qwen2.5-coder:1.5b`.
- `tests/e2e_k8s.py` docstring: `and llama3.2:1b pulled` → `and gemma2:2b pulled` (it exercises `summarize`, which now resolves to gemma2).

- [ ] **Step 5: ADVANCED hardware row**

In `docs/ADVANCED.md`'s per-hardware table, "No GPU, 16 GB RAM" row: replace ``(`llama3.2:1b`, `llama3.2:3b`, `qwen3:4b`)`` with ``(`qwen2.5-coder:1.5b` and `gemma2:2b` — both measured here — or `llama3.2:3b`)``. Rest of the row unchanged.

- [ ] **Step 6: DESIGN §11 lists + dev-models line (current claims only — touch nothing else in DESIGN)**

Replace the five `- \`code\`:` … `- \`summarize\`:` bullet lines to match Task 1's `PREFERENCES` exactly:

```markdown
- `code`: qwen3-coder, qwen2.5-coder (any), devstral, deepseek-coder, codegemma,
  qwen3, llama3.1, gemma3, gemma2, llama3.2, mistral
- `commit`: qwen2.5-coder, llama3.1, llama3.2, qwen3, gemma3, gemma2
- `shell`: qwen3, llama3.1, llama3.2, qwen2.5, gemma3, gemma2
- `general`: qwen3, llama3.1, gemma3, gemma2, llama3.2, mistral, qwen2.5-coder (floor)
- `summarize`: llama3.2, gemma3, gemma2, qwen2.5, llama3.1, mistral, qwen3 (last resort)
```

Replace the "**Models used during development** (this machine): …" sentence with: `**Models used during development** (this machine, since 2026-07-28): qwen2.5-coder:1.5b, gemma2:2b, and devstral-small-2:latest (15 GB — auto-detect skips it; larger than free RAM). The original fleet is recorded in §3.`

- [ ] **Step 7: CLAUDE.md sentence**

In CLAUDE.md's "Model resolution" paragraph, after the sentence about auto-detect never falling back to an arbitrary model, insert: `Auto-detect also skips any candidate whose file size exceeds free RAM (best-effort — it stands down when either number is unknown; explicit pins bypass the gate, and `models` prints what was skipped and why).`

- [ ] **Step 8: Verify**

Run: `python scripts/validate_repo.py` (checks the example config keys), then
`git grep -n -e "qwen3:8b" -e "llama3.2:1b" -e "devstral:latest" -- README.md config docs/ADVANCED.md .github/workflows/e2e.yml tests/e2e_local.py tests/e2e_k8s.py CLAUDE.md`
Expected: validator all OK; grep returns **no matches**.

- [ ] **Step 9: DOGFOOD LOOP**

`<paths>` = `README.md config/.ollama-skills.example.json docs/ADVANCED.md .github/workflows/e2e.yml tests/e2e_local.py tests/e2e_k8s.py docs/DESIGN.md CLAUDE.md docs/superpowers/notes/2026-07-29-fleet-benchmarks.md` (the notes file carries Task 4's pending tally line)

---

### Task 6: History-preserving DESIGN append + CHANGELOG (spec §6 append list)

**Executor model: sonnet** (explicit — do not inherit; extends records without falsifying them). **Local models exercised:** `qwen2.5-coder:1.5b` in the dogfood loop.

**Files:**
- Modify: `docs/DESIGN.md` (append only), `CHANGELOG.md` (new top section only)
- Read: `docs/superpowers/notes/2026-07-29-fleet-benchmarks.md`

**Interfaces:**
- Consumes: Task 4's notes numbers; Task 5 must be done (so DESIGN's current-claims lines are already updated and this task only appends).
- Produces: DESIGN decision D14 + dated measurement subsection; CHANGELOG `[Unreleased]`.

- [ ] **Step 1: Label the original measured table and append the new one**

In DESIGN §3, change the line `Machine: Windows 11, 16 GB RAM (~6 GB free), **no GPU**, Ollama 0.32.1.` to `Machine: Windows 11, 16 GB RAM (~6 GB free), **no GPU**, Ollama 0.32.1 — measured 2026-07-18; kept as the record behind D3/D10/D12.` Then append AFTER the existing table and its design-rules list (do not touch either):

```markdown
### 3.1 Measured facts — fleet of 2026-07-28 (Ollama 0.32.4, ~7.5 GB free)

The machine's fleet changed; the table above stays as the original record. New
measurements (raw data: benchmark notes, 2026-07-29):

| Test | Result |
|---|---|
| `qwen2.5-coder:1.5b` cold load | <from notes §Cold load> |
| `gemma2:2b` cold load | <from notes §Cold load> |
| `qwen2.5-coder:1.5b` commit-msg (e2e) | <from notes §E2E> |
| `gemma2:2b` summarize single-shot (e2e) | <from notes §E2E> |
| `devstral-small-2:latest` (15.2 GB) probe, 120 s cap | <from notes §probe> |
```

- [ ] **Step 2: Append decision D14**

Add one row to the end of DESIGN's decision table (D13 is last today):

```markdown
| D14 | Auto-detect skips models larger than free RAM; flag/env/config picks bypass the gate; the gate stands down when sizes or free RAM are unknown. The size>free test is a deliberately lenient proxy (no KV-cache estimate) — same basis as the `health` warning | devstral-small-2 (15.2 GB) matched the code list on a ~7.5 GB-free machine and would burn up to 480 s before exit 5; `health` warned but resolution was blind (2026-07-28) |
```

- [ ] **Step 3: CHANGELOG `[Unreleased]`**

Insert above the `## [0.2.0]` heading:

```markdown
## [Unreleased]

### Added

- Free-RAM gate in model auto-detect: candidates larger than free RAM are skipped;
  `models` reports each skip (`skipped <model> for <tasks> (<size> > <free> free RAM)`)
  and `--json` gains a `skipped` array. Explicit `--model` / env / config picks are
  never gated. When every matching candidate is gated, the task fails with exit 4
  naming the model, its size, and free RAM.

### Changed

- Preference lists: `gemma2` joins every task list directly after `gemma3`; the gemma
  family joins `shell`; `qwen2.5-coder` becomes the last-resort floor for `general`.
- Example config, README fleet + measured-speed tables, e2e default model, and the
  two pull hints now match the 2026-07 development fleet (`qwen2.5-coder:1.5b`,
  `gemma2:2b`, `devstral-small-2:latest`).
```

(Leave `plugin.json` at 0.2.0 — the release that ships this becomes 0.3.0, set then.)

- [ ] **Step 4: Verify + DOGFOOD LOOP**

Run: `python scripts/validate_repo.py` (all OK). `<paths>` = `docs/DESIGN.md CHANGELOG.md docs/superpowers/notes/2026-07-29-fleet-benchmarks.md` (pending tally line)

---

### Task 7: Final verification (spec §10)

**Executor model: sonnet** (explicit — do not inherit). **Local models exercised:** `qwen2.5-coder:1.5b`, `gemma2:2b` (live resolution + warmup); `qwen2.5-coder:1.5b` for the final tally commit.

**Files:**
- Modify: `docs/superpowers/notes/2026-07-29-fleet-benchmarks.md` (final tally lines + verification transcript)

**Interfaces:**
- Consumes: everything above.
- Produces: the pass/fail verdict; this task's own commit carries the last dogfood tally lines.

- [ ] **Step 1: Suite + validator** — `python -m unittest discover -s tests -v` (63 OK) and `python scripts/validate_repo.py` (all OK).
- [ ] **Step 2: Live resolution** — `python scripts/ollama_ask.py models`: five resolved rows, zero `none`, `general` = `gemma2:2b`, `summarize` = `gemma2:2b`, and a `skipped devstral-small-2:latest for code` line.
- [ ] **Step 3: The previously broken path** — `python scripts/ollama_ask.py warmup --task general` exits 0 (was exit 4 before this work).
- [ ] **Step 4: Grep sweep** — rerun Task 5 Step 8's `git grep`; expected no matches. (CHANGELOG, RESEARCH, skill-tests, DESIGN historical sections, and `scripts/ollama_ask.py`'s summarize comment are exempt records — they are not in the grep's path list.)
- [ ] **Step 5: E2E evidence** — confirm the notes file contains both models' full `E2E` step lists with all steps passing (or a documented quality-gate demotion from Task 4 Step 5), plus the probe record.
- [ ] **Step 6: Dogfood evidence (spec §10.7)** — `git log --oneline origin/draft..HEAD` should be empty or near-empty after the final push; every T0–T6 commit message follows Conventional Commits; the notes tally has one line per commit marked used-as-is / edited / replaced / model-failed; no commit used `--allow-protected` (verify: `git log --format=%H origin/draft | head` commits all exist on the remote branch, and the loop transcript shows plain `commit-push` calls).
- [ ] **Step 7: Report** — summarize verification results + the dogfood tally stats (how many drafts used as-is / edited / replaced / failed) back to the user. Then DOGFOOD LOOP one last time: `<paths>` = `docs/superpowers/notes/2026-07-29-fleet-benchmarks.md`.
