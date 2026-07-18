---
name: ollama-shell
description: Turn a plain-words chore into a shell command using a local Ollama model, then safety-check and run it. Use when the user asks for simple file or system chores (copy, move, clean, zip, list, run a script) and wants the local model to draft the command. Requires local Ollama and Python 3.9+.
argument-hint: "<task in plain words>"
---

# ollama-shell — drafted commands, checked by you

The local model turns plain words into a command. You are the safety gate. The
command runs only after YOUR check and the normal permission prompt.

## Script

Set `SCRIPT` = `${CLAUDE_PLUGIN_ROOT}/scripts/ollama_ask.py`
(manual install: `$OLLAMA_SKILLS_HOME/scripts/ollama_ask.py`).
Use `python` on Windows, `python3` on macOS/Linux.

## Steps

1. `python "$SCRIPT" draft-command "<the task in plain words>"`
   (add `--shell bash` or `--shell powershell` to override the OS default).
2. Parse the JSON: `command`, `explanation`, `caution`.
3. **Safety check — run through this list yourself.** The model's own `caution`
   field does NOT count; models often say "none" for dangerous commands.
4. Scope check: does the command touch ONLY what the user named? Wildcards or
   parent folders beyond the target = rewrite it yourself, narrower.
5. Show the user the command and the one-line explanation, then run it through the
   normal permission prompt. Never chain it with other commands.
6. Return the command's real output to the user.

## Deny-list — rewrite or refuse, never run as-is

- Recursive delete outside the folder the user named (`rm -rf`, `Remove-Item -Recurse -Force` on `~`, `/`, `$env:USERPROFILE`, `AppData`, wildcards at high levels)
- `git clean -fdx` / `-fd` (silently deletes untracked files — configs, .env, notes)
- Disk or partition operations (`format`, `diskpart`, `mkfs`, `dd`)
- Registry edits, `shutdown`, `reboot`, service stop/start
- Piping a download into a shell (`curl ... | sh`, `iwr ... | iex`)
- Reading or sending credential files (`.ssh`, `.aws`, tokens, browser profiles)
- `git push --force` to a shared branch, `git commit --no-verify`
- Mass permission changes (`chmod -R 777`, `icacls /reset /T`)
- Anything with `sudo` the user did not explicitly request

A command on this list is not "probably fine". Rewrite a narrow, safe version
yourself, or ask the user.

## Rules (do not skip)

1. The drafted command is an **UNTRUSTED DRAFT** from a small model. It can be
   wrong, too broad, or subtly destructive while looking clean.
2. The user's words are the spec; the draft is just a guess at it. When they
   disagree, follow the user's words.
3. **Fallback rule:** exit 3/4/5/6 → write the command yourself right away and say
   the local model was skipped and why. One retry max.
4. Use only the flags shown in this skill. If you need a flag that is not
   documented, it does not exist — do not invent one.

## Troubleshooting

Exit-code table: see the `ollama-ask` skill. JSON parse trouble is exit 6 — the
script already retried once; write the command yourself.
