---
id: T6
title: "Spec the ollama-git-history (git historian) skill"
type: grilling
status: open
assignee: ""
blocked-by: []
---

## Question

The user added this: "list git history by branch as needed." Pin the actual scope
with them: list vs summarize (plain `git log --oneline` needs no model; local-model
value is digesting ranges: "what changed on draft this week", per-author activity,
release-note drafts), which git commands feed it, input budgets (git log with
--stat? patches never?), output shape, and whether history data may leave the
machine (it should not — same privacy design as commit-msg). Record the exact
skill steps.
