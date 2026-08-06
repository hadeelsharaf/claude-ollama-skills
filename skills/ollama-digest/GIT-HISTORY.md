# Git history digests — command forms and the patch ban

Two sub-paths; pick by what the user asks for.

**List sub-path (default when unclear) — no model call.** "Show the history,"
"list commits," "what's on X that main doesn't have": run `git log --oneline`
(add `-n`, a branch, or `A..B`). Show the output exactly as git printed it.
Default to the latest 50 commits when no count/range is given and say so in
one line. This text is short and meant to be read — no summarizing, no
rewording.

**Digest sub-path — for asks that need judgment** ("what changed this week,"
"how busy was each author," "draft release notes"):

1. Read-only git only. Allowed: `git branch --list` / `-a`, `git log --oneline`,
   `git shortlog -sn <range>`, `git log --pretty=format:"%h %ad %an %s" --date=short <range>`,
   `git log --stat <range>` (only if the text still fits the input budget), `git show --stat <commit>`.
   Never run `git log -p`, `--patch`, `-U<n>`, `--word-diff`, `--full-diff`, or
   plain `git diff` — those print real code changes. This skill shows only
   history facts — who, when, which file, one-line subject. It never shows patch content.
2. If the ask needs an exact number (commits per author), get it first with
   `git shortlog -sn <range>` — deterministic — and put that number in the fed
   text. Never let the model count; small models miscount.
3. Optionally add ONE steering line at the top of the text (e.g. "Context:
   write 3 short release notes from the commits below").
4. Pipe to summarize over stdin, always with `--no-verdict` (on git input the
   VERDICT line invites invented error/warning counts — observed live 2026-07-29):
   `{ git shortlog -sn <range>; git log --pretty=format:"%h %ad %an %s" --date=short <range>; } | python "$SCRIPT" summarize --kind git --no-verdict`
5. Every bullet in the digest must point at something really in the input — a
   real hash, author, or date. A name, date, or count not in the fed text is a
   guess; fix it or drop it.

**Privacy rule (history):** the compact log text goes only to the local Ollama
model over stdin; only the digest comes back into your context. The plain
`--oneline` list is fine to see directly (short subjects, no file content, no
patches) — full patches are what the privacy rule protects, and this skill
never touches them. This skill never changes the repo: no `checkout`, `reset`,
`rebase`, `merge`, `commit`, `push`, or branch/tag deletes.
