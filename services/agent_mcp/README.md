# findevil-agent-mcp

Python MCP server exposing the Find Evil! crypto custody (M2) and
ACH judge/correlator (M4) stacks as typed tools for Claude Code.

Per **Amendment A2** (Claude Code as primary interface) the agent
runtime is no longer a custom Python service — Claude Code itself
is the orchestrator. This package wraps the M2 + M4 modules so
they are reachable as MCP tools alongside the typed Rust DFIR
surface in `services/mcp/`.

## Boot

```bash
uv run --directory services/agent_mcp python -m findevil_agent_mcp.server
```

In normal use you do not invoke this directly — the repo-root
`.mcp.json` registers both MCP servers and Claude Code spawns them
on session start.

## Tools

| Tool | Wraps | Purpose |
|---|---|---|
| `audit_append` | `AuditLog.append` | Append one event to the hash-chained audit log. |
| `audit_verify` | `AuditLog.verify` | Replay the chain; surface any break. |
| `manifest_finalize` | `build_manifest` + `write_manifest` | Build, sign, and write `run.manifest.json`. |
| `manifest_verify` | `verify_manifest` | Offline verify (chain + Merkle root + sig presence). |
| `ots_stamp` | `crypto.ots.stamp` | Submit manifest to OpenTimestamps. |
| `ots_verify` | `crypto.ots.verify` | Verify the calendar/Bitcoin proof. |
| `verify_finding` | `verifier.reverify_finding` | Re-run the cited tool call; approve/reject/downgrade. |
| `detect_contradictions` | `contradiction.detect_contradictions` | Pairwise scan Pool A vs Pool B. |
| `judge_findings` | `judge.judge_findings` | Credibility-weighted merge of pool findings. |
| `correlate_findings` | `correlator.correlate` | SOUL.md cross-artifact rule enforcement. |

Each tool has a Pydantic input model with `extra="forbid"` (deny
unknown fields) and a Pydantic output model. JSON schemas are
emitted to the MCP client at `list_tools` time.

## Tests

```bash
uv run --directory services/agent_mcp pytest
```
