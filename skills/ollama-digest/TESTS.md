# ollama-digest / TESTS.md — failing test runs

Read this when the ask is to run a test suite or digest its output. The raw
runner output is what you are delegating away: you see the counts header, the
per-failure digest, and the coverage line — never the run itself.

Workflow hook: whenever a workflow step (a TDD red run, a
verification-before-completion gate, a plan's test step) requires running a
suite, this pipe IS that step — the counts header is the evidence.

## Pipe forms

Set `SCRIPT` as in SKILL.md. Always merge stderr (`2>&1`) — runners print
failures there.

- pytest: `pytest -q 2>&1 | python "$SCRIPT" summarize --kind test`
- unittest: `python -m unittest discover -s tests 2>&1 | python "$SCRIPT" summarize --kind test`
- a saved run: `python "$SCRIPT" summarize --kind test --file <captured.txt>`

## What comes back

1. A counts header the script parsed from the runner's own summary line —
   `tests: 233 passed, 12 failed, 3 errors (parsed from pytest output)`. The
   model never counts. Treat this line as your verification evidence; an
   all-green run makes no model call at all.
2. One block per failure: test id, error type, the assertion line verbatim,
   and a suspect file:line. Fields the script could not find verbatim in the
   input are marked `(unverified)` — trust those least.
3. A counts-only `coverage:` line on stderr. Judge it first: `blocks=` must be
   N/N and `dropped=0`. A `missing from input` or `[chunk ... dropped]` marker
   means incomplete coverage — narrow the run or fall back; never fill the gap
   by reading the raw output.

## Privacy rules (both hold at once)

- You never read the raw test-runner output: do not run the suite unpiped to
  look at it, and no Read/cat/Get-Content on a captured run file.
- After the digest, you may re-run at most one named failing test to verify a
  fix (`pytest tests/test_x.py::test_y`, or
  `python -m unittest tests.test_x.Class.test_y`); that single-test output is
  the only runner output allowed into your context.

## Rules

- Each failure block is an **UNTRUSTED DRAFT**: open the named file at the
  named line before acting on it, and prefer the one-named-retest above over
  trusting the draft.
- `--verdict` is ignored for `--kind test`; the counts header is the verdict.
- Exit 6 saying the input was not recognized → the runner is not
  pytest/unittest; digest with `--kind log` instead. Other exits: SKILL.md
  fallback rule applies (do it yourself, say why in one line).
- Record the draft's fate per SKILL.md rule 5 (`--outcome` on the next call,
  or `record-outcome <verdict> --task summarize`).

## Free rider — PR threads and CI logs (no new flags)

- `gh pr view <n> --comments 2>&1 | python "$SCRIPT" summarize --kind text --no-verdict`
- `gh run view <id> --log 2>&1 | python "$SCRIPT" summarize --kind log`

Same stance: digest the thread or CI log; do not paste it into your context.
