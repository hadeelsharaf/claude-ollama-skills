---
id: T3
title: "Spec the summarize core subcommand"
type: grilling
status: open
assignee: ""
blocked-by: [T2]
---

## Question

Lock the CLI contract for `ollama_ask.py summarize`: input mode (stdin only, or
also run-a-command-itself like commit-msg does for privacy), tail/chunk defaults
(from T2), output shape (bullet summary? one-line verdict + bullets?), which task
profile/model it uses, exit codes, and how it degrades when input exceeds budget.
Decide with the user; record the exact flag list and defaults.
