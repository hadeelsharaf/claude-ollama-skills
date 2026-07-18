# Research notes (condensed)

Collected 2026-07-18 while designing this project. Three research passes: prior art,
task patterns, and official Claude Code formats. Kept short here; the design
decisions they produced are in [DESIGN.md](DESIGN.md) §10.

## Prior art — Claude + local Ollama delegation

| Project | Approach | Takeaway |
|---|---|---|
| [claude-coworker-model](https://github.com/imkunal007219/claude-coworker-model) | CLI wrappers + CLAUDE.md routing, deliberately no MCP | Most-starred delegation project; routing rules in CLAUDE.md are what make delegation happen |
| [claude-ollama-agents](https://github.com/PratikHotchandani22/claude-ollama-agents) | subagents + Python helper | stream output so slow local inference shows progress |
| [teams-ollama](https://github.com/bobbymac/teams-ollama) | plugin + child `claude -p` at Ollama | local model gets a full tool loop; build a fallback to a cloud model |
| [zen-mcp-server / PAL](https://github.com/beehiveinnovations/zen-mcp-server) | MCP multi-model orchestration | the mature MCP route; tool schemas cost context tokens |
| [OllamaClaude](https://github.com/Jadael/OllamaClaude) | MCP, file-aware tools | pass file PATHS not contents — that is where token savings live |
| [rawveg/ollama-mcp](https://github.com/rawveg/ollama-mcp) | generic Ollama MCP | well tested; default 30 s timeouts hurt CPU inference |
| [claude-code-router](https://github.com/musistudio/claude-code-router) | proxy, routes Claude Code itself | session-wide replacement, not per-task delegation |
| [Ollama ↔ Claude Code official](https://docs.ollama.com/integrations/claude-code) | native Anthropic API since Ollama 0.14 | `ANTHROPIC_BASE_URL=http://localhost:11434` just works |
| [opencommit](https://github.com/di-sukharev/opencommit) / [aicommits](https://github.com/Nutlope/aicommits) / [aicommit2](https://github.com/tak-bro/aicommit2) | commit-message CLIs with Ollama support | prompt + truncation + sanitize patterns copied below |

Why we chose CLI wrappers over MCP: no schema token cost, no server to babysit,
timeouts fully ours (critical: CPU inference regularly needs minutes), works in CI.
MCP stays documented in [ADVANCED.md](ADVANCED.md) for multi-client users.

## Patterns copied into the script (with sources)

1. "Your entire response will be passed directly into git commit" (aicommits) —
   telling the model its raw output is the artifact cuts preamble and fences.
2. Enumerate the closed set of allowed commit types in the prompt (opencommit).
3. Sanitize pipeline for one-liners: strip reasoning blocks → first line → strip
   quotes/trailing period → bounded retry (aicommits).
4. Diff budgeting: exclude lockfiles, cut context lines (`-U1`), cap per-file,
   hard total cap (opencommit / aicommit2 — shrunk further for CPU).
5. Disable thinking mode; an 18× speedup was reported for the same delegation
   pattern (sumguy.com local-workhorse writeup). We send `think:false` AND strip
   `<think>` blocks as a second guard.
6. Lint-fix loop shape (BitsAI-Fix, arXiv 2508.03487; aider lint loop): minimal
   context window, search/replace output, re-run the linter to verify, ≤3 rounds,
   one finding at a time. BitsAI needed a fine-tuned 32B for ~85% accuracy — an
   off-the-shelf small model must therefore be suggest-only.
7. NL→shell guardrails, in order of adoption (shell_gpt, llm-cmd, open-interpreter,
   Warp): show-first, edit-before-execute, per-step confirmation, static deny rules.
   Danger gating is STATIC — no serious tool asks the model to certify safety.
8. Sampling: temperature 0 for commands, ~0.4 for commit messages; never ask for
   content not derivable from the input (issue numbers get hallucinated).

## Model shortlist (≤14 B, as of mid-2026)

- Code: `qwen2.5-coder:14b` > `qwen2.5-coder:7b` > `qwen3:8b` > `phi-4:14b`
- Commit/diff summarization: `qwen2.5-coder:7b`, `llama3.1:8b`, `gemma3:4b/12b`,
  floor: `llama3.2:3b` (and `llama3.2:1b` for speed, verified in our e2e)
- Shell instruction-following: `qwen3:8b/14b`, `llama3.1:8b`, `qwen2.5:7b-instruct`
- Skip as outdated: codellama, granite-code, mistral:7b for code

These lists are encoded as the auto-detect preferences in `scripts/ollama_ask.py`
(`PREFERENCES`) — override any of it in config.

## Official format sources

- Skills: https://code.claude.com/docs/en/skills.md
- Subagents: https://code.claude.com/docs/en/sub-agents.md
- Plugins: https://code.claude.com/docs/en/plugins.md and plugins-reference.md
- Marketplaces: https://code.claude.com/docs/en/plugin-marketplaces.md
- MCP: https://code.claude.com/docs/en/mcp.md
