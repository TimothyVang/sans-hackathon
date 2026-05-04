# AGENTS.md

This file is for Codex-compatible coding agents. `CLAUDE.md` remains the authoritative project instruction file; read it first and treat this file as the Codex adapter layer.

## Operating Mode

- The primary SANS judge/demo interface is Claude Code via `scripts/find-evil` or `claude` from the repo root.
- Codex compatibility is developer/operator support for the same repo and the same MCP servers, not a separate product path.
- Use the existing narrow typed MCP surface only: `findevil-mcp` and `findevil-agent-mcp`.
- Do not add generic MCP defaults such as filesystem, git, browser, Docker, Kubernetes, GitHub, fetch, or shell tools.

## Required Context

Before investigating evidence or changing investigation behavior, read these files in order:

1. `CLAUDE.md`
2. `agent-config/SOUL.md`
3. `agent-config/AGENTS.md`
4. `agent-config/PLAYBOOK.md`
5. `agent-config/TOOLS.md`
6. `agent-config/MEMORY.md`
7. `agent-config/HEARTBEAT.md`
8. `agent-config/JUDGING.md`

## MCP Surface

The canonical MCP config is `.mcp.json`:

- `findevil-mcp`: Rust stdio MCP server, 13 typed DFIR tools.
- `findevil-agent-mcp`: Python stdio MCP server, 11 crypto/ACH/memory/ACP tools.
- Expected total: 24 tools.

SIFT mode uses `.mcp.json.sift` through SSH into the SIFT VM. Do not rewrite user-level Codex or Claude config unless explicitly asked.

## Hard Rules

- No `execute_shell`, shell passthrough, arbitrary command MCP, or tool that accepts raw shell commands.
- Do not reintroduce `ots_stamp`, `ots_verify`, OpenTimestamps, or Bitcoin attestation runtime behavior.
- Evidence is read-only. Never mutate original evidence.
- Every Finding must cite `tool_call_id`.
- Execution claims require at least two artifact classes.
- Treat Hayabusa, Sigma, YARA, capa, and anomaly matches as triage leads unless corroborated.
- Do not describe limited coverage as clean, cleared, disproven, or absent. Use `NO_EVIL` only with the documented verdict semantics and state coverage limits.
- Do not assert attribution.
- Keep secrets out of the repo and out of generated output.

## Codex MCP Setup

If your Codex build supports MCP stdio servers, configure it to launch the two existing servers from the repo root. See `docs/codex-compatibility.md` for TOML snippets and validation commands.

## Dashboard Command

This repo includes a Codex skill at `.agents/skills/dashboard`. In Codex, use the dashboard skill when the operator types `/dashboard`, asks for the dashboard, or wants the Codex cockpit. The skill starts the local web UI and opens `http://localhost:3000/codex`.

Manual fallback:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/codex-dashboard.ps1
```

## Validation Commands

Use the smallest relevant checks first:

```bash
python scripts/verdict-policy-smoke.py
ruff check .
ruff format --check .
uv run --directory services/agent_mcp python -m pytest -q
cargo test --workspace --locked
```

For MCP smoke tests:

```bash
python scripts/rust-mcp-smoke.py --real-evidence
uv run --directory services/agent_mcp python ../../scripts/agent-mcp-smoke.py
```

If a validation command is not feasible in the current environment, state why and run the closest component-level replacement.
