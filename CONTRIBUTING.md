# Contributing

Thanks for helping! This project is small on purpose. Please keep it that way.

## Ground rules

- **Standard library only.** No pip packages at runtime or in tests.
- **Simple English** in all docs. Short sentences. Common words.
- **Conventional Commits**: `feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`.
- Every behavior change needs a test in `tests/`.
- Skill frontmatter stays single-line `key: value` pairs (the validator depends on this).
- Safety rules are not optional: local model output stays an untrusted draft,
  and nothing may bypass Claude Code permission prompts.
- Releases: merge draft → main, bump plugin.json version, update CHANGELOG, tag ollama-skills--v<version> — pushes without a version bump never reach installed users.

## Before you open a PR

```bash
python -m unittest discover -s tests -v   # all green
python scripts/validate_repo.py           # all OK
```

Optional, with a local Ollama running:

```bash
RUN_OLLAMA_E2E=1 python tests/e2e_local.py
```

## Adding a new skill

1. Copy an existing folder under `skills/`.
2. Keep the three shared rules section ("Rules (do not skip)") word for word.
3. `description` must say what the skill does **and** when to use it ("Use when ...").
4. Run the validator.
5. If the skill adds a deny-list or any other safety wording, pin it with a test in
   `tests/test_ollama_ask.py` (copy a `test_denylist_covers_*` case). Those tests exist
   so a later reword cannot silently drop a guardrail.
