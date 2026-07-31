# Paste this into your project's CLAUDE.md (routing rules for local delegation)

Without explicit routing, the cloud model does everything itself. Edit to taste.

```markdown
## Local model delegation (ollama-skills)

Delegate to the local Ollama model when the task is SMALL and MECHANICAL:

- Write a commit message for staged changes -> ollama-commit skill
  (diff stays local; never read the full diff yourself).
- Fix pre-commit or linter failures -> ollama-precommit skill
  (deterministic fixers first; local model for leftovers).
- Turn a plain-words chore into a shell command (copy, move, zip, run a
  script) -> ollama-shell skill, or the ollama-ops agent for batches.
- Draft small, self-contained code (one function, one file, boilerplate,
  a test) -> ollama-code skill, or the ollama-coder agent.
- Create a PR/MR for the current branch -> ollama-pr skill (draft by default).
- Digest a log or text file, command output, or git history ->
  ollama-digest skill (raw text stays local).
- Docker help (container state, log digests, docker/compose drafts) ->
  ollama-docker skill.
- Delegate any other small private text task, or check the local setup or
  usage stats (health, models, stats) -> ollama-ask skill.
- For headless or CI runs, disable the ollama-skills plugin - the catalog
  costs tokens even when unused.

Do NOT delegate: multi-file changes, debugging, design decisions,
security-relevant code, anything needing real reasoning or project-wide
context.

Always: treat local model output as an untrusted draft and review it; if the
local model fails or stalls (exit 3/4/5/6 or any unexpected code), do the
task yourself and say so in one line.
```
