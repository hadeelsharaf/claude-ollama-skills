# Wayfinder tracker (local-markdown)

Planning artifacts for in-flight efforts. Convention:

- `map-*.md` — one map per effort (frontmatter `label: wayfinder:map`). The map is an index: destination, notes, decisions-so-far (links), fog ("Not yet specified"), and out-of-scope.
- `tickets/<id>-*.md` — child tickets. Frontmatter: `id`, `title`, `type` (research | prototype | grilling | task), `status` (open | closed), `assignee` (a name = claimed; empty = unclaimed), `blocked-by` (list of ticket ids).
- A ticket is **unblocked** when everything in `blocked-by` is closed. The **frontier** = open + unblocked + unclaimed.
- Resolutions are appended to the ticket under `## Resolution`, then `status: closed`, then one line added to the map's Decisions-so-far.
- `research/` — findings captured while resolving research tickets.

One ticket per session (research tickets excepted). Claim before working.
