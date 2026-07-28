# Advanced options

Everything here is optional. The default setup (plugin + the bundled script) needs
none of it.

## 1. Manual install (without the plugin system)

1. Clone this repo anywhere, for example `~/tools/claude-ollama-skills`.
2. Copy each folder from `skills/` into `~/.claude/skills/` (personal) or your
   project's `.claude/skills/` (shared with the team).
3. Copy the files from `agents/` into `~/.claude/agents/` or `.claude/agents/`.
4. Set the environment variable `OLLAMA_SKILLS_HOME` to the clone path.
   The skills use it to find `scripts/ollama_ask.py` when `${CLAUDE_PLUGIN_ROOT}`
   does not exist (it only exists for plugin installs).

## 2. MCP server instead of the CLI script

An MCP server is the better fit when you want the SAME Ollama access from several
clients (Claude Desktop, Cursor, other MCP apps), or multi-model conversations.
Trade-offs: its tool schemas use context tokens in every session, and many servers
default to short timeouts that CPU inference blows through.

Vetted options (active, documented, tested as of mid-2026):

- `rawveg/ollama-mcp` — 14 tools, high test coverage, ships a companion skill.
- `BeehiveInnovations/zen-mcp-server` (renamed "PAL MCP") — multi-model
  orchestration (chat, codereview, planner, consensus) across cloud + local.

Example project-scope `.mcp.json` for a generic stdio server:

```json
{
  "mcpServers": {
    "ollama": {
      "command": "npx",
      "args": ["-y", "@rawveg/ollama-mcp"],
      "env": { "OLLAMA_HOST": "http://localhost:11434" }
    }
  }
}
```

Check the server's own README for its real package name and timeout settings before
trusting it with long CPU generations.

## 3. Fully offline Claude Code (no cloud at all)

Since Ollama v0.14, Ollama speaks the Anthropic API natively. That means Claude Code
itself can run against a local model — no internet, and also none of Claude's cloud
intelligence. Expect much weaker planning and tool use; this is a different trade,
not an upgrade.

```powershell
$env:ANTHROPIC_BASE_URL = "http://localhost:11434"
$env:ANTHROPIC_AUTH_TOKEN = "ollama"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL = "qwen2.5-coder:1.5b"   # your pick
claude
```

Or in one step, if your Ollama version has it: `ollama launch claude`.

## 4. The child-worker pattern (local model with a full tool loop)

The scripts in this repo are text-in/text-out. If you want the LOCAL model to run a
full agentic loop (read files, edit, run commands) while your main session stays on
Claude, spawn a child Claude Code process pointed at Ollama:

```powershell
$env:ANTHROPIC_BASE_URL = "http://localhost:11434"; $env:ANTHROPIC_AUTH_TOKEN = "ollama"
claude -p "run the linter and fix trivial findings" --permission-mode default
```

Run it in a separate terminal (or via the Bash tool) so the env vars never touch
your main session. Treat everything it did as untrusted and review the diff.
This pattern is powerful and rough — test on a throwaway branch first.

## 5. Warm the model when a session starts (opt-in)

Loading a model takes ~30 s on CPU. A SessionStart hook can hide that — at the cost
of RAM in EVERY session, including ones that never use the local model. That is why
it ships disabled. If you want it, add to your `settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"$OLLAMA_SKILLS_HOME/scripts/ollama_ask.py\" warmup --task general --quiet"
          }
        ]
      }
    ]
  }
}
```

## 6. Tuning for your hardware

| Machine | Advice |
|---|---|
| No GPU, 16 GB RAM | Use a 1–4 B model (`qwen2.5-coder:1.5b`, `gemma2:2b`, `llama3.2:3b`). Keep `max_input_chars` at 2500. An 8 B model works but costs 30 s load + slow prefill; 14 B+ will thrash or time out. |
| No GPU, 32 GB RAM | 7–8 B models are the sweet spot (`qwen2.5-coder:7b`, `llama3.1:8b`). |
| GPU ≥ 8 GB VRAM | 7–14 B models fly. Raise `max_input_chars` (8000+) and `max_tokens`. |
| GPU ≥ 16 GB VRAM | `qwen2.5-coder:14b` or MoE coders; you can raise budgets a lot. |

Never run two local models at the same time on CPU — they fight for RAM and both
crawl (measured on the dev machine: everything timed out).
