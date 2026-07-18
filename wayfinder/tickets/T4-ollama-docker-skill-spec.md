---
id: T4
title: "Spec the ollama-docker skill"
type: grilling
status: open
assignee: ""
blocked-by: [T1]
---

## Question

Lock the ollama-docker SKILL.md content: the read-verb list (ps, logs, inspect,
images, stats, compose ps ...), the mutate-verb list requiring explicit user words
(stop, restart, rm, compose up/down ...), deny-list additions (system prune,
volume rm, network rm, rm -f on running containers ...), the log-summarize flow
(docker logs → summarize), and the Dockerfile/compose drafting flow (reuse
draft-code with domain system prompt?). Include trigger wording for the
description. Feed the copy/avoid list from T1.
