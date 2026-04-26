# FIND EVIL! — Build Plan v2

**Layered on top of:** `Find_Evil_Research_and_Build_Plan.docx` (v1, dated 2026-04-22).
**v2 date:** 2026-04-23. **Deadline:** 2026-06-15 22:45 CDT (53 days).
**Purpose:** Capture what changed after April 2026 web research into Lovable-grade autonomy UX, 2026 agent orchestration primitives, and Find Evil! competitor activity. v1 is still the source of truth for DFIR fundamentals, rubric analysis, evidence-integrity invariants, and the References section.

> **Superseded sections (read this first):** Sections that name `services/agent/graph.py`, `services/agent/api.py`, `services/agent/cli.py`, `services/agent/supervisor.py`, or `services/agent/specialists/` describe the pre-A2 architecture. Amendment A2 (2026-04-25, see `docs/superpowers/specs/2026-04-25-amendment-a2-claude-code-primary-interface.md`) drops the custom Python orchestrator entirely — Claude Code IS the orchestrator, and the M2 + M4 stacks ship as a Python MCP server (`services/agent_mcp/`). The `apps/web/` Next.js SPA is deferred to bonus polish. The DFIR fundamentals, rubric analysis, demo beat structure (§9), risk register (§11), and research questions (§12) all stand. Treat any §10 "Week-1 skeleton" file path that names a dropped module as historical context, not as guidance.

---

## 1. What changed (one-paragraph summary)

v1's hypothesis — "win below the Claude Code cluster by shipping a typed MCP server, a verifier loop, and a hash-chained log" — is still correct and unchanged. What the research added:

1. **A web UI is now table stakes, not a differentiator.** At least one public competitor (`github.com/marez8505/find-evil`) ships a localhost dashboard on port 8080 with auth and PDF export. Another (`github.com/dhyabi2/findevil`) is doing hypothesis-driven + MITRE-mapped + self-correcting. We need to compete on Lovable-grade *polish* and DFIR-native *vocabulary*, not on "we have a web UI."
2. **Two orchestration primitives became free in 2026** that v1's plan hand-rolls: LangGraph `SqliteSaver` checkpointing (kill/resume from disk) and Claude Agent SDK subagents (per-specialist context isolation). Adopt both; delete the custom replay code v1 specified.
3. **A new demo beat became available:** Lovable's "Plan Mode" (Feb 2026) — show the investigation plan *before* evidence is touched, gate execution behind approval. This is the most judge-memorable 30 seconds we can add, and it directly answers rubric criterion 1 (Autonomous Execution Quality).
4. **DFIR-IRIS / TheHive / Catalyst vocabulary is a free UX win.** Judges are DFIR practitioners; they already have a mental model of Case → Observables → Tasks → Timeline → Report → Export. Using those exact words in the UI makes us feel native in 2 seconds. Competitors using chat/log framing fight upstream against that expectation.
5. **The commercial autonomous SOC category (Dropzone, Prophet, Exaforce) already has the "watch it unfold" narrative UX** we're aiming for. That gives us concrete reference implementations to steal from, instead of designing from scratch.

---

## 2. Updated winning thesis

Ship a purpose-built Rust MCP server that exposes a narrow typed DFIR surface, driven by a LangGraph graph (with SqliteSaver checkpointing) whose specialist nodes are Claude Agent SDK subagents, wrapped in a Lovable-polished Next.js web UI that uses DFIR-IRIS vocabulary and a Dropzone-style narrative-beside-timeline layout, with architectural guardrails surfaced as UI chrome and verifier decisions rendered as live animations. CLI stays for CI/scripting; the demo and the judge's first impression are browser-first. Publish the accuracy benchmark as a separate Apache 2.0 repo. Every run is one shareable URL, survives SIGKILL, and ends in a verdict card + `notify-send` toast + optional Slack webhook — the "async coworker" experience, local-first.

---

## 3. Updated architecture (v2)

Seven layers, still bottom-up. Deltas from v1 marked **[CHANGED]** or **[NEW]**.

1. **Evidence vault** — read-only mounted image + write-only working dir. Unchanged from v1.
2. **SIFT tool subprocess layer** — unprivileged user, read-only bind mounts, wall-clock + CPU budgets. Unchanged.
3. **Typed Rust MCP server (rmcp)** — narrow typed tools, no `execute_shell`, DuckDB per case owned by server. Unchanged.
4. **Memory layer (three stores):**
   - L1 Case-evidence (DuckDB per case) — unchanged.
   - L2 Per-case structural memory — **[CHANGED]** Now sourced from LangGraph `SqliteSaver` checkpoint, not hand-rolled JSONL replay. Hash-chained JSONL log still emitted for audit trail / forensic soundness, but it's no longer the resume mechanism.
   - L3 Cross-case learned (Hermes-as-MCP-sidecar) — unchanged.
5. **Agent graph** — Python + LangGraph. **[CHANGED]** Specialist nodes are implemented as Claude Agent SDK subagents (one per evidence class: disk, memory, logs, network) so each has its own isolated context window. Supervisor + verifier + correlator remain LangGraph-native Python.
6. **Agent runtime** — **[CHANGED]** Single Python process hosts LangGraph + FastAPI web server + SSE bus. Rust MCP server is a stdio subprocess. OpenClaw + Claude Code both remain supported runtimes for the agent (via the same LangGraph entry point), but day-to-day development and the demo video run in the Python+FastAPI process directly — matches OpenHands's architecture and removes a layer of indirection.
7. **Presentation & automation shell:**
   - **[NEW]** `./find-evil serve` launches FastAPI on `localhost:8080` — primary entry point for demos and interactive use.
   - `./find-evil run --case X.e01` remains for CI/scripting.
   - **[NEW]** Next.js 15 + shadcn/ui + Tailwind v4 web UI (see Section 6).
   - **[NEW]** `notify-send` desktop notifications + optional Slack webhook on verdict commit.
   - GitHub Actions nightly benchmark + regression gate + spoliation suite — unchanged.
   - Single-file offline `report.html` via Vite library build — unchanged.

### Event bus (unchanged from v1, just restated here since it's load-bearing)
Typed `AgentEvent` union streamed via SSE. Variants: `ToolCallStart`, `ToolCallOutput`, `AgentMessage`, `Finding`, `VerifierAction`, `ChainUpdate`, `RunVerdict`, plus **[NEW]** `PlanProposed`, `PlanApproved`, `HypothesisUpdate`. Pydantic on Python side; TypeScript types generated via `pydantic-to-typescript` (replaces v1's `ts-rs` since the event bus moved Python-side).

---

## 4. Updated stack picks

| Layer | v1 | v2 | Why changed |
|---|---|---|---|
| MCP server | Rust (rmcp) | Rust (rmcp) | Unchanged — still correct |
| Agent graph | Python + LangGraph | Python + LangGraph **+ `SqliteSaver` checkpointer** | Native kill/resume, drops hand-rolled replay |
| Specialists | LangGraph nodes | **Claude Agent SDK subagents** inside LangGraph nodes | Per-class context isolation; SDK handles session persistence |
| Web backend | Rust axum + SSE | **FastAPI (Python) + SSE** | Same process as agent, simpler boundary, matches OpenHands |
| Event codegen | `ts-rs` (Rust → TS) | **`pydantic-to-typescript` (Python → TS)** | Event bus moved to Python side |
| LLM text streaming | Raw SSE | **Vercel AI SDK `useChat` pattern** | Industry-standard token streaming; matches Lovable/v0/Bolt |
| Frontend | Next.js 15 + shadcn + Tailwind v4 + TanStack + Observable Plot + Cytoscape + xterm.js + duckdb-wasm | Same minus Cytoscape and xterm.js (cut — see §8) | Scope cuts |
| Case DB (L1) | DuckDB per case | Unchanged | |
| Per-case memory (L2) | Hash-chained JSONL | **SqliteSaver (resume) + JSONL (audit-only)** | Split roles |
| Cross-case memory (L3) | Hermes-as-MCP sidecar | Unchanged | |
| Notifications | None | **`notify-send` + optional Slack webhook** | Coworker-feel payoff |
| Packaging | Docker + Make | Unchanged | |
| CI | GitHub Actions | Unchanged | |
| Docs | Markdown + mkdocs-material | Unchanged | |

---

## 5. The ten differentiators (v2, superseding v1's six)

Ranked by estimated (impact × judge-memorability) / effort.

| # | Differentiator | Rubric criteria hit | Est. build cost |
|---|---|---|---|
| 1 | **Typed Rust MCP server** (narrow, typed, no `execute_shell`) | 2, 4 | ~3 weeks |
| 2 | **Plan Mode approval step** (NEW) — investigation plan before evidence | 1, 4, 6 | ~3 days |
| 3 | **DFIR-native vocabulary** (NEW) — Case/Observable/Task/Finding/Verdict throughout | 6 | ~1 day (audit-and-rename sprint) |
| 4 | **Dropzone-style narrative pane** (NEW) — plain-English reasoning beside tool-call timeline | 1, 3, 6 | ~1 week |
| 5 | **Hypothesis board + MITRE ATT&CK overlay with live confidence deltas** (upgraded from v1 MITRE chips) | 2, 3 | ~4 days |
| 6 | **Verdict card** (NEW) — one-page executive summary, expandable evidence, citations | 5, 6 | ~2 days |
| 7 | **Guardrails-as-chrome** (NEW) — read-only MCP badge, hash-chain integrity widget, forensic_audit viewer | 4, 5 | ~3 days |
| 8 | **Verifier-drop animations** (NEW) — rejected findings fade out with reason tooltip | 1, 2 | ~1 day |
| 9 | **Kill/Resume via LangGraph SqliteSaver** (downgraded from custom replay) | 1 | ~2 days |
| 10 | **Published accuracy benchmark** (separate Apache 2.0 repo, leaderboard CSV) | 2, tiebreaker | ~1 week (week 6) |

Total incremental cost vs. v1: ~2 weeks of net work. Net-net near-even because SqliteSaver adoption cuts ~1 week of custom replay code.

---

## 6. Web UI component contract (v2)

```
app/
├── page.tsx                             # Landing: case list + "New Case" dropzone
├── case/new/page.tsx                    # Upload flow → Plan Mode
├── case/[id]/page.tsx                   # Live investigation (split-pane)
│   ├── <NarrativePane />                # LEFT: Dropzone-style plain-English + span tree
│   │   ├── <PlanModePanel />            # NEW — pre-approval plan view
│   │   ├── <StreamingSpanTree />        # Tool calls + agent messages, Langfuse-like
│   │   └── <VerifierDiff />             # Rejected findings fade out in-place
│   └── <EvidenceCanvas />               # RIGHT: tabs
│       ├── <TimelineTab />              # Observable Plot, linked-brush
│       ├── <HypothesisBoard />          # NEW — MITRE grid with live confidence bars
│       ├── <EventTable />               # TanStack Table + duckdb-wasm
│       └── <ObservablesTab />           # NEW — TheHive-style IOC/observable list
├── case/[id]/verdict/page.tsx           # NEW — verdict card + expandable evidence
└── case/[id]/report.html                # Offline single-file Vite library build

Chrome components (render everywhere):
  <ReadOnlyMcpBadge />                   # NEW — green "read-only" indicator
  <HashChainBadge />                     # Existing — click to re-verify in worker
  <NotifyStatus />                       # NEW — shows "will notify: desktop + Slack"
  <KillResumeControl />                  # Existing
  <CommandPalette />                     # cmdk; unchanged
```

### DFIR vocabulary audit (one-day sprint in week 7)

Every UI string must use TheHive/DFIR-IRIS vocabulary. Banned words → preferred words:

| Banned | Preferred |
|---|---|
| Session, run, job | **Case** |
| Artifact, file, evidence blob | **Observable** |
| Step, action, node execution | **Task** |
| Result, output, hit | **Finding** |
| Conclusion, summary, answer | **Verdict** |
| Score, certainty | **Confidence** |

Grep the entire codebase; judges notice this in hover text and toast messages.

---

## 7. Updated nine-week roadmap (delta from v1)

| Week | Dates | v1 goal | v2 delta |
|---|---|---|---|
| 1 | Apr 22–28 | SIFT VM + Protocol SIFT baseline; repo bootstrap; CI skeleton | **ADD** Week-1 skeleton (§10) runs end-to-end with fake data |
| 2 | Apr 29–May 5 | Rust MCP scaffold + 3 tools; schema validation | Unchanged |
| 3 | May 6–12 | Remaining 7 tools; hash-chain logging | Unchanged |
| 4 | May 13–19 | LangGraph graph + verifier | **REPLACE** hand-rolled replay with SqliteSaver; **ADD** Claude Agent SDK subagents for specialists |
| 5 | May 20–26 | Multi-source correlator; spoliation tests | **ADD** Hypothesis board LangGraph state + MITRE confidence deltas |
| 6 | May 27–Jun 2 | Benchmark harness + leaderboard | Unchanged |
| 7 | Jun 3–9 | Polish, HTML report, docs | **REFRAME** as "Lovable polish sprint": Plan Mode, DFIR vocab audit, guardrails-as-chrome, verifier animations, verdict card, notify-send/Slack |
| 8 | Jun 10–15 | Scripted demo, Devpost render, submit | **ADD** "record with the browser open, not the terminal" as explicit directive |

Dog-leg: if week 7 runs over, cut hypothesis board (5/10 differentiator) before cutting Plan Mode or DFIR vocabulary (2/10 and 3/10 — both are cheap and high-impact).

---

## 8. Explicit scope cuts vs. v1

- **Cut:** Hand-rolled JSONL replay logic — replaced by LangGraph SqliteSaver.
- **Cut:** Cytoscape entity graph tab — timeline + hypothesis board + table cover 90% of judge attention.
- **Cut:** xterm.js raw terminal tab — narrative pane replaces its role; raw logs accessible via JSONL export.
- **Cut:** Multi-case batch analysis (deferred from v1's Analyst Training Loop).
- **Keep everything else** in v1.

---

## 9. Updated demo video beats (5:00 flat)

| Time | Beat | Visual | Rubric hit |
|---|---|---|---|
| 0:00–0:20 | Problem | Breakout-time chart (62→48→29 min; 27-sec fastest) | Stakes |
| 0:20–0:40 | Architecture | One diagram; trust boundaries labeled | 4 |
| 0:40–1:10 | **Plan Mode** — drop `.e01` → plan appears → approve | Lovable-inspired pre-flight | 1, 4 |
| 1:10–3:30 | Live run — narrative pane streaming reasoning, evidence canvas updating, MITRE chips appearing, hypothesis confidence bars animating | "Watch it unfold" (Dropzone pattern) | 2, 3, 5 |
| 3:30–4:00 | Self-correction — verifier rejects a finding, fade-out animation + reason tooltip, re-dispatch, corrected finding appears | Visible autonomy | 1, 2 |
| 4:00–4:30 | Kill/Resume — `Ctrl+C`, show SqliteSaver state on disk, resume, pick up at last checkpoint, hash-chain badge verifies | Memorable moment | 1 |
| 4:30–4:50 | Verdict card renders → `notify-send` toast → Slack webhook message | Coworker-feel payoff | 6 |
| 4:50–5:00 | Links to benchmark repo, CI badge green, submission package manifest | Tiebreaker proof | — |

**Directive:** record with the browser open, not the terminal. Most competitors will open with a terminal; the browser-first framing is a free differentiator.

---

## 10. Week-1 skeleton (first vertical slice)

Goal: end of week 1, a full (fake-data) loop runs end-to-end. Every week after fills in real functionality behind known contracts.

1. **Next.js 15 shell** (`apps/web/`) — shadcn/ui scaffolding, dark theme, three routes: `/`, `/case/new`, `/case/[id]`. Drop zone on `/case/new` fires a POST to FastAPI with a stubbed response. Plan Mode modal renders hardcoded plan.
2. **FastAPI service** (`services/agent/`) — three endpoints: `POST /cases` (accepts file, returns `case_id`), `GET /cases/:id/stream` (SSE emitting a hardcoded `AgentEvent` sequence), `POST /cases/:id/plan/approve`.
3. **Rust MCP server scaffold** (`services/mcp/`) — `rmcp` + `case_open` tool only; returns `CaseHandle { id, db_path, image_hash }`. stdio transport. Compiles and runs.
4. **LangGraph skeleton** (`services/agent/graph.py`) — supervisor + one dummy specialist that emits a fake `Finding`, compiled with `SqliteSaver.from_conn_string("case.db")`. Verify kill/resume with a test.
5. **`./find-evil serve` launcher** (`scripts/serve.sh`) — single command that starts FastAPI + Next.js dev server + Rust MCP server, opens browser to `localhost:8080`.
6. **GitHub Actions CI** — runs `cargo test`, `pytest`, `pnpm build`, and a smoke test that hits `POST /cases` and verifies SSE stream starts. Green badge in README.

Acceptance test for end of week 1: `./find-evil serve` → drag a placeholder `.e01` → Plan Mode modal → approve → fake `AgentEvent` stream plays in the UI → finishes with a fake verdict. Then SIGKILL the Python process, restart, verify the case URL resumes to the same state.

---

## 11. Updated risk register (additions to v1's R1–R17)

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R18 | Polish sprint (week 7) goes over time | **High** | Med | Fixed budget; dog-leg cut order already defined (drop hypothesis board first). Lovable-level polish is infinite; stop when week 8 starts. |
| R19 | `notify-send` / Slack integration doesn't work on judges' SIFT VM | Med | Low | `notify-send` ships with libnotify-bin — auto-install in setup.sh; Slack webhook is optional, only fires if configured in env. |
| R20 | DFIR vocabulary rename breaks link discoverability late in sprint | Low | Med | Do the rename in week 7 BEFORE docs are finalized; grep-based search-replace in one commit; unit tests for UI copy. |
| R21 | LangGraph SqliteSaver API changes between pin and submission | Low | High | Pin exact version in `pyproject.toml`; CI runs weekly with `--upgrade` as canary; hold pin otherwise. |
| R22 | Competitor ships equivalent Lovable-polish UX | Med | High | Our architecture moat (Rust MCP + three-layer memory + verifier + benchmark) is still unique regardless of UX. But monitor `github.com/topics/find-evil` weekly. |
| R23 | Plan Mode approval step slows the demo video past 5 min cap | Low | Med | Hard budget: Plan Mode + approval ≤30 s. If Plan Mode render takes longer, cache a pre-computed plan for the demo case. |

---

## 12. Open research questions (targets for the next research pass)

These are things the v2 plan punts on; the user wants to research them next.

1. **LangGraph SqliteSaver + Claude Agent SDK subagent interaction** — can a LangGraph node internally spawn a Claude Agent SDK subagent and have both checkpoint correctly? Need a canonical recipe. Search: LangGraph docs (current), Claude Agent SDK repo, any published examples of combining them.
2. **Vercel AI SDK with a FastAPI backend** — Vercel's SDK expects Next.js API routes by default. What's the canonical pattern for Next.js frontend + Python backend streaming? `useChat({ api: "http://localhost:8080/stream" })` should work but edge cases (tool calls, structured outputs) need confirmation.
3. **Durable execution libraries revisited** — if LangGraph SqliteSaver turns out to have gaps (e.g., doesn't checkpoint Claude Agent SDK subagent state), is Temporal/Restate/Inngest worth the dependency on a local SIFT VM? Cost-benefit TBD.
4. **Protocol SIFT's current state** — check `github.com/teamdfir/protocol-sift` weekly for updates; the baseline might evolve during the hackathon and change what counts as a meaningful delta.
5. **Competitor repo monitoring** — add `marez8505/find-evil` and `dhyabi2/findevil` to a watch list; search `github.com/topics/find-evil-hackathon` weekly for new entrants. Who else is shipping? What patterns are they converging on?
6. **DFIR-IRIS / TheHive UI study** — screen-capture their actual case-creation flow; identify specific UI idioms to copy (e.g., how DFIR-IRIS shows observables in a sidebar, task status badges, report template rendering).
7. **Air-gapped Chrome testing** — verify `duckdb-wasm` + base64-embedded Parquet actually works in `--disable-features=NetworkService`. This has regressed in Chrome before. Smoke test it in week 1 before committing to the offline-report strategy.
8. **Claude Agent SDK versioning** — check Anthropic's SDK changelog; what's the stable API surface as of June 2026? Are there subagent features that shipped after the research cutoff that we should use?
9. **OpenHands architecture deep-dive** — read their SDK paper (arxiv.org/html/2511.03690v1) end-to-end; extract specific patterns for FastAPI + SSE + agent process lifecycle that we can copy verbatim.
10. **SANS judging biases** — are there recorded past SANS hackathons or Summit talks that reveal what this specific set of judges (Rob T. Lee et al.) values? Tone? Depth? Honesty about limitations?

---

## 13. Source of truth

- **v1 (this document's parent):** `Find_Evil_Research_and_Build_Plan.docx` — DFIR fundamentals, rubric deep-dive, original architecture sketch, v1 differentiator list, References (Section 19). Still authoritative for all content not contradicted by v2.
- **v2 (this document):** research-driven deltas dated 2026-04-23. Supersedes v1 only where explicitly noted.
- **Memory system:** `C:/Users/newbi/.claude/projects/C--Users-newbi-Desktop-PUG-Projects-SANS-Hackathon/memory/` — project context, user role, reference URLs. Loaded into future Claude Code sessions automatically.

---

*This plan is intentionally research-driven and incomplete. §12 lists what it doesn't know yet. Run the next research pass against those questions before committing to week-1 implementation.*
