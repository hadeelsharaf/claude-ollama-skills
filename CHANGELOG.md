# Changelog

All notable changes to this project are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [0.1.0] - 2026-07-18

### Added

- Core CLI `scripts/ollama_ask.py` (Python 3.9+, standard library only):
  `health`, `models`, `warmup`, `ask`, `commit-msg`, `draft-command`, `draft-code`, `fix-lint`.
- Five skills: `ollama-ask`, `ollama-commit`, `ollama-precommit`, `ollama-shell`, `ollama-code`.
- Three subagents on haiku: `ollama-coder`, `ollama-git`, `ollama-ops`.
- Plugin + marketplace manifests (installable with two commands).
- CLAUDE.md routing template.
- Docs: design, plan, research, advanced options, security notes.
- Unit tests with a fake Ollama server; opt-in real e2e script.
- GitHub Actions: unit tests (Ubuntu + Windows), repo validation, opt-in e2e.
