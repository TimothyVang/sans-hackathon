# Find Evil! — Architecture

**Devpost Required Component #3** — architecture diagram with trust boundaries, distinguishing prompt-based guardrails from architectural guardrails.

This document is the single-page visual summary judges reach first. Full detail lives in `docs/superpowers/specs/2026-04-25-the-product-design.md` (seven-layer product), `docs/superpowers/specs/2026-04-24-autonomous-build-swarm-design.md` (build swarm), and `docs/superpowers/specs/2026-04-23-amendment-option-b-claude-code-mode.md` (three credential modes).

---

## Architectural pattern claimed

Per SANS Find Evil! rules, submissions declare which of four supported patterns they implement. Our submission uses **two** primary patterns:

1. **Custom MCP Server** (rules §2) — a purpose-built Rust MCP server exposing 11 typed functions. The agent physically cannot run destructive commands because the server does not expose them. No `execute_shell` tool exists anywhere in the MCP surface.
2. **Multi-Agent Framework (LangGraph)** (rules §3) — the agent graph is decomposed into a supervisor, two competing-hypothesis worker pools, a judge node, a verifier, and a correlator. Each specialist has its own context window.

Both patterns are implemented together. The typed MCP server is called by every specialist agent in the LangGraph graph; no agent ever reaches a raw shell.

---

## Runtime architecture (the Product that judges run)

```mermaid
flowchart TB
    subgraph Trust0["**TRUST BOUNDARY 0** — Evidence Vault (read-only)"]
        Evidence["/evidence/case-id/<br/>Original .e01<br/>SHA-256 verified<br/>chmod 444 / mount -o ro"]
    end

    subgraph Trust1["**TRUST BOUNDARY 1** — SIFT Tool Subprocesses (unprivileged, sandboxed)"]
        Hayabusa[Hayabusa<br/>AGPL-3.0<br/>subprocess]
        Chainsaw[Chainsaw v2<br/>GPL-2.0<br/>subprocess]
        Volatility[Volatility3<br/>BSD-2<br/>subprocess]
        Velociraptor[Velociraptor<br/>AGPL-3.0<br/>gRPC subprocess]
        YARA[YARA + Forge Core<br/>subprocess scan]
    end

    subgraph Trust2["**TRUST BOUNDARY 2** — Typed Rust MCP Server (rmcp 0.16)"]
        MCP["11 typed tools<br/>NO execute_shell<br/>NO arbitrary command exec<br/>---<br/>case_open, mft_timeline,<br/>evtx_query, hayabusa_scan,<br/>vol_pslist, vol_malfind,<br/>yara_scan, usnjrnl_query,<br/>registry_query, prefetch_parse,<br/>vel_collect"]
        EvtxCrate["evtx crate<br/>MIT, in-process<br/>1600× python-evtx"]
        Merkle["rs_merkle 1.4.0<br/>append-only tree"]
        DuckDB["DuckDB 0.10<br/>L1 case store"]
    end

    subgraph Trust3["**TRUST BOUNDARY 3** — Agent Graph (LangGraph + M4 ACH pattern)"]
        Supervisor[Supervisor<br/>plan decomposition<br/>PlanProposed event]
        PoolA["Pool A<br/>PERSISTENCE-BIASED<br/>prior:<br/>Scheduled Tasks, Services,<br/>WMI, Run keys, IFEO, LOLBins"]
        PoolB["Pool B<br/>EXFIL-BIASED<br/>prior:<br/>net connections, staging dirs,<br/>certutil, bitsadmin, cloud sync,<br/>USB writes"]
        Contradiction["Contradiction<br/>Detection Node<br/>FIRES BEFORE JUDGE"]
        Judge["Judge Node<br/>credibility-weighted<br/>Estornell ICML 2025"]
        Verifier["Verifier<br/>re-executes tool_calls<br/>vetos uncited Findings"]
        Correlator["Correlator<br/>≥2 artifact classes<br/>for execution claims"]
    end

    subgraph Trust4["**TRUST BOUNDARY 4** — Agent Runtime + Crypto Custody"]
        FastAPI[FastAPI + SSE<br/>uvicorn :8080]
        SqliteSaver[LangGraph SqliteSaver<br/>resume after SIGKILL]
        Sigstore["sigstore 3.x<br/>keyless Fulcio signing<br/>Rekor transparency log"]
        OTS["OpenTimestamps 0.7.2<br/>Bitcoin anchor<br/>FRE 902(14) self-authenticating"]
        AuditJSONL["audit.jsonl<br/>hash-chained, append-only<br/>prev_hash per line"]
    end

    subgraph Trust5["**TRUST BOUNDARY 5** — Presentation (human-in-loop)"]
        NextJS[Next.js 15 SPA<br/>NarrativePane + EvidenceCanvas<br/>HypothesisBoard + VerdictCard<br/>ContradictionSurface]
        MCPWidgets[MCP App widgets SEP-1865<br/>timeline + heatmap + diff<br/>Claude Desktop / ChatGPT / Cursor]
        CLI[find-evil CLI<br/>serve / run / verify<br/>--unattended mode]
        Notify[notify-send + Slack webhook<br/>RunVerdict toast]
    end

    Human((Analyst /<br/>Judge)) -->|drop .e01| CLI
    Human -->|drop .e01| NextJS
    Human -->|prompt| MCPWidgets

    Evidence -.->|read-only mount| Trust1
    Trust1 -->|stdout parsed<br/>subprocess boundary| Trust2
    Trust2 -->|typed JSON-RPC<br/>stdio transport| Trust3

    Supervisor --> PoolA
    Supervisor --> PoolB
    PoolA --> Contradiction
    PoolB --> Contradiction
    Contradiction -->|ContradictionFound<br/>event emitted FIRST| Human
    Contradiction --> Judge
    Judge --> Verifier
    Verifier --> Correlator
    Correlator --> Trust4

    Trust3 --> Sigstore
    Trust2 -.->|Merkle leaf per<br/>tool call| Merkle
    Merkle --> OTS
    Sigstore --> AuditJSONL

    Trust4 --> NextJS
    Trust4 --> MCPWidgets
    Trust4 --> CLI
    Trust4 --> Notify

    Human -->|approve / reject<br/>plan + contradictions| Trust3

    style Trust0 fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px
    style Trust1 fill:#fff3e0,stroke:#ef6c00,stroke-width:2px
    style Trust2 fill:#e3f2fd,stroke:#1565c0,stroke-width:3px
    style Trust3 fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style Trust4 fill:#fffde7,stroke:#f9a825,stroke-width:3px
    style Trust5 fill:#fce4ec,stroke:#ad1457,stroke-width:2px
```

### Trust boundary legend

| # | Boundary | Enforcement mechanism | Type |
|---|---|---|---|
| 0 | Evidence vault | **Architectural:** `mount -o ro` + `chmod 444`; `inotifywait` in L3 asserts zero writes to `/evidence` | Filesystem-enforced |
| 1 | SIFT tool subprocesses | **Architectural:** unprivileged user (no root, no CAP_SYS_ADMIN), 120s wall-clock budget per call, cpulimit 50%, tmpfs `/tmp/case-<id>-work/`, binary allowlist (no curl/wget/nc) | OS-enforced |
| 2 | Typed Rust MCP Server | **Architectural:** type system forbids `execute_shell`; tool surface is fixed at compile time in `services/mcp/src/tools/mod.rs`; adding a shell passthrough would require a code change + PR + review | Compiler-enforced |
| 3 | Agent Graph | **Mixed:** agent system prompts (`agent-config/SOUL.md` — epistemic hierarchy, AGENTS.md — roles) are **prompt-based guardrails**; verifier veto (no Finding without `tool_call_id`) is **architectural** (Pydantic schema-level) | Mixed — prompt guards behavior, Pydantic guards data |
| 4 | Crypto Custody | **Architectural:** sigstore signing and Merkle root computation happen server-side before any finding is user-visible; OpenTimestamps anchoring is a subprocess call outside the agent's reach | Cryptographic |
| 5 | Presentation | **Architectural:** Next.js SSE bus is read-only from the frontend; analyst approval requires POST to `/cases/{id}/plan/approve` with session auth; `--unattended` mode auto-approves with `approved_by: "auto"` label in the audit log | Auth-enforced |

### Prompt-based vs architectural guardrails — explicit distinction

**Prompt-based guardrails (prompts that GUIDE behavior):**
- `agent-config/SOUL.md` epistemic hierarchy (CONFIRMED > INFERRED > HYPOTHESIS)
- `agent-config/AGENTS.md` specialist roles and tool scope
- `agent-config/MEMORY.md` DFIR artifact semantics (Amcache ≠ execution time, etc.)
- `agent-config/HEARTBEAT.md` canary string self-check every turn

These are **testable for bypass** in L3 golden runs — a prompt-injection fixture is included in `tests/acceptance/AC13_no_execute_shell.sh`. Prompt guardrails can fail; when they do, the architectural guardrails below must catch the fallout.

**Architectural guardrails (structural controls that PHYSICALLY PREVENT bad outcomes):**
- Read-only evidence mount (filesystem-enforced; even root can't mutate original .e01)
- Typed Rust MCP server with no `execute_shell` (compiler-enforced; adding shell passthrough requires a code change and PR review)
- Pydantic schema on `Finding` events requires `tool_call_id` (schema-enforced; unvalidated Findings can't exit the graph)
- LangGraph SqliteSaver checkpoints before every node (durability-enforced)
- sigstore signing of tool calls at the Rust MCP layer (agent cannot forge signatures)
- Merkle tree append-only at the Rust MCP layer (agent cannot backdate audit entries)
- OpenTimestamps subprocess anchoring (agent does not own the OTS calendar or the Bitcoin blockchain)
- FastAPI session auth on approval endpoints (agent cannot self-approve its own plan)

**Cisco `mcp-scanner` run pre-submission** asserts zero findings for `execute_shell` or equivalent arbitrary-execution patterns in `services/mcp/` — the architectural claim is machine-verified.

---

## Build-time architecture (Autonomous Build Swarm — INVISIBLE to judges)

```mermaid
flowchart LR
    subgraph Local["Developer laptop (Option B)"]
        Cron[jshchnz/claude-code-scheduler<br/>cron: 0 23 * * *]
        Supervisor[LangGraph Supervisor<br/>services/swarm/supervisor.py]
        Postgres[(PostgresSaver<br/>docker postgres:16-alpine<br/>DAG checkpoints)]
        SessionGuard[session_guard.py<br/>detects 429 / rate-limit<br/>halts cleanly, no retry]
    end

    subgraph Workers["Per-PR git worktrees + Claude CLI subagents"]
        direction TB
        Rust[Rust Worker<br/>.wt/wt-rust-id<br/>claude CLI subprocess]
        Python[Python Worker<br/>.wt/wt-py-id<br/>claude CLI subprocess]
        TS[TypeScript Worker<br/>.wt/wt-ts-id<br/>claude CLI subprocess]
    end

    subgraph Gate["Critic + L1 sandbox gate"]
        Critic[Critic subagent<br/>Sonnet<br/>structured CriticVerdict]
        L1[L1 sandbox<br/>cargo test / pytest / pnpm test]
    end

    subgraph GitHub["GitHub"]
        DraftPR[gh pr create --draft<br/>label: swarm-generated]
        Human((Human reviewer<br/>morning triage))
        Main[main branch<br/>merge after human review]
    end

    Cron --> Supervisor
    Supervisor <--> Postgres
    Supervisor --> SessionGuard
    SessionGuard -.->|CLAUDE_CODE_OAUTH_TOKEN<br/>or interactive session| Rust
    SessionGuard -.-> Python
    SessionGuard -.-> TS
    Supervisor --> Rust
    Supervisor --> Python
    Supervisor --> TS
    Rust --> Critic
    Python --> Critic
    TS --> Critic
    Rust --> L1
    Python --> L1
    TS --> L1
    Critic -->|APPROVE| DraftPR
    L1 -->|green| DraftPR
    DraftPR --> Human
    Human -->|merge| Main

    style Local fill:#e8eaf6,stroke:#3949ab,stroke-width:2px
    style Workers fill:#e0f7fa,stroke:#00838f,stroke-width:2px
    style Gate fill:#fff3e0,stroke:#ef6c00,stroke-width:2px
    style GitHub fill:#f1f8e9,stroke:#558b2f,stroke-width:2px
```

**Budget control (Option B, Amendment A1):**
- NO LiteLLM proxy, NO Anthropic API key required for the swarm
- Workers use the developer's Claude Code subscription via the local `claude` CLI
- `session_guard.py` detects rate-limit signals (HTTP 429, stderr patterns) and halts the supervisor cleanly
- Postgres checkpoint preserves state across halts — the next night's run resumes without re-dispatching already-completed PRs
- Per-subagent `--max-turns 40` and no-progress detector (3 zero-diff tool calls → kill) prevent individual workers from burning budget in loops

---

## Credential modes (Amendment A1)

The Product (what judges run) detects three credentials in priority order via `scripts/install.sh` and `services/agent/config.py resolve_credentials()`:

```mermaid
flowchart TD
    Start(["install.sh / resolve_credentials()"])
    Check1{CLAUDE_CODE_OAUTH_TOKEN<br/>env var set?}
    Check2{~/.claude/<br/>interactive session?}
    Check3{ANTHROPIC_API_KEY<br/>env var set?}

    Mode1[Mode 1:<br/>long-lived token<br/>from claude setup-token<br/>non-interactive<br/>inference-only scope]
    Mode2[Mode 2:<br/>interactive session<br/>from claude auth login<br/>dev/demo use]
    Mode3[Mode 3:<br/>direct API<br/>from console.anthropic.com<br/>metered, < $1/run]
    Fail["FAIL FAST<br/>error message lists<br/>all 3 options"]

    Start --> Check1
    Check1 -->|yes| Mode1
    Check1 -->|no| Check2
    Check2 -->|yes| Mode2
    Check2 -->|no| Check3
    Check3 -->|yes| Mode3
    Check3 -->|no| Fail

    style Mode1 fill:#c8e6c9
    style Mode2 fill:#c8e6c9
    style Mode3 fill:#c8e6c9
    style Fail fill:#ffcdd2
```

All three modes are **judge-valid**. Judges pick whichever they already have — none is required to build or submit.

---

## Data flow — a single investigation from `.e01` to verdict

1. Analyst drops `case.e01` into the Next.js SPA (or runs `find-evil run --case case.e01 --unattended`)
2. FastAPI creates a new `case_id` UUID, returns it, redirects browser to `/case/{id}`
3. Rust MCP `case_open` tool SHA-256-verifies the image; opens it via libewf in read-only mode; initializes DuckDB at `~/.findevil/cases/<id>/evidence.ddb`
4. LangGraph supervisor emits `PlanProposed` event; analyst approves (or auto-approves in unattended)
5. Supervisor scatters identical plan to Pool A (persistence) and Pool B (exfil) in parallel
6. Each pool's specialists (disk/memory/log analysts) invoke MCP tools via stdio JSON-RPC; each call is sigstore-signed and its SHA-256 output hash is appended to the Merkle tree
7. Pool findings merged into `contradiction.py` node — emits `ContradictionFound` events to the UI **before** reconciliation
8. Analyst resolves contradictions (Trust A / Trust B / Flag) in the SPA, or `--unattended` auto-passes them to the judge
9. Judge node credibility-weighted-merges into final finding set
10. Verifier re-executes tool calls behind every Finding; vetos any without `tool_call_id`
11. Correlator enforces SOUL.md cross-artifact rule (≥2 artifact classes for execution claims)
12. Supervisor assembles `RunVerdict`; Rust MCP finalizes the Merkle root; `opentimestamps-client` stamps the root to Bitcoin asynchronously
13. `run.manifest.json` written; `audit.jsonl` hash-chain finalized; OTS receipt saved
14. `notify-send` + optional Slack webhook fires
15. `find-evil verify run.manifest.json` on any machine with internet validates the entire run offline, citing FRE 902(14)

---

## What we differ from the reference bar (Valhuntir)

| Dimension | Valhuntir (reference) | Us |
|---|---|---|
| MCP server | Python, 8 servers via sift-gateway, 100+ tools | Rust rmcp, 1 server, 11 typed tools, no execute_shell |
| Chain-of-custody | Password-gated HMAC (PBKDF2 2M iter) | sigstore + Merkle + OpenTimestamps Bitcoin anchor (FRE 902(14)) |
| Agent pattern | Single agent + human approval | ACH dual-agent (persistence vs exfil) + judge + contradiction surface |
| Benchmarks published | **None** (their README: "no performance metrics disclosed") | DFIR-Metric + public leaderboard |
| UI | Browser Examiner Portal | Next.js SPA + MCP Apps widgets (SEP-1865) |
| Install pattern | `curl ... | bash` one-liner | `curl ... | bash` one-liner (same pattern, our repo) |
| Credential mode | 1 (their gateway config) | 3 (CLAUDE_CODE_OAUTH_TOKEN / interactive / API key) |

We match Valhuntir's architectural discipline and exceed it on three dimensions that are documented, measurable, and legally framed.

---

## References

- `docs/superpowers/specs/2026-04-23-find-evil-automation-master-design.md` — master design
- `docs/superpowers/specs/2026-04-25-the-product-design.md` — product spec (detailed 7-layer architecture)
- `docs/superpowers/specs/2026-04-24-autonomous-build-swarm-design.md` — swarm spec
- `docs/superpowers/specs/2026-04-23-amendment-option-b-claude-code-mode.md` — credential modes
- `agent-config/SOUL.md` + `AGENTS.md` + `TOOLS.md` + `MEMORY.md` + `HEARTBEAT.md` — runtime agent identity
