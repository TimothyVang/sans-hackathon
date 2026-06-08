---
date: 2026-06-08
description: VERDICT project North Star — what we are building, for whom, the hard boundary memory must respect, and current state.
tags: [brain, north-star]
aliases: [Goals, Focus]
---

# North Star — VERDICT

**VERDICT is a DFIR agent.** Point it at digital evidence (Windows memory, EVTX, disk, network,
Velociraptor) and it produces a signed **Verdict** — *is there evil here?* — plus an analyst
report, backed by a cryptographic chain of custody any third party can verify offline.
**Claude Code IS the engine** (Amendment A2): when a judge runs `scripts/verdict` or `claude`
from this repo, that session is the forensic analyst.

This is the SANS **Find Evil!** 2026 hackathon submission. Deadline **2026-06-15 22:45 CDT**.

## Goals

- Every conclusion is provable: each **Finding** cites a `tool_call_id`; the whole run is
  hash-chained, Merkle-rooted, and signed (`manifest_verify` checks it offline).
- The tool surface stays narrow and typed — **31 product tools, no `execute_shell`** — because
  the narrowness *is* the security pitch.
- Verdicts stay honest about coverage: `SUSPICIOUS` / `INDETERMINATE` / `NO_EVIL`, never
  "definitely safe."
- The judge narrative is "an orchestrator that reduces friction," never "autonomous responder."

## The memory boundary (read before writing anything here)

This vault is the **dev/operator memory layer**. It is **never evidence, never in a case
`audit.jsonl`, never Merkle-hashed, and never emits a Finding.** That hard line is the same one
Engram and the n8n grounding feature respect — see [[Key Decisions#Memory is never evidence]].
The in-flow *investigation* memory is the Hermes FTS5 `memory_remember`/`memory_recall` tools, a
different system.

## Current state

Product is feature-complete through A3 Phase 4 + post-A5 additions. Local EVTX investigations run
fully in-process; disk forensics run via the SANS SIFT VM (`--sift`). The NIST/SCHARDT disk case
now reaches **SUSPICIOUS / CONFIRMED** via UserAssist corroboration — see
[[Gotchas#NIST SCHARDT disk wall (SIFT)]]. Open work is mostly human submission steps (demo
video render/upload, Devpost).

Related: [[Memories]] · [[Gotchas]] · [[Key Decisions]] · [[Patterns]] · [[Skills]]
