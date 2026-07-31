---
name: ollama-code
description: Draft small, self-contained code (one function, one small file, boilerplate, a test) with a local Ollama model, then review and place it. Use when the user asks for a small offline code task or private code drafting.
---

# ollama-code — small code drafts, reviewed line by line

The local model drafts SMALL code. You review every line, fix small problems, and
only then write the file. Big or cross-file work is your job, not the local model's.

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
3. Review the draft line by line:
   - Does it do exactly what the spec says? Edge cases handled?
   - No secrets, no network calls, no file deletions the spec did not ask for.
   - Style matches the surrounding project.
4. Fix small problems yourself.
5. Place the code with Write/Edit, run the project's quick check
   (tests, linter, or at least import/compile).
6. Tell the user what the local model drafted and what you changed.

## Rules (do not skip)

1. The draft is an **UNTRUSTED DRAFT**. You review it, you fix it, you own it.
   Never paste it into the project unread.
2. The spec you send is the contract. If the draft ignores it, one retry with a
   sharper spec, then write the code yourself.
3. **Fallback rule:** exit 3/4/5/6 → write the code yourself right away and tell
   the user in one line why the local model was skipped.
4. Use only the flags shown in this skill; do not invent flags.

## Troubleshooting

Exit 6 means the draft failed the syntax check twice — write it yourself.
Slow on CPU is normal for code drafts (30 s – 3 min). Exit-code table: see the
`ollama-ask` skill.
