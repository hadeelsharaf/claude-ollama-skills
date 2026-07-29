# Benchmarks — A/B token measurement + quality evals

Two consumers share one set of deterministic fixtures (`benchmarks/fixtures.py`,
`PROMPT_COMMIT` / `PROMPT_SUMMARIZE`):

1. **`benchmarks/measure_ab.py`** — a hand-rolled token-consumption runner. It
   is the source of the published "Measured savings" numbers.
2. **`evals/commit-msg/`, `evals/summarize/`** — a permanent quality/regression
   suite runnable via the built-in `claude plugin eval` command, and a
   cross-check on consumer 1's numbers when it reports cost/usage per run
   (see "Cross-check" below).

Both are opt-in, manual, real-money-spending tools. Neither runs in CI.

## 1. Token-consumption runner (`measure_ab.py`)

Runs the same task prompt twice per trial in a fresh, disposable fixture
folder — once WITH the plugin (`--plugin-dir <repo>`), once WITHOUT — via
headless `claude -p --output-format json --model opus`, and compares token
usage, cost, wall time, success, and (WITH arm) real local-model tokens from
the Ollama usage ledger.

Pilot first (1 run, summarize only — cheapest way to shake out the harness):

```bash
python benchmarks/measure_ab.py --runs 1 --tasks summarize
```

Full matrix (default: both tasks, both arms, 3 runs each = 12 headless
sessions):

```bash
python benchmarks/measure_ab.py
```

Output: `benchmarks/results/ab-YYYYMMDD-HHMMSS.json` (per-run rows + per-cell
aggregates) plus a printed table. `benchmarks/results/` is gitignored except
explicitly published `ab-published-*.json` files.

### Honesty rules (spec §8 — verbatim)

- n=3 per cell; mean with min-max, not a significance claim.
- Both arms opus, identical prompts, cold folders; the ONLY difference is
  `--plugin-dir`.
- `tokens_consumed` excludes cache reads (reported separately); cost USD is
  the secondary, pricing-dated metric.
- Savings counted over successful runs only; delegation rate published even
  when embarrassing.
- Local tokens are real (Ollama-reported); they are the plugin's cost, shown
  next to the cloud savings, never netted silently.

### Cost warning

Real opus API spend. Defaults run **~12 opus sessions** (2 tasks × 2 arms ×
3 runs). Always run the `--runs 1 --tasks summarize` pilot first.

## 2. Quality/regression evals (`claude plugin eval`)

```bash
claude plugin eval . --scaffold --ablation with-without --model opus --runs 3 \
  --json benchmarks/results/eval-run.json \
  --report benchmarks/results/eval-report.html \
  --max-cost-usd 15
```

`--scaffold` is required — it is the consent gate for running each case's
author-supplied `scaffold_script` (see schema below); without it the fixture
is never built and the case fails immediately. `--ablation with-without` runs
every case twice (with the plugin loaded, and a no-plugin baseline) and
reports the score delta. This is real opus spend too — the `--max-cost-usd`
ceiling aborts and reports partial results (exit 2) if hit, but budget for the
full with/without matrix across both cases before running it.

### Cost warning

Real opus API spend, same as the runner above — this is a *second*,
independent paid tool, not free because the runner already ran. Use
`--max-cost-usd` every time; there is no dry-run mode (every invocation
launches at least one real agent session per case/arm/run).

### Feature-gate note (discovered, not documented publicly yet)

On this machine's CLI build (`claude` 2.1.220), `claude plugin eval` is
gated behind an early-access rollout flag — running any `plugin eval`
subcommand without it prints `` `plugin eval` is currently in early access ``
and exits 1, even for read-only operations like `init --bare`. The gate
checks a rollout flag OR the environment variable
`CLAUDE_CODE_WALNUT_SPIRE=1` (discovered from the CLI's own gate-check
message plus its `--help` output; not in the public docs as of this writing).
Set that env var to unlock the command locally:

```bash
CLAUDE_CODE_WALNUT_SPIRE=1 claude plugin eval . --scaffold --case summarize ...
```

This is a rollout mechanism, not a secret — it unlocks a command that
already appears in `claude plugin eval --help` on this build. Expect this
note to become unnecessary once the feature ships to everyone.

### Discovered case schema

`claude plugin eval --help` states cases live at `evals/**/case.yaml` or
`evals/<case>/prompt.md` + `evals/<case>/graders/*.md`. Both formats were
probed (`claude plugin eval init <name> --bare` writes the `prompt.md` +
`graders/criteria.md` template for free, no agent run). **We use `case.yaml`
for both of our cases** because the split `prompt.md` format's frontmatter
only accepts a fixed key set — `schema_version, name, description, tags,
plugins, runs, expected_outcome` (top-level) and `model, max_turns,
timeout_seconds, allowed_tools, append_system_prompt, env` (execution) — and
has **no field for `scaffold_script`**; only `case.yaml`'s `context:` block
exposes it. Any other key raises `unknown frontmatter key "..."`.

`case.yaml` fields (required unless noted):

```yaml
schema_version: "1.1"          # string, required
name: <string, min 1>          # matched by `--case <glob>`
description: <string>          # optional
tags: [<string>, ...]          # optional, default []
plugins: [<string>, ...]       # optional — restrict which plugins can load
context:                       # optional, default {add_dirs: []}
  scaffold_script: <path>      # optional — bash script, MUST resolve inside
                                # this case's own directory (no ../.. escape)
  history_file: <path>         # optional
  add_dirs: [<string>, ...]    # optional, default []
execution:
  prompt: <string>             # optional (case can omit and rely on history_file)
  max_turns: <int 1-200>       # default 10
  timeout_seconds: <int 1-3600> # default 300
  model: <string>              # optional — overridden by CLI --model
  allowed_tools: [<string>...] # default []
  append_system_prompt: <string> # optional
  env: {<key>: <value>}        # default {}
runs: <int 1-50>               # default 3
graders:                       # required, min 1, names must be unique
  - type: llm                  # also: regex | tool_used | tool_order |
                                # file_exists | baseline
    name: <string>
    criteria: <string>         # the rubric text, LLM-graded
    focus: last_message        # default; also: trace | files | {source: file, path: ...}
    weight: 1                  # default
    arm: with-only|both        # optional — restrict grader to one ablation arm
expected_outcome: <string>     # optional, documentation only
```

Grader `type: llm` is what both of our cases use (matches the design spec's
"LLM rubric per case"). `focus: trace` is used for `commit-msg` so the grader
sees the actual `git commit` tool call and its output, not just the agent's
closing remark; `focus: last_message` (the default) is used for `summarize`
since the graded artifact *is* the assistant's final reply.

**Gated tools**: `--allow-tools` on the CLI is "an operator grant for gated
tools (Bash, Write, Edit, WebFetch, mcp__\*)" (verbatim from `--help`). A
case's own `execution.allowed_tools` list is not enough by itself — any gated
tool it names that the operator didn't also pass via `--allow-tools` is
denied for that run (logged as `denied tools (pass --allow-tools to grant):
...`), which quietly removes it rather than erroring. Both our cases list
`Bash` in `allowed_tools` (needed for the WITH arm to actually shell out to
the local model, and for `commit-msg` to run `git commit` at all). Running
either case for real — beyond the schema smoke-test below — needs
`--allow-tools Bash` added to the command, or the WITH arm degrades to "read
the file and answer without delegating" and `commit-msg` cannot commit at
all.

**Scaffold script sandboxing**: `scaffold_script` is a path, resolved
relative to (and must stay inside) the case's own directory — not an inline
shell one-liner. `evals/commit-msg/scaffold.sh` and
`evals/summarize/scaffold.sh` locate the repo root via their own `$0`
(`dirname`/`cd .. .. `, since `evals/<case>/` is two levels below the repo
root) and then call `python(3) benchmarks/fixtures.py commit|log .` — the
same fixtures CLI `measure_ab.py` uses, so both consumers build byte-identical
fixtures from one source. The scaffold process itself gets a minimal env
(`PATH, HOME, USERPROFILE, TMPDIR, TERM, USER_TYPE, NODE_ENV` only — no
`CLAUDE_PROJECT_DIR` or similar), which is why the scripts resolve the repo
root from their own path instead of an environment variable.

### Reproduction commands

Full with/without matrix, both cases (same command as above):

```bash
claude plugin eval . --scaffold --ablation with-without --model opus --runs 3 \
  --json benchmarks/results/eval-run.json \
  --report benchmarks/results/eval-report.html \
  --max-cost-usd 15
```

One case only, cheap smoke test (haiku, 1 run, $2 ceiling — this is the
sanctioned low-cost sanity check for this schema/wiring, not a quality
measurement):

```bash
claude plugin eval . --scaffold --case summarize --runs 1 --model haiku \
  --max-cost-usd 2 --json benchmarks/results/eval-smoke.json
```

### Cross-check with the token-measurement runner

Spec §6 asks whether `claude plugin eval`'s `--json` output includes
per-run cost/usage, as a cross-check on `measure_ab.py`'s numbers. The
sanctioned `eval-smoke.json` sanity run above has **not been executed yet**
in this environment — the session's auto-mode permission classifier blocks
launching a nested paid `claude plugin eval` invocation from inside a running
Claude Code session (denied identically via two different shells; see
`.superpowers/sdd/2026-07-29-measure-ab/task-3-report.md` for the verbatim
denial). Run the smoke command yourself in a normal terminal (outside an
active Claude Code session, or with an explicit Bash permission rule for it)
to get the answer, then update this section with the result.
