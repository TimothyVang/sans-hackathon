# Amendment A2 — Claude Code as Primary Interface

> **Status: SHIPPED.** The custom Python orchestrator (`graph.py`, `api.py`, `cli.py`, `supervisor.py`, `specialists/`) was dropped; Claude Code is the orchestrator. `services/agent_mcp/` shipped as the Python MCP wrapper around M2 + M4. `.mcp.json` at repo root auto-spawns both MCP servers. The L0 `amendment-a2-guard` GHA job fails CI if any of the dropped modules reappears. Live entry points: `scripts/find-evil`, `scripts/find-evil-auto`, `scripts/find-evil-sift`.

**Date:** 2026-04-25
**Status:** Active — supersedes affected sections of Spec #2 (The Product)
**Scope:** Product runtime + entry points + UI + Python agent service composition
**Rationale:** Direct Agent Extension via Claude Code is SANS rules §1 ("the fastest path to a working submission"). Combining it with Custom MCP Server (rules §2) lets us claim two of the four supported patterns simultaneously while shrinking remaining work by ~30%.

---

## 1. Decision

The Product's primary interface is **Claude Code invoked in the SIFT VM**. Claude Code talks to two MCP servers:

1. **`findevil-mcp` (Rust, `services/mcp/`)** — typed DFIR tool surface (case_open, evtx_query, plus 9 more Rust tools).
2. **`findevil-agent-mcp` (Python, `services/agent_mcp/`)** — wraps the M2 crypto + M4 ACH stacks as MCP tools.

A `.mcp.json` at the repo root registers both servers; Claude Code auto-discovers them on session start.

The Next.js SPA (`apps/web/`) and MCP Apps widgets (`apps/mcp-widgets/`) are **deferred** to a week-7 polish bonus — not on the critical path. They can be added if time allows; the submission ships without them.

---

## 2. Deltas from Spec #2

### 2.1 Removed from the critical path

| Module | Removed because |
|---|---|
| `services/agent/findevil_agent/graph.py` | Claude Code IS the LangGraph orchestrator |
| `services/agent/findevil_agent/api.py` (FastAPI + SSE) | Claude Code's terminal IS the streaming UX |
| `services/agent/findevil_agent/cli.py` (`find-evil` CLI) | `claude-code` IS the CLI |
| `services/agent/findevil_agent/supervisor.py` | Claude Code main agent IS the supervisor |
| `services/agent/findevil_agent/specialists/` | Claude Code subagents (`CLAUDE_CODE_FORK_SUBAGENT=1`) replace per-class specialists |
| `apps/web/` Next.js SPA | Deferred — bonus, not required |
| `apps/mcp-widgets/` | Deferred — bonus |

The deps in `services/agent/pyproject.toml` shrink accordingly:

- **Removed:** `langgraph`, `langgraph-checkpoint-sqlite`, `fastapi`, `uvicorn[standard]`, `sse-starlette`.
- **Kept:** `anthropic`, `pydantic`, `pydantic-to-typescript`, `sigstore`, `opentimestamps-client`, `duckdb`, `mitreattack-python`, `structlog`, `httpx`. Plus `mcp` (the Anthropic MCP Python SDK) — newly added.

### 2.2 Added by the pivot

**`services/agent_mcp/` — Python MCP server wrapping the existing M2/M4 stacks:**

```
services/agent_mcp/
├── pyproject.toml                 # mcp SDK + dep on findevil-agent for the wrapped logic
├── findevil_agent_mcp/
│   ├── __init__.py
│   ├── server.py                  # MCP stdio entry point; registers all tools
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── audit_append.py        # wraps AuditLog.append
│   │   ├── audit_verify.py        # wraps AuditLog.verify
│   │   ├── manifest_finalize.py   # wraps build_manifest + write_manifest
│   │   ├── manifest_verify.py     # wraps verify_manifest
│   │   ├── ots_stamp.py           # wraps crypto.ots.stamp
│   │   ├── ots_verify.py          # wraps crypto.ots.verify
│   │   ├── verify_finding.py      # wraps verifier.reverify_finding
│   │   ├── detect_contradictions.py  # wraps contradiction.detect_contradictions
│   │   ├── judge_findings.py      # wraps judge.judge_findings
│   │   └── correlate_findings.py  # wraps correlator.correlate
└── tests/
    └── test_server.py             # boots server, calls each tool, checks shape
```

Each tool module:
- Defines a Pydantic Input model (deny_unknown_fields).
- Defines a Pydantic Output model.
- Exports an async handler.
- The server registers all handlers on startup.

**`.mcp.json` (repo root):**

```json
{
  "mcpServers": {
    "findevil-mcp": {
      "type": "stdio",
      "command": "cargo",
      "args": ["run", "--release", "-p", "findevil-mcp", "--quiet"],
      "cwd": "."
    },
    "findevil-agent-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "services/agent_mcp", "python", "-m", "findevil_agent_mcp.server"],
      "cwd": "."
    }
  }
}
```

Both servers boot when Claude Code starts; the agent picks tools by name from either.

**`scripts/find-evil`** — thin convenience wrapper, NOT a custom CLI:

```bash
#!/usr/bin/env bash
# scripts/find-evil — convenience launcher for the SANS Find Evil! agent.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec claude-code . "$@"
```

The judge runs either `scripts/find-evil` OR `claude-code .` directly — both are equivalent.

**Updated `CLAUDE.md` (extension, not rewrite):**
- Add a top-level "Agent investigation prompt" section that orients Claude Code toward the DFIR investigation flow when invoked in this repo.
- Reference SOUL.md / AGENTS.md / MEMORY.md / HEARTBEAT.md as MUST-READ at session start.
- Document the two MCP servers and which tools live where.

### 2.3 Demo video pivot

Original beat map (Spec #2 §10) had the browser open at T+45s. Under A2 the demo is **terminal-only**:

```
T+00s  $ scripts/find-evil
       Claude Code session starts; reads CLAUDE.md + agent-config/*
       Greeting + "drop a case path"

T+05s  > investigate fixtures/nist-hacking-case/SCHARDT.001
       Claude calls case_open MCP tool; SHA-256 + uuid case_id displayed

T+15s  First [confirmed · Hayabusa · sha256:abcd…] line in terminal
       (same chip format, just plain text)

T+25s  Two parallel forked subagents (Pool A persistence, Pool B exfil)
       Output streams interleaved with [pool=A] / [pool=B] tags

T+45s  Claude calls detect_contradictions MCP tool → ContradictionFound
       printed inline; Claude pauses, asks "Trust A, Trust B, or Flag?"

T+1:30 Judge call (judge_findings MCP) returns merged set
       Verifier re-runs each tool call; vetoes one finding (sha drift)

T+3:30 Manifest finalized: ots_stamp + manifest_verify in terminal
       Path to run.manifest.json + .ots displayed

T+4:00 $ ots verify run.manifest.ots
       (judge runs offline verifier; sees "Bitcoin block 873421 confirmed")

T+5:00 End — RunVerdict line + path to artifacts.
```

Mirrors Rob Lee's 14:27 template even more closely (terminal-first, no GUI distraction).

### 2.4 Devpost README updates

Architectural-pattern declaration changes to:

> **Two SANS-supported patterns combined:**
> 1. **Direct Agent Extension (Claude Code)** (rules §1) — primary interface
> 2. **Custom MCP Server** (rules §2) — typed Rust DFIR surface (`findevil-mcp`) + crypto/ACH MCP server (`findevil-agent-mcp`)

The "Try it" section becomes:

```bash
git clone <REPO>
cd find-evil
scripts/install.sh        # detects Claude Code / OAuth token / API key
claude-code .
> investigate fixtures/nist-hacking-case/SCHARDT.001
```

---

## 3. No changes to

- `services/mcp/` (Rust MCP server) — same role, more tools to add.
- `services/swarm/` (build swarm) — unchanged.
- Sandbox (L0/L1/L2/L3) — unchanged.
- M2 + M4 internal modules — they already have stable Python APIs; the new Python MCP server is just a thin wrapper.
- CI workflows in `.github/workflows/` — unchanged.

---

## 4. Acceptance criteria for the pivot

- [ ] `services/agent_mcp/` package builds and tests green (`uv run pytest` in that directory).
- [ ] `.mcp.json` at repo root validates against MCP schema.
- [ ] `claude-code .` in the repo discovers both MCP servers on startup (verified by checking server list).
- [ ] An end-to-end smoke run against a synthetic fixture produces:
  - Valid `audit.jsonl` (verify chain offline).
  - Valid `run.manifest.json` (verify Merkle root).
  - At least one `ContradictionFound`-style event (parallel pool dispatch).
- [ ] No reference to `graph.py` / `api.py` / `cli.py` / `supervisor.py` / `apps/web/` in the critical-path docs.
- [ ] `services/agent/pyproject.toml` no longer lists fastapi / uvicorn / sse-starlette / langgraph.

---

## 5. Rollback path

If the pivot proves unworkable (e.g., the MCP Python SDK has blockers we hit late), revert is cheap:

1. The dropped modules (`graph.py` / `api.py` / `cli.py`) were never written under A2 — there's nothing to delete.
2. The `findevil-agent-mcp` server can be repurposed as the FastAPI backend by adding HTTP routes that wrap the same tool functions.
3. Re-add the dropped deps to `pyproject.toml`.

Rollback is ~1 day. Not zero, but cheap enough that committing to the pivot is safe.

---

## 6. Decision log entry

**2026-04-25, user directive (option B from a 4-choice prompt):** pivot to Claude Code as the primary interface; keep M2 + M4 Python stacks but expose them as MCP tools; defer Next.js SPA + MCP Apps widgets to week-7 polish bonus. Amendment A2 captures the deltas. Specs #1-#4 remain authoritative for everything A2 doesn't override.
