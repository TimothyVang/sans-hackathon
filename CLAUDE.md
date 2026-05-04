# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. Under **Amendment A2** (2026-04-25, active) Claude Code IS the Product's primary interface — when a SANS judge runs `scripts/find-evil` or `claude` from this repo, the session you are reading is what executes the investigation. CLI binary is `claude` (the canonical name; older docs alias as `claude-code`).

## Agent investigation prompt (read first when invoked in this repo)

When a session opens in this repo and the user asks you to **"investigate \<case path\>"** or similar, you are acting as the SANS Find Evil! DFIR agent. Before answering, read these files in order — they encode mission, identity, and hard rules that you MUST not violate:

1. **`agent-config/SOUL.md`** — your purpose, the epistemic hierarchy (CONFIRMED > INFERRED > HYPOTHESIS), the FRE 902(14) self-authenticating-evidence stance, the strict cross-artifact rule for execution claims, the no-attribution rule.
2. **`agent-config/AGENTS.md`** — the supervisor/Pool A/Pool B/judge/verifier/correlator role descriptions. You are the supervisor; the two pools are spawned as forked subagents (`CLAUDE_CODE_FORK_SUBAGENT=1`).
3. **`agent-config/PLAYBOOK.md`** — investigation tool sequences per evidence type (`.e01`, `.mem`, `.evtx`, Velociraptor `.zip`, mixed case dirs). Treat as defaults, not laws — deviate when the case shape diverges and log the deviation.
4. **`agent-config/TOOLS.md`** — the typed tool surface (Rust `findevil-mcp` + Python `findevil-agent-mcp`).
5. **`agent-config/MEMORY.md`** — Tier-1 DFIR caveats (Amcache LastModified ≠ execution, ShimCache order changed at Win8.1, EVTX Logon Type 3 vs 10, etc.).
6. **`agent-config/HEARTBEAT.md`** — the per-iteration self-check loop.
7. **`agent-config/JUDGING.md`** — the SANS Find Evil! 2026 rubric (6 criteria, verbatim) plus the end-of-investigation self-score checklist that appends to the audit JSONL as `kind="judge_selfscore"` before `manifest_finalize`. The agent is graded against this, so it must self-check against this.

Two MCP servers are registered in `.mcp.json` and auto-spawned by Claude Code on session start:

| Server | Lang | Tools |
|---|---|---|
| `findevil-mcp` | Rust (`services/mcp/`) | DFIR tool surface — `case_open`, `evtx_query`, plus 11 more (`mft_timeline`, `hayabusa_scan`, `vol_pslist`, `vol_psscan`, `vol_psxview`, `vol_malfind`, `yara_scan`, `usnjrnl_query`, `registry_query`, `prefetch_parse`, `vel_collect`). Read-only on evidence; SHA-256 every output. The `vol_pslist` + `vol_psscan` pair is deliberately redundant — pslist walks the active list, psscan signature-scans EPROCESS pool memory; divergence between the two is the textbook DKOM/T1014 (Rootkit) signature. `vol_psxview` cross-references process views after a divergence. |
| `findevil-agent-mcp` | Python (`services/agent_mcp/`) | 11 tools — crypto/ACH plumbing (`audit_append`, `audit_verify`, `manifest_finalize`, `manifest_verify`, `verify_finding`, `detect_contradictions`, `judge_findings`, `correlate_findings`) + Hermes-pattern cross-case memory (`memory_remember`, `memory_recall`) + IBM-ACP handoff (`pool_handoff`). A3 added the 3 memory/ACP tools; **A5 (2026-04-30) removed `ots_stamp` + `ots_verify`** — Bitcoin/OpenTimestamps tier cut, chain is now 3 tiers (audit prev_hash → rs_merkle → sigstore). See `agent-config/AGENTS.md` for canonical use sites per role. |

The investigation flow is roughly: `case_open` → split into Pool A (persistence) + Pool B (exfil) subagents → each pool runs DFIR tools and emits Findings (each citing a `tool_call_id`) → `detect_contradictions` → analyst resolves → `verify_finding` re-runs each cited tool → `judge_findings` (credibility-weighted merge) → `correlate_findings` → `manifest_finalize` (signs the run; terminal beat under A5). The terminal beat map for the judge demo lives in Amendment A2 §2.3.

## Project state

This is the SANS **Find Evil!** hackathon submission (deadline **2026-06-15 22:45 CDT**). All four subsystems exist and the smoke suite is **fully green** (14/14 in `bash scripts/run-all-smokes.sh` as of 2026-04-27). The Product layer is feature-complete through Amendment A3 Phase 4 plus the post-A5 `vol_psxview` addition: **24 MCP tools** (13 Rust DFIR + 11 Python crypto/ACH/memory/ACP — post-A5), the agent-config prompts know when to call them, the audit-log SSE tail powers a Next.js + Tailwind v4 + NES.css dashboard scaffold at `apps/web/`. The five pixel-art sprite components (Phase 5) and the AuditBeadString chrome (Phase 6) remain gated on a Claude Design prototyping pass per A3 §1.2. The 0-hard-blocker state was reached when PR #4 cut the pre-A2 `find-evil` CLI wrapper + `.deb` packaging.

Before writing code of your own, **read the relevant spec and plan** for the subsystem you are touching. The specs define exact file paths, pinned dependency versions, and TDD task sequences; diverging from them silently creates integration mismatches with other subsystems. When a spec and the current code disagree, the **code + its committed pin files win** — see "Spec/code divergences" below for known cases. `CHANGELOG.md` summarizes per-feature; `git log --oneline -20` for recent commit context.

## In-flight design work (post-A3, not yet implemented as code)

Two design artifacts remain as research material — neither is on the critical path; both can be cut without affecting the shipped Product. Treat as optional, not inherited TODOs.

- **Phase 5/6 sprite design brief** (`docs/design-briefs/phase-5-6-sprite-design-brief.md`) — Claude Design handoff for sprites + AuditBeadString chrome that would dress `apps/web/`. Only the SSE audit-tail route is wired (debug viewer at `/debug`). Polish-budget item.
- **Amendment A4 — Managed Agents production runtime** (`docs/specs/2026-04-27-amendment-a4-managed-agents-runtime.md`) — third deployment mode for hosted durability. PURELY ADDITIVE; A1/A2/A3 unchanged. Deferred until post-submission adoption.

The canonical Product is the existing investigation flow: `scripts/find-evil` (interactive), `scripts/find-evil-auto` (headless), `scripts/find-evil-sift` (SIFT-VM SSH bridge). Earlier "Judge Mode + Tamper Replay" spec + plans + design-loop output were removed in the scope-reduction pass.

## External reference clones (never ship, never edit, never import)

Four directory names are reserved at the repo root for local-only research clones; all are `.gitignore`'d. Under A2 none are required at runtime — Claude Code drives investigations via the two MCP servers in `.mcp.json`.

- **`openclaw/`** — Openclaw harness. Pre-A2 candidate entry point; superseded by `scripts/find-evil`/`find-evil-auto`.
- **`hermes-agent/`** — Hermes MCP sidecar (cross-case L3 memory). Deferred to week-7 polish.
- **`Linear-Coding-Agent-Harness/`** — build-swarm worker pattern reference. Read-only.
- **`.playwright-mcp/`** — scratch from a competitor-recon session.

Editing files inside these is almost certainly a mistake — check `.gitignore` first. The Devpost zip is produced by `scripts/package-devpost.sh`.

An expanded research library lives at `git-hub-references/` (gitignored per A3 §1.3) — see `git-hub-references/CLAUDE.md` for the per-clone index (seven SDK/OpenClaw/Hermes/Pixel-Agents clones + DFIR awesome-lists). Same "never ship, never edit, never import" rule.

## Quickstart for the impatient

If you want to run the agent against evidence right now, see **`QUICKSTART.md`** at the repo root. Three steps: pick environment (SIFT VM or local), open Claude Code, prompt `investigate <path>`. Everything else in this file is reference material.

For false-positive prevention strategy and analyst checklists, see **`docs/false-positives.md`** — three architectural layers, four operational habits, plus specific FP traps and how to avoid them.

For an example end-to-end investigation report (real evidence, real findings), see **`docs/reports/2026-04-26-srl2018-dc-investigation.md`** — covers the SRL-2018 SANS HACKATHON-2026 dataset, includes a CONFIRMED DKOM finding (MITRE T1014).

## Document hierarchy (authoritative order)

Read these in precedence order. Later documents override earlier ones only where explicitly noted:

1. **`docs/specs/2026-04-23-find-evil-automation-master-design.md`** — master design. 4-subsystem decomposition + 4 differentiators (M1 leaderboard, M2 crypto chain-of-custody, M3 MCP App widgets, M4 ACH competing-hypothesis agents).
2. **`docs/specs/2026-04-23-amendment-option-b-claude-code-mode.md`** — **A1, active.** Removes LiteLLM proxy + `services/swarm/budget.py` + USD caps; workers use the user's Claude Code subscription via `claude` CLI. Product accepts three credential modes (`CLAUDE_CODE_OAUTH_TOKEN`, interactive `~/.claude/`, `ANTHROPIC_API_KEY`).
3. **`docs/specs/2026-04-25-amendment-a2-claude-code-primary-interface.md`** — **A2, active.** Drops the custom Python orchestrator (`graph.py`/`api.py`/`cli.py`/`supervisor.py`/specialists) — Claude Code IS the orchestrator. Adds `services/agent_mcp/` and `.mcp.json` registering both servers. `apps/web/` + `apps/mcp-widgets/` deferred (A3 un-defers `apps/web/`).
4. **`docs/specs/2026-04-26-amendment-a3-agent-army-and-dashboard.md`** — **A3, active.** Un-defers `apps/web/` (NES.css live dashboard tailing the audit JSONL hash chain; 5 sprites mapping to `agent-config/AGENTS.md` roles). Adds 3 tools to `findevil-agent-mcp`: `memory_remember`/`memory_recall` (Hermes FTS5 cross-case memory), `pool_handoff` (IBM ACP envelope). `apps/mcp-widgets/` remains deferred.
5. **`docs/specs/2026-04-27-amendment-a4-managed-agents-runtime.md`** — **A4, future deployment (NOT critical path).** Third deployment mode on Anthropic's Managed Agents (durable containers, auto-recovery, multi-tenant). Purely additive; A1/A2/A3 unchanged. Adds `services/mcp_http/` + `services/managed_agent/` + `scripts/find-evil-managed`. Cost model conflicts with A1 (metered vs subscription). Deferred post-submission.
6. **A5 (2026-04-30, active — no spec doc yet, encoded in commits + CHANGELOG).** Removes the OpenTimestamps/Bitcoin tier. Cuts `services/agent/findevil_agent/crypto/ots.py` + tests, `ots_stamp`/`ots_verify` MCP tools, and the `opentimestamps-client` dep. Chain collapses from 4 tiers to 3 (audit prev_hash → rs_merkle → sigstore). Commits `743404d`, `a75ea44`, `e265600`, `6da4d95`, `2b59572`. Post-A5 `findevil-agent-mcp` registry is **11 tools, not 13**; `services/agent_mcp/tests/test_stdio_smoke.py` enforces it.
7. **Per-subsystem specs** (in `docs/specs/`):
   - `2026-04-23-layered-test-sandbox-design.md` — Spec #3 (L0-L3 sandbox; blocks all other work).
   - `2026-04-24-autonomous-build-swarm-design.md` — Spec #1 (build swarm; interpret through A1).
   - `2026-04-25-the-product-design.md` — Spec #2 (the DFIR tool judges run).
   - `2026-04-26-orchestration-glue-design.md` — Spec #4 (GHA CI; `budget-guard.yml` is a no-op under A1 unless `ANTHROPIC_API_KEY` is set).
8. **Implementation plans** (in `docs/plans/`) — one per spec, each step written as a TDD checkbox with the exact failing test → implement → commit sequence.
9. ~~**`BUILD_PLAN_v2.md`**~~ — moved to `docs/legacy/BUILD_PLAN_v2.md` 2026-05-02 (pre-A2/A3/A5 research artifact; pitch surface consolidated into `README.md` per Phase 3c+3d of the doc reorg — SUBMISSION_NOTES.md was deleted in 3d, judge Q&A migrated to README "Anticipated questions"). Kept in legacy for git-log archaeology; do not read it for current architecture.
10. **`Find_Evil_Research_and_Build_Plan.docx`** — v1 research doc; authoritative only for what v2 doesn't contradict.

## Repository layout (current)

Shipped tree — these are the directories that end up in the submission:

```
.
├── Cargo.toml / Cargo.lock / rust-toolchain.toml   # Rust workspace (members = [services/mcp]); Cargo.lock IS committed (app, not library)
├── Dockerfile                                      # Production multi-stage image → ghcr.io/find-evil/find-evil:v<N>
├── LICENSE                                         # Apache-2.0
│                                                   # (pre-A2/A3/A5 research artifacts — BUILD_PLAN_v2 + v1 .docx — both at docs/legacy/)
├── sift-2026.03.24.ova                             # 9.3 GB SIFT VM image — Packer input; gitignored (*.ova)
├── agent-config/                                   # Runtime DFIR agent identity (SOUL/AGENTS/TOOLS/MEMORY/HEARTBEAT/JUDGING/PLAYBOOK)
├── docs/specs/ + plans/                # 8 specs (incl. A1 + A2 + A3 amendments) + 5 TDD plans
├── docs/braindumps/                                # Origin-of-feature scratch docs — A3 spawned from docs/braindumps/2026-04-26-agent-army-and-dashboard.md
├── docs/legacy/                                    # v1 docs superseded by v2 + amendments
├── services/mcp/                                   # Rust MCP server (13 typed DFIR tools; hand-rolled stdio JSON-RPC 2.0 per "Spec/code divergences" §5; evtx/duckdb/rs_merkle linked; others subprocess-only)
├── services/agent/                                 # Python package findevil_agent — M2 crypto + M4 ACH + A3 memory/acp (FastAPI/LangGraph DROPPED under A2)
├── services/agent_mcp/                             # Python MCP server wrapping M2/M4/memory/ACP as 11 typed tools for Claude Code
├── services/swarm/                                 # Python build swarm (Option B — Claude CLI subagents)
├── .mcp.json                                       # A2: registers findevil-mcp (Rust) + findevil-agent-mcp (Python) for auto-spawn
├── apps/web/                                       # Next.js 15 + Tailwind v4 + NES.css scaffold (A3 §2.1) — SSE audit-log tail at /api/audit, /debug live viewer, pydantic→TS event codegen at lib/events.ts; sprites + chrome gated on Claude Design pass
├── apps/mcp-widgets/                               # M3 widgets — still DEFERRED per A2 §2.1 (A3 does not need them)
├── packer/sift-microvm.pkr.hcl                     # L3 warm-qcow2 build from the OVA
├── docker/                                         # l1-compose.yml, l1-devbase.Dockerfile, l2-siftlite.Dockerfile, swarm-postgres.yml
├── scripts/                                        # swarm-start, swarm-status, l2-dfir-smoke, l3-run-goldens, fetch-fixtures,
│                                                   # package-devpost, push-leaderboard-score, competitor-watch,
│                                                   # setup-branch-protection, sift-provision, verify-sandbox, json-to-benchmark-csv.py
│                                                   # find-evil-auto + find_evil_auto.py (Tesla-mode end-to-end orchestrator),
│                                                   # fleet_investigate.py + fleet_correlate.py + render_fleet_report.py (multi-host pipeline),
│                                                   # render_report.py + _report_style.css (per-case PDF rendering)
├── goldens/                                        # nist-hacking-case/, synthetic-benign/ — L3 golden fixtures
└── .github/workflows/                              # l0/l1/l2/l3 + release + competitor-watch + devpost-submit + budget-guard
```

The dev entry points are `scripts/find-evil` (interactive Claude Code session) and `bash scripts/find-evil-auto <evidence>` (headless single-shot orchestrator over SSH into a SIFT VM); see "Commands" below. The pre-A2 `python -m findevil_agent.cli` entry point was dropped by A2; the corresponding Dockerfile wrapper + `scripts/build-deb.sh` were cut on 2026-04-27 (PR #4) per `docs/runbooks/dockerfile-a2-decision.md` "Option B." The L0 `amendment-a2-guard` GHA job + L1 `divergence-smoke.py` §3 both fail CI if `findevil_agent.cli` re-appears in active code.

## The 4 subsystems (master design §3)

```
#3 Sandbox (L0-L3) ──┐
                     ├──► #1 Build Swarm ──► #2 Product ──► #4 Orchestration Glue
                     └──► #2 Product (directly — sandbox also gates Product CI)
```

- **#3 Sandbox** blocks everything else. L0 lint, L1 unit/build (Docker Ubuntu 22.04), L2 SIFT-lite (Sysbox runtime, advisory), L3 full SIFT VM parity (QEMU microvm + qcow2 snapshot-restore, Packer-built from `sift-2026.03.24.ova`, on GHA KVM larger runners).
- **#1 Build Swarm** is invisible to judges — writes code overnight into draft PRs. LangGraph supervisor + Claude CLI subagents + one git worktree per PR + critic subagent gate. **Option B (A1):** runs on user's Claude Code subscription, not a metered API key.
- **#2 Product** is the submission. Under **A2** the layers collapse to: evidence vault → SIFT tool subprocesses → two MCP servers (Rust DFIR tools + Python crypto/ACH wrappers) → Claude Code (acts as supervisor + ACH pool subagents + audit-log driver). Primary entry point: **`scripts/find-evil`** (or `claude` directly — the canonical Claude Code CLI binary name). The Next.js SPA / `find-evil serve` / `find-evil run` / `find-evil verify` are not on the critical path; the equivalent verification is the `manifest_verify` MCP tool (the `ots_verify` tool was removed by Amendment A5).
- **#4 Orchestration Glue** is thin CI: 9 GHA workflows, branch protection, release pipeline, Devpost submission zip on `v-submit` tag.

## Non-negotiable invariants

These show up across multiple specs and the agent-config files. Violating any of them breaks the judging story or an integration contract:

- **No `execute_shell` MCP tool, ever.** The Rust MCP server's typed surface (13 tools — the 11 from Spec #2 §6 plus `vol_psscan` and `vol_psxview` for DKOM cross-validation) is deliberately narrow. Adding shell pass-through undoes the "reduces the attack surface" pitch.
- **Every Finding cites a `tool_call_id`.** The verifier node vetos any Finding without one (Spec #2, `agent-config/SOUL.md`). UI chips render `[confirmed · tool · sha256]` per finding.
- **Epistemic hierarchy is strict.** `CONFIRMED` (backed by tool output) > `INFERRED` (≥2 confirmed facts, labeled) > `HYPOTHESIS` (prefixed "hypothesis:"). Nothing else is legal.
- **AGPL/GPL tools (Hayabusa, Chainsaw, Volatility3, Velociraptor, YARA) are subprocess-only — never linked.** Violating this contaminates the submission license (must be MIT or Apache-2.0 per SANS rules).
- **Evidence is read-only.** Original `.e01` opened via libewf; write-only working dir elsewhere. No tool mutates evidence. SHA-256 of image verified at `case_open`.
- **Hash-chained audit JSONL is append-only.** Each line has a `prev_hash` field linking to the previous line. Rewriting history breaks the M2 crypto chain-of-custody pitch ("FRE 902(14) self-authenticating"). The chain is **3 tiers** post-A5 (audit prev_hash → rs_merkle → sigstore); the 4th OpenTimestamps/Bitcoin tier was removed 2026-04-30 — see `docs/cryptographic-attestation.md` and rubric criterion #5 ("Audit Trail Quality").
- **Draft PRs only.** The build swarm never auto-merges or force-pushes `main`. Human merges every PR after morning triage.
- **Execution claims need ≥2 artifact classes** (Prefetch + Amcache+ShimCache, or EDR telemetry). Amcache alone is insufficient — it's catalog-registration time, not execution.
- **All timestamps UTC, ISO-8601, trailing `Z`.** SHA-256 preferred over MD5. Never assert attribution.
- **Judge narrative:** "orchestrator that reduces friction," never "autonomous responder." Rob Lee's explicit preference (memory: `project_judging_signals.md`).

## Credential modes (Amendment A1)

The Product (`scripts/install.sh`) detects three credential paths in priority order:

1. `CLAUDE_CODE_OAUTH_TOKEN` env var (from `claude setup-token`) — non-interactive, script-friendly. Preferred for judges with a subscription.
2. Interactive Claude Code session (`~/.claude/` populated via `claude auth login`) — used in dev.
3. `ANTHROPIC_API_KEY` env var — direct metered API, used when no Claude Code is available.

**For the build swarm specifically:** only modes 1 and 2 apply. Option B removed all LiteLLM/USD-cap code; rate-limit handling is `services/swarm/findevil_swarm/session_guard.py`, which halts the supervisor cleanly on 429 and resumes from the Postgres checkpoint the next night. There is no in-flight retry.

## Commands

Canonical commands. As of 2026-04-27 the smoke suite is fully green (14/14); quote these verbatim so swarm-generated code and human work use the same invocations.

**Rust MCP server (`services/mcp/`):**
- Build: `cargo build --workspace --release --locked`
- Lint: `cargo check --workspace && cargo clippy --workspace --all-targets -- -D warnings`
- All tests: `cargo test --workspace --locked`
- Single test (named fn in an integration test file): `cargo test -p findevil-mcp --test tool_smoke test_case_open_returns_handle`
- Single crate's unit tests: `cargo test -p findevil-mcp --lib`

**Python agent + swarm (`services/agent/`, `services/agent_mcp/`, `services/swarm/`):**
- There is **no root `pyproject.toml`** — each service is its own uv project. Use `--directory <svc>` (or `cd` first) for any uv command that needs a project context.
- Env sync (per service): `uv sync --directory services/agent` (likewise `services/agent_mcp`, `services/swarm`)
- Lint + format check (works from repo root — ruff walks the tree): `ruff check . && ruff format --check .`
- All tests (the L1 way — iterate per service): see `docker/l1-compose.yml` lines 60–68; locally use `bash scripts/run-all-smokes.sh` or run each service's pytest separately
- Single file: `uv run --directory services/agent pytest tests/test_crypto_audit_log.py -v`
- Single test function: `uv run --directory services/agent pytest tests/test_crypto_audit_log.py::TestCanonicalize::test_sorted_keys -v`
- Run an investigation directly (dev, under A2): `scripts/find-evil` (interactive Claude Code session) or `bash scripts/find-evil-auto <evidence-path>` (headless single-shot orchestrator). The pre-A2 `python -m findevil_agent.cli` entry point was dropped — see the "## Agent investigation prompt" guidance at the top of this file.

**Next.js web (`apps/web/`):** `apps/mcp-widgets/` remains deferred per A2 §2.1; commands below filter to `@findevil/web` since it's the only live workspace member.
- Install: `pnpm install --frozen-lockfile` (run from repo root)
- Typecheck: `pnpm --filter @findevil/web typecheck`
- Build: `pnpm --filter @findevil/web build`
- Test all: `pnpm --filter @findevil/web test` (8 Vitest tests covering `audit-tail.ts` + the path allow-list)
- Test one file: `pnpm --filter @findevil/web test -- __tests__/audit-tail.test.ts`
- Dev server: `pnpm --filter @findevil/web dev` then open `http://localhost:3000` (placeholder dashboard) or `http://localhost:3000/debug` (live SSE event viewer)
- Regenerate audit-event TypeScript types from Pydantic source: `pnpm --filter @findevil/web codegen:events` (writes `apps/web/lib/events.ts`)

**Launchers under Amendment A2 (Claude Code as primary interface):**
- Open an investigation, **local mode** (the demo entry point): `scripts/find-evil` or `claude` from the repo root. `.mcp.json` auto-spawns both MCP servers locally. Use this when the DFIR tool binaries (Hayabusa, Volatility3, Velociraptor) are installed on the host machine.
- Open an investigation, **SIFT-VM mode** (Tesla-mode automation against the SANS-blessed environment): `bash scripts/find-evil-sift` from the repo root. Pre-flight: run `bash scripts/sift-vm-bootstrap.sh` (one-time, ~15 min — converts `sift-2026.03.24.ova` to a VMware Workstation VM, boots it headless, builds `findevil-mcp` inside, installs the SSH key). The launcher then swaps `.mcp.json` → `.mcp.json.sift` so the MCP servers spawn over SSH inside SIFT (where Volatility/Hayabusa/Velociraptor/YARA are natively present); restores `.mcp.json` on exit. **Hypervisor:** VMware Workstation only (`scripts/find-evil-sift` lines 10–12); a VirtualBox path is stubbed but not implemented.
- Verify a submitted manifest cryptographically (offline): the agent calls the `manifest_verify` MCP tool from `findevil-agent-mcp`. CLI fallback: `uv run --directory services/agent_mcp python -m findevil_agent_mcp.server` then drive over stdio.
- Pre-A2 launchers (`./find-evil serve|run|verify`, `find-evil` console script, `openclaw run`) are deprecated and not on the critical path.

**Build swarm (Spec #1, interpret through Amendment A1):**
- Pre-flight + start a nightly run: `bash scripts/swarm-start.sh` (verifies Postgres + git clean, then `cd services/swarm && uv run python -m findevil_swarm.main run …`)
- Dry-run gate for a specific week: `cd services/swarm && uv run python -m findevil_swarm.main run --week 4 --dry-run-gate`
- Resume after laptop sleep: `cd services/swarm && uv run python -m findevil_swarm.main run --resume`
- Morning triage status: `bash scripts/swarm-status.sh`
- Postgres DAG state lives in Docker Compose service: `docker compose -f docker/swarm-postgres.yml up -d`

  Note: the swarm package is `findevil_swarm` (matches the `findevil_*` naming convention shared with `findevil_agent` + `findevil_agent_mcp`). The original Spec #1 / build-swarm-plan TDD doc imports from `services.swarm.*` — that's a known **plan-vs-code divergence** (the plan was written with the `services.swarm.*` namespace; the code shipped under `findevil_swarm.*` for consistency with the other Python packages). When in doubt, match `scripts/swarm-start.sh` line 105 — that's the canonical invocation.

**Autonomous-loop harness (lightweight alternative to the swarm):**
- Driver: `python scripts/autonomous-loop.py [--max-hours N] [--dry-run]` reads the user-level `memory/project_autonomous_queue.md`, picks the highest-priority unblocked item (skipping the `### Hard blockers (require user)` section), and spawns `claude -p --permission-mode acceptEdits` headless per item until the queue is exhausted, the wall-clock cap is hit, or a 429 / `usage limit reached` / `reached your usage limit` is detected. Auth inherits from the `claude` CLI subprocess (Amendment A1 subscription path; no API key).
- When to use which: the swarm is the heavyweight nightly-cron PR-generator (Postgres-checkpointed, per-PR worktrees, critic gate, draft PRs for morning triage); `autonomous-loop.py` is the lightweight queue-driven sequential runner (one Python process, no Postgres, no worktrees, just claude-per-item until the queue is empty). Both inherit subscription auth via the `claude` CLI; pick by whether you want PRs (swarm) or commits-on-current-branch (autonomous-loop).

**Sandbox layers (Spec #3):**
- L1 locally: `docker compose -f docker/l1-compose.yml up --build --exit-code-from l1` (base image is `docker/l1-devbase.Dockerfile`)
- L2 locally (requires Sysbox installed): `bash scripts/l2-dfir-smoke.sh` (or the raw `docker run --runtime=sysbox-runc …` it wraps; base image is `docker/l2-siftlite.Dockerfile`)
- L3 Packer build of the warm qcow2: `packer build packer/sift-microvm.pkr.hcl` (reads `sift-2026.03.24.ova` from repo root)
- L3 goldens in CI: `bash scripts/l3-run-goldens.sh` (expects the warm qcow2 in GHA cache)

**Workflows and CI (Spec #4):**
- Static-check workflow files locally: `actionlint .github/workflows/*.yml`
- Simulate a workflow job locally: `act -j l0-static`
- Cut a weekly release: `git tag v<N> && git push origin v<N>` (triggers `release.yml`, which gates on L3 green)
- Cut the final submission: `git tag v-submit && git push origin v-submit` (triggers `devpost-submit.yml` after `release.yml` succeeds)

## How to code in this repo (the four principles)

Adapted from Andrej Karpathy's observations on LLM coding pitfalls — these behavioral guardrails apply to **both the live agent and the build swarm**. They bias toward caution over speed; for trivial tasks use judgment.

**1. Think before coding.** State assumptions explicitly. If multiple interpretations exist, present them — don't pick silently. If a simpler approach exists, say so. If something is unclear, stop, name what's confusing, ask. Particularly important under Amendment A2: *every* tool call we make is on someone's evidence — uncertainty must surface, not be papered over.

**2. Simplicity first.** Minimum code that solves the problem. No features beyond what was asked. No abstractions for single-use code. No "flexibility" or "configurability" that wasn't requested. No error handling for impossible scenarios. If you write 200 lines and it could be 50, rewrite it. Test: would a senior DFIR engineer say this is overcomplicated?

**3. Surgical changes.** Touch only what you must. Don't "improve" adjacent code, comments, or formatting. Don't refactor things that aren't broken. Match existing style even if you'd do it differently. If you notice unrelated dead code, mention it — don't delete it. Remove imports/variables that *your* changes made unused; never pre-existing dead code unless asked. Every changed line traces directly to the user's request.

**4. Goal-driven execution.** Transform tasks into verifiable goals. "Add a tool" → "write the typed Input/Output, the failing integration test, and the boundary error tests; then make them all green." For multi-step work state a brief plan and verify each step before moving on. Strong success criteria let you loop independently; weak ones ("make it work") require constant clarification.

These principles are *working* when: diffs are small and focused, fewer rewrites are needed, and clarifying questions come *before* implementation rather than *after* mistakes.

## Conventions

- **TDD loop is mandatory for every plan task.** Write failing test → run to confirm RED → implement → run to confirm GREEN → commit with the exact message the plan specifies. One commit per plan task; never batch.
- **Conventional Commits:** `feat(scope):`, `test(scope):`, `chore(scope):`, `fix(scope):`, `docs(scope):`. Scope examples from existing commits: `mcp`, `swarm`, `sandbox`, `ci`, `plan`, `amendment A1`.
- **Never use `--no-verify`, `--no-gpg-sign`, or `git commit --amend`** in plan execution. If a hook fails, fix the root cause and make a new commit.
- **Pinned dependency versions.** Specs pin exact versions (e.g. `rmcp = "=0.16.0"`, `evtx = "=0.11.2"`). Upgrading without updating the spec is a silent contract break — but when the code already ships a different pin (see "Spec/code divergences"), the shipped pin wins and the spec text is the thing to update.
- **DFIR vocabulary, not software vocabulary.** In UI copy and docs use: **Case** (not session/run/job), **Observable** (not file/path/blob — the *generic* container), **Task** (not step/action), **Finding** (not result/hit-as-software-result), **Verdict** (not conclusion/summary), **Confidence** (not score/certainty). Three specific carve-outs: (1) **"artifact" is correct** in the DFIR-canonical sense — "artifact class" (Prefetch/MFT/EVTX/Amcache as evidence types) is the SOUL.md ≥2-corroboration vocabulary and must NOT be massaged into "Observable class"; (2) **"hit"** is correct for rule-engine matches (YARA hit, Sigma rule hit) since that's the industry term in those contexts; (3) **"investigation" is correct as the activity-noun** (the verb form is "investigate") — `the investigation flow`, `the investigation took 4 hours`, `end-of-investigation self-score` are all fine. The unit of work is still **Case** (with `case_id`); "investigation" means the *act* of working a case, never the case itself ("the investigation directory" is wrong; say "the case directory"). The forbidden usages are the *software* meanings: a build "session", a CI "job", a search "hit". A vocab-audit sprint is budgeted for week 7 (and partially executed in commit history — grep `vocab-audit`).
- **Python tooling:** `uv` for envs and lockfile; `pytest` for tests; `ruff` for lint/format. Python 3.11.
- **Rust tooling:** `cargo test --workspace --locked`, `cargo clippy --deny warnings`. Rust 1.88 (rust-toolchain.toml is authoritative; Spec #2 §16's 1.83 pin is superseded — see "Spec/code divergences" §1 below).
- **Node tooling:** `pnpm` with `--frozen-lockfile`; `tsc --noEmit` in L0; `pnpm test` in L1. Node 20.

## Sandbox layer cheat sheet (Spec #3)

| Layer | Runtime | Budget | Blocks merge? |
|---|---|---|---|
| L0 | GHA `ubuntu-24.04`, no containers | 30–60s | Yes |
| L1 | Docker Compose + GHA standard runner | 2–5min | Yes |
| L2 | Sysbox runtime (rootless systemd+FUSE) | 5–10min | No (advisory on PRs) |
| L3 | QEMU microvm + qcow2 snapshot-restore on GHA KVM larger runner | ~5–20min | Yes for **releases**, nightly on `main` |

L3's warm `.qcow2.zst` is built once by Packer from `sift-2026.03.24.ova` and cached via `actions/cache`. The OVA itself is in `.gitignore` (`*.ova`) and never committed.

## Large files to never commit

`.gitignore` already excludes `*.ova`, `*.qcow2`, `*.vmdk`, `*.vdi`, `*.E01`, `*.dd`, `*.raw`, `*.mem`, `*.aff`, `*.aff4`, `*.vhd`, `*.vhdx`, `target/`, `node_modules/`, `.venv/`, `__pycache__/`, `.next/`, `dist/`, `state/`, `checkpoints/`, and `*.sqlite`. Evidence images (NIST CFReDS Hacking Case, OTRF datasets) are pulled by L3 scripts at CI time — they never enter the git tree.

## Spec/code divergences (code wins)

Specs were written 2026-04-23; code has been shipped since 2026-04-24. Where they disagree, the shipped code + its pin files are authoritative. Update the spec if the divergence is intentional; update the code if it's drift. Known cases:

- **Rust toolchain: spec pins 1.83, repo ships 1.88.** `Cargo.toml` (`rust-version = "1.88"`) and `rust-toolchain.toml` (`channel = "1.88.0"`) both note the bump was needed because transitive deps (e.g. `clap_builder` 4.6) now require edition-2024 stabilization (Rust ≥1.85). Spec #2 §16 is superseded; don't downgrade.
- **`Cargo.lock` is committed.** `.gitignore` has an explicit comment: "Cargo.lock IS committed — this is an application workspace with a shipped binary (findevil-mcp), not a library." Don't add it back to the ignore list.
- **Python CLI package is `findevil_agent`, not `services.agent`.** Tests + entry points use `findevil_agent.*` — never `services.agent.*`. The `cli.py` submodule was dropped under A2 (Claude Code IS the orchestrator). `Dockerfile` wrapper + `scripts/build-deb.sh` cut 2026-04-27 (PR #4) per `docs/runbooks/dockerfile-a2-decision.md`. L0 `amendment-a2-guard` + L1 `scripts/divergence-smoke.py` §3 fail CI if `findevil_agent.cli` re-appears.
- **Rust MCP tool count is 13, not 11.** Spec #2 §6 enumerates 11; we ship `vol_psscan` as the 12th for DKOM cross-validation against `vol_pslist`, plus `vol_psxview` as the 13th to cross-reference process views after a DKOM divergence. The tools are deliberately redundant (active-list walk vs pool-memory signature scan vs cross-view check); divergence between them IS the T1014/Rootkit finding. Don't fold them.
- **`rmcp` is intentionally NOT a runtime dependency.** Spec #2 §4.1 lists `rmcp 0.16.x`; we ship a hand-rolled stdio JSON-RPC 2.0 (MCP 2024-11-05) in `services/mcp/src/server.rs` for wire-format stability and Python-server dispatch parity. `Cargo.toml` line 27 keeps the `rmcp` line commented as a deliberate marker. See `services/mcp/README.md`.
- **Swarm package is `findevil_swarm`, not `services.swarm`.** Spec #1 / `docs/plans/2026-04-23-build-swarm-plan.md` use `services.swarm.*`; code ships under `findevil_swarm.*` (matching `findevil_agent`/`findevil_agent_mcp`/`findevil-mcp`). Canonical invocation: `scripts/swarm-start.sh:105` (`cd services/swarm && exec uv run python -m findevil_swarm.main run "$@"`).
- **A3 MemoryStore: FTS5 phrase-quoting + Python-side sort.** Plan Task 1.1/spec §2.4 specified raw `params=[query]` MATCH + `ORDER BY score`. Shipped `services/agent/findevil_agent/memory/store.py` phrase-quotes (`fts_query = '"' + query.replace('"','""') + '"'`) — required so queries like `evil.com` or `T1059.001` don't trip `fts5: syntax error near "."` — and re-sorts by combined `confidence` so decay breaks BM25 ties. Plan + spec updated; multi-word recall is conservative phrase-match.
- **A3 audit-log push: SSE, not WebSocket.** Plan Task 4.2 specified a WebSocket; PR #7 (`281d26f`) shipped SSE. Flow is strictly server→client, App Router doesn't natively support WS upgrade, SSE is one route handler. Live handler: `apps/web/app/api/audit/route.ts` (Node runtime, SSE MIME, 15s keepalive comment frame). Iterator: `apps/web/lib/audit-tail.ts`. Consumers: `new EventSource("/api/audit?case=…")` + `addEventListener("audit_line", …)`. Don't "upgrade" back to WS without a spec amendment naming a concrete client→server message.
- **A5 OTS removal: legacy specs (M2 spec, A2 §2.3) still reference `ots_stamp`/`ots_verify`/Bitcoin as design-era behavior.** Code has cut all five touchpoints (`crypto/ots.py`, both MCP tool modules, `opentimestamps-client` dep, orchestrator + report-renderer + smoke refs). Chain is 3 tiers; `docs/cryptographic-attestation.md` now documents the post-A5 trade-off. Code wins for any remaining legacy-spec conflict. No A5 spec doc written yet.

When you spot a new divergence, append it here (one bullet, one line) before continuing with the task — so the next session doesn't re-litigate the same decision.

## Memory system

User-level auto-memory lives at `C:/Users/newbi/.claude/projects/C--Users-newbi-Desktop-PUG-Projects-SANS-Hackathon/memory/` and is auto-loaded into every session. The index (`MEMORY.md`) points to per-topic memory files covering: automation scope, top competitors, DFIR tooling picks, swarm architecture, sandbox stack, judging signals, crypto chain-of-custody stack, MCP Apps readiness, adversarial-agents pattern, the Option B credential decision, and Devpost rules compliance + new intel. Read the index at session start if you need historical context; update the relevant memory file (don't invent a new one) when facts change.


## External "Protocol SIFT" reference (not authoritative)

The full Protocol SIFT integration material lives at `docs/references/protocol-sift-integration-reference.md`. It uses a different conceptual frame than this repo's authoritative spec/plan stack — **where the two disagree, the specs win.** Three reconciled contradictions to keep in mind before acting on anything from that doc:

- Its example `settings.json` deny-list blocks `curl` and `wget`, but `scripts/install.sh` (Amendment A1 §3.2) and `scripts/l3-run-goldens.sh` (Spec #3 §4.4) both rely on curl. Treat that deny-list as illustrative, not a drop-in config — the repo's real permissions live in `.claude/settings.json` per Spec #4.
- Its `~/.claude/skills/volatility/SKILL.md` pattern duplicates the typed MCP tool surface pinned in Spec #2 §6 (`services/mcp/src/tools/vol_pslist.rs`, `vol_malfind.rs`). Volatility is invoked as a subprocess from the Rust MCP server, not as a Claude skill.
- Its `/ralph-loop` self-learning Stop hook is not defined in any spec, plan, or memory file in this repo. Background reading only; wiring it in needs its own design doc first.

https://www.anthropic.com/engineering/managed-agents
