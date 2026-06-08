---
date: 2026-06-08
description: VERDICT architecture decisions — amendments A1-A6, the non-negotiable invariants, and the memory-is-never-evidence boundary.
tags: [brain, decision]
---

# Key Decisions

## Amendment lineage (code wins over spec)

Specs were written 2026-04-23; code has shipped since 2026-04-24. **Where they disagree, shipped
code + its committed pin files win.**

- **A1** — three credential modes (`CLAUDE_CODE_OAUTH_TOKEN` › interactive `~/.claude/` ›
  `ANTHROPIC_API_KEY`). The build-swarm LiteLLM proxy was never built.
- **A2** — Claude Code IS the orchestrator; the custom Python orchestrator (`graph.py`/`api.py`/
  `cli.py`/`supervisor.py`) was dropped. Adds `services/agent_mcp/` + `.mcp.json`.
- **A3** — `apps/web/` live dashboard (SSE audit tail, role-state sprites) + 3 agent-mcp tools:
  `memory_remember`/`memory_recall` (Hermes FTS5), `pool_handoff` (IBM ACP).
- **A5** — removed the OpenTimestamps/Bitcoin 4th crypto tier. Chain is **3 tiers**: audit
  `prev_hash` → rs_merkle root → sigstore. `opentimestamps-client` dep cut.
- **A6** (2026-06-07) — removed the build swarm (Spec #1) entirely; subsystems 4 → 3.

## Non-negotiable invariants

- **No `execute_shell` tool, ever.** 19 Rust + 12 Python = 31 typed tools is the entire verb set.
- **Every Finding cites a `tool_call_id`.** The verifier vetoes uncited findings.
- **Epistemic hierarchy is strict:** CONFIRMED (tool-backed) > INFERRED (≥2 confirmed facts) >
  HYPOTHESIS (prefixed "hypothesis:").
- **Execution claims need ≥2 artifact classes.** Amcache alone is insufficient.
- **Evidence is read-only**; SHA-256 verified at `case_open`; `.e01` opened via libewf.
- **AGPL/GPL tools (Hayabusa, Volatility3, Velociraptor, YARA-via-binary) are subprocess-only —
  never linked.** Keeps the tree Apache-2.0 clean.
- **Replay evidence is a customer-PDF blocker** (`verify_finding_replay_embedded`). Do not
  downgrade without an explicit policy change.

## Engine decisions worth remembering

- **NIST/SCHARDT corroboration via UserAssist.** Prefetch + UserAssist (ROT13 `UEME_RUNPATH:`)
  = two execution artifact classes; promotes prefetch hacking-tool findings to CONFIRMED. Three
  downgrade gates had to clear: verify replay, judge floor (solo CONFIRMED kept), correlator
  (`_USERASSIST_RE`). See [[Gotchas#NIST SCHARDT disk wall (SIFT)]].
- **In-tree registry reader** (`regf.rs`) replaced `frnsc-hive` (which panicked on XP `lf/li/ri`
  cells); `notatin` won't build under rustc 1.88.
- **`rmcp` deliberately NOT activated** — `server.rs` is a hand-rolled stdio JSON-RPC 2.0 server.

## Memory is never evidence

The dev/operator memory systems — **this obsidian-mind vault** and the **n8n grounding**
sidecars — are both **outside** the investigation. They never produce a
`tool_call_id`, never append to `audit.jsonl`/`run.manifest.json`, and never change a Finding's
Confidence or the Verdict (frozen at `manifest_finalize`). Web text is untrusted DATA. The only
in-flow memory is the audit-chained Hermes FTS5 pair (`memory_remember`/`memory_recall`).

Related: [[North Star]] · [[Gotchas]] · [[Patterns]]
