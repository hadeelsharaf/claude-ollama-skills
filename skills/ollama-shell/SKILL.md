---
name: ollama-shell
description: Turn a plain-words chore into a shell command with a local Ollama model, then safety-check and run it. Use when the user asks for simple file or system chores (copy, move, clean, zip, list) drafted by the local model.
argument-hint: "<task in plain words>"
---

# ollama-shell — drafted commands, checked by you

The local model turns plain words into a command. You are the safety gate. The
command runs only after YOUR check and the normal permission prompt.

The loop is ground -> draft -> judge.

## Script

Set `SCRIPT` = `${CLAUDE_PLUGIN_ROOT}/scripts/ollama_ask.py`
(manual install: `$OLLAMA_SKILLS_HOME/scripts/ollama_ask.py`).
Use `python` on Windows, `python3` on macOS/Linux.

## Steps

1. `python "$SCRIPT" draft-command "<the task in plain words>"`
   (add `--shell bash` or `--shell powershell` to override the OS default).
2. Parse the JSON: `command`, `explanation`, `caution`.
3. **Safety check.** If the script prints classification: read-only, you may
   run the draft without review. Any other draft gets your full review
   against the task and the deny list before it runs. The model's own
   `caution` field does NOT count; models often say "none" for dangerous
   commands.
4. If the script printed classification: read-only, run the draft without
   review. Any other draft: Read DENYLIST.md in this skill's folder first,
   then review the draft - the deny-list check against that file, then the
   scope check (touches only what the user named) - before running.
   (plugin: `${CLAUDE_PLUGIN_ROOT}/skills/ollama-shell/DENYLIST.md`;
   manual: `$OLLAMA_SKILLS_HOME/skills/ollama-shell/DENYLIST.md`)
5. Show the user the command and the one-line explanation, then run it through the
   normal permission prompt. Never chain it with other commands.
6. Return the command's real output to the user. When the draft's fate is
   decided, record it:
   `python "$SCRIPT" record-outcome <used-as-is|edited|replaced|model-failed> --task shell`.

## Rules (do not skip)

Every draft is an UNTRUSTED DRAFT until its tier's gate passes.

1. The drafted command is an **UNTRUSTED DRAFT** from a small model. It can be
   wrong, too broad, or subtly destructive while looking clean.
2. The user's words are the spec; the draft is just a guess at it. When they
   disagree, follow the user's words.
3. **Fallback rule:** exit 3/4/5/6 → write the command yourself right away and tell
   the user in one line why the local model was skipped. One retry max.
4. Use only the commands and flags shown in this skill. If a flag is not documented
   here, it does not exist — do not invent one.

## Troubleshooting

Exit-code table: see the `ollama-ask` skill. JSON parse trouble is exit 6 — the
script already retried once; write the command yourself.
