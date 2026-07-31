# ollama-docker — Dockerfile / Compose drafting (reference)

Loaded on the drafting branch only. The deny-list, grounding, and review
rules in SKILL.md still apply. The loop is ground -> draft -> judge.

Reuse the existing `draft-code` subcommand. Do NOT build a new drafting
command and do NOT use `ask` — `draft-code` already strips code fences, and
its `--out` refuses to overwrite an existing file (a built-in review gate).

`draft-code` has no `--system` flag (its system prompt is fixed and keyed by
`--lang`). So the domain "system prompt" rides at the TOP of the `--spec`
text as a terse, artifact-only preamble, and `--lang` selects the language:

```
python "$SCRIPT" draft-code --lang dockerfile --spec "<DOMAIN PREAMBLE>\n\n<user request + grounding facts>"
```

Use `--lang dockerfile` for a Dockerfile, `--lang yaml` for a compose file.

**DOMAIN PREAMBLE (fixed text):** "Output ONLY the file contents. No prose, no markdown,
no fences. Use a slim, version-pinned base image; a multi-stage build when it helps; a
non-root user; a .dockerignore-friendly layout; and a HEALTHCHECK when sensible. If the
request is unclear, pick the smallest safe default. Do not repeat a pattern that already
failed."

Print-and-review by default: `draft-code` prints the file, you review it, the user places
it (or `--out <newfile>`, which refuses to clobber). Never pipe a drafted
Dockerfile/compose straight into `docker build` / `docker compose up` unseen.

Ground the spec against real state first: read the working directory — any existing
Dockerfile, `docker-compose.yml`, and the language/manifest (`package.json`,
`requirements.txt`, `go.mod`, …), and run `docker compose config` if a compose file
exists. Feed those facts into `--spec` so the draft extends the real project.
