# Fleet benchmark + dogfood notes — 2026-07-29

Machine: Windows 11, 16 GB RAM, no GPU, Ollama 0.32.4.
Raw data for the doc refresh (plan Task 5) and the dogfood evidence (spec §10.7).

## Cold load

## E2E qwen2.5-coder:1.5b

## E2E gemma2:2b

## devstral-small-2 probe

## Quality-gate verdicts

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
