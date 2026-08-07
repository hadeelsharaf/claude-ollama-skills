---
name: ollama-code
description: Draft small, self-contained code (one function, one small file, boilerplate, a test) with a local Ollama model, then review and place it. Use when the user asks for a small offline code task or private code drafting.
---

# ollama-code — small code drafts, gated before they land

The local model drafts SMALL code. A draft lands only through its gate: apply it
unread when a test you wrote yourself covers it and the suite passes; review every
line otherwise. Big or cross-file work is your job, not the local model's.

The loop is ground -> draft -> judge.

## Script

Set `SCRIPT` = `${CLAUDE_PLUGIN_ROOT}/scripts/ollama_ask.py`
(manual install: `$OLLAMA_SKILLS_HOME/scripts/ollama_ask.py`).
Use `python` on Windows, `python3` on macOS/Linux.

## Steps

1. **Size gate.** Good fit: one function, one small class, one small script or test,
   boilerplate — roughly 150 lines or less, no knowledge of other project files
   needed. Anything bigger, multi-file, or subtle: write it yourself and say why.
2. Write a short, precise spec (inputs, outputs, edge cases, language) to a temp
   file, then:
   `python "$SCRIPT" draft-code --spec-file <tempfile> --lang python`
   (`--lang javascript` also gets a syntax check when node is installed).
   Do not use `--out`: you review first, then place the code yourself (step 5).
3. **Apply/review gate.**
   - A test you wrote yourself already covers this change: apply the draft
     unread with Write/Edit, then run the suite. Green = done. Red = review
     the draft line by line (below) or write the code yourself.
   - No such test exists yet: write the failing test first, then apply and
     run the suite the same way — or, when a test is not practical here,
     review the draft line by line right now:
     - Does it do exactly what the spec says? Edge cases handled?
     - No secrets, no network calls, no file deletions the spec did not ask for.
     - Style matches the surrounding project.
4. Fix small problems yourself when you reviewed line by line.
5. Place the code with Write/Edit (if not already placed above), run the
   project's quick check (tests, linter, or at least import/compile).
6. Tell the user what the local model drafted — and whether a test verified it
   unread, or you reviewed and changed it. When the draft's fate is decided,
   record it on your next delegating call by adding
   `--outcome` `<used-as-is|edited|replaced|model-failed>` (add
   `--outcome-task <task>` if the next call is a different task); if no next
   call comes, run:
   `python "$SCRIPT" record-outcome <verdict> --task code`.

## Rules (do not skip)

Every draft is an UNTRUSTED DRAFT until its tier's gate passes.

1. The draft is an **UNTRUSTED DRAFT**. You review it, you fix it, you own it.
   Apply a draft unread only when a test you wrote yourself covers the change
   and the suite passes after applying; if the suite goes red, review the
   draft or write the code yourself. Otherwise, never paste it into the
   project unread.
2. The spec you send is the contract. If the draft ignores it, one retry with a
   sharper spec, then write the code yourself.
3. **Fallback rule:** exit 3/4/5/6 → write the code yourself right away and tell
   the user in one line why the local model was skipped.
4. Use only the commands and flags shown in this skill. If a flag is not documented
   here, it does not exist — do not invent one.

## Troubleshooting

Exit 6 means the draft failed the syntax check twice — write it yourself.
Slow on CPU is normal for code drafts (30 s – 3 min). Exit-code table: see the
`ollama-ask` skill.
