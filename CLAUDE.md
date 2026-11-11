# CLAUDE.md — Claude Code & Anthropic Agent Guide

@AGENTS.md

## Claude Code / Plugin Notes
- **MCP Config:** Automatically loaded from `.mcp.json` (`indian-investor-mcp` -> `python mcp_server.py`).
- **Plugin Manifest:** Located at `.claude-plugin/plugin.json`.
- **Skills:** Located in `skills/<skill-name>/SKILL.md` and indexed in `skills/registry.json`.
- **Specialized Subagent Prompts:** Located in `agents/` (`multibagger-hunter.md`, `forensic-auditor.md`, `earnings-reviewer.md`).
- **CLI Verification:** Run `python -m pytest test_agent.py -v` before finalizing edits.
