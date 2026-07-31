# Paste this into your project's CLAUDE.md (routing rules for local delegation)

Research shows one thing clearly: without explicit routing rules in CLAUDE.md,
the cloud model just does everything itself. Paste the block below (edit to taste).

```markdown
## Local model delegation (ollama-skills)

Delegate to the local Ollama model when the task is SMALL and MECHANICAL:

- Commit message for staged changes → use the ollama-commit skill
  (keeps the diff on this machine; never read the full diff yourself).
- Pre-commit or linter failures → use the ollama-precommit skill
  (deterministic fixers first; local model only for simple leftovers).
- Simple file/system chores (copy, move, zip, run a script) → use the
  ollama-shell skill, or ollama-ops for batches.
- Small self-contained code (one function, one small file, boilerplate, a test)
  → use the ollama-code skill, or the ollama-coder agent in the background.
- Opening a PR/MR for the current branch → use the ollama-pr skill (drafted
  description, draft PR by default).
- Summarizing a log/text file or git history → use the ollama-digest skill
  (stays local).
- Other small private text work, or checking the local model setup/models
  → use the ollama-ask skill.
- For headless or CI runs, disable the ollama-skills plugin — the catalog costs tokens even when unused.

Do NOT delegate: multi-file changes, debugging, design decisions, security-relevant
code, anything needing real reasoning or project-wide context.

Always: treat local model output as an untrusted draft and review it; if the local
model fails or stalls (exit 3/4/5/6 or any unexpected code), do the task yourself
and say so in one line.
```
