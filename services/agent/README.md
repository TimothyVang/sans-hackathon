# findevil-agent

Python runtime for the Find Evil! Product. Hosts the LangGraph ACH graph, FastAPI SSE bus, crypto chain-of-custody layer (M2), MCP widget server (M3 progressive enhancement), and CLI.

**Authoritative design:** `docs/superpowers/specs/2026-04-25-the-product-design.md`.
**Credential rules:** `docs/superpowers/specs/2026-04-23-amendment-option-b-claude-code-mode.md`.
**Invariants:** `CLAUDE.md` §"Non-negotiable invariants".

## Status

| Component | Status |
|---|---|
| Package scaffold + pinned deps | ✅ |
| `config.resolve_credentials()` (3 modes — Amendment A1) | ✅ |
| `events.py` AgentEvent union (11 variants) | ✅ |
| Per-case memory resolver | ✅ |
| `mcp_client.py` (stdio subprocess manager for the Rust MCP server) | ⏳ Week 2 Task B4 |
| `crypto/signer.py` sigstore-based per-call signing (M2) | ⏳ Week 2 Task B5 |
| `crypto/audit_log.py` hash-chained JSONL writer | ⏳ Week 2 Task B6 |
| `crypto/ots.py` OpenTimestamps Bitcoin anchor | ⏳ Week 3 Task B7 |
| Specialist subagents (disk/memory/log analysts) | ⏳ Week 3-4 Task B8 |
| ACH pools (persistence / exfil) + judge + contradiction | ⏳ Week 4 Tasks B9-B12 |
| `supervisor.py` scatter-gather + PlanProposed | ⏳ Week 4 Task B14 |
| LangGraph StateGraph wire-up + SqliteSaver | ⏳ Week 4 Task B15 |
| FastAPI SSE endpoints | ⏳ Week 5 Task B16 |
| `cli.py` (find-evil CLI entry) | ⏳ Week 5 Task B17 |

## Quick start

```sh
# From the repo root:
cd services/agent
uv sync
uv run pytest -xvs
```

## Credential resolver (Amendment A1)

`resolve_credentials()` detects in this order:

1. `CLAUDE_CODE_OAUTH_TOKEN` env var (generated via `claude setup-token` — inference-only; judge-friendly).
2. `~/.claude/` interactive session (after `claude auth login`).
3. `ANTHROPIC_API_KEY` env var (direct metered API from console.anthropic.com).

Raises `CredentialsNotAvailableError` with a multi-line message listing all three options if none are found. The CLI catches this and prints the error at startup.

## AgentEvent union (Spec #2 §5)

The 11 variants:

- `ToolCallStart`, `ToolCallOutput` — tool lifecycle
- `AgentMessage` — specialist/supervisor/judge/verifier/correlator reasoning
- `Finding` (requires `tool_call_id`), `VerifierAction` — findings + vetos
- `ChainUpdate` — merkle_root + leaf_count + ots_pending
- `RunVerdict` — final verdict + confidence + manifest path
- `PlanProposed`, `PlanApproved` — Plan Mode gate
- `HypothesisUpdate` — MITRE board drive
- `ContradictionFound` — emits BEFORE the judge reconciles; the architectural moat

Every event is Pydantic-frozen, `extra="forbid"`. `event_id` auto-fills as UUID4; `ts` auto-fills as UTC ISO-8601 with trailing `Z`. TypeScript types for `apps/web/lib/events.ts` are generated via `pydantic-to-typescript` (follow-up task).

## For swarm workers

- New Pydantic model → add to `findevil_agent/events.py`, extend the `AgentEvent` discriminated union, add roundtrip test in `tests/test_events.py`.
- New config constant → put it in `findevil_agent/config.py`; export via `__all__`.
- LangGraph node → put it in `findevil_agent/nodes/<name>.py` (directory will land with Task B14).
- Specialist subagent → put it in `findevil_agent/specialists/<name>.py` (Task B8).

## Pinned dependencies

See `pyproject.toml`. Do not upgrade without a spec amendment.

Key pins:
- `langgraph >=1.0,<2.0`
- `langgraph-checkpoint-sqlite >=2.0,<3.0`  *(Product uses Sqlite; Swarm uses Postgres)*
- `anthropic >=0.45,<1.0`
- `sigstore ==3.*`
- `opentimestamps-client ==0.7.2`
- `fastapi >=0.115,<1.0`
- `pydantic >=2.7,<3.0`
- `mitreattack-python >=5.4,<6.0`
