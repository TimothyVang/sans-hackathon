# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. Under **Amendment A2** (2026-04-25, active) Claude Code IS the Product's primary interface — when a SANS judge runs `scripts/find-evil` or `claude-code .` from this repo, the session you are reading is what executes the investigation.

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
| `findevil-mcp` | Rust (`services/mcp/`) | DFIR tool surface — `case_open`, `evtx_query`, plus 10 more (`mft_timeline`, `hayabusa_scan`, `vol_pslist`, `vol_psscan`, `vol_malfind`, `yara_scan`, `usnjrnl_query`, `registry_query`, `prefetch_parse`, `vel_collect`). Read-only on evidence; SHA-256 every output. The `vol_pslist` + `vol_psscan` pair is deliberately redundant — pslist walks the active list, psscan signature-scans EPROCESS pool memory; divergence between the two is the textbook DKOM/T1014 (Rootkit) signature. |
| `findevil-agent-mcp` | Python (`services/agent_mcp/`) | Crypto + ACH plumbing — `audit_append`, `audit_verify`, `manifest_finalize`, `manifest_verify`, `ots_stamp`, `ots_verify`, `verify_finding`, `detect_contradictions`, `judge_findings`, `correlate_findings`. |

The investigation flow is roughly: `case_open` → split into Pool A (persistence) + Pool B (exfil) subagents → each pool runs DFIR tools and emits Findings (each citing a `tool_call_id`) → `detect_contradictions` → analyst resolves → `verify_finding` re-runs each cited tool → `judge_findings` (credibility-weighted merge) → `correlate_findings` → `manifest_finalize` (signs the run) → `ots_stamp` (Bitcoin anchor). The terminal beat map for the judge demo lives in Amendment A2 §2.3.

## Project state

This is the SANS **Find Evil!** hackathon submission (deadline **2026-06-15 22:45 CDT**). Week-1 implementation is underway — `services/mcp/` (Rust MCP server with `evtx_query` and other tools), `services/agent/` (Python package, AgentEvent union, M2 crypto layer, M4 ACH stack with verifier/judge/contradiction/pools/correlator, `mcp_client.py` Python↔Rust bridge), and `services/swarm/` scaffolding all exist. `packer/`, `docker/`, `scripts/`, `goldens/`, `.github/workflows/`, root `Cargo.toml`/`Cargo.lock`/`rust-toolchain.toml`, and a root-level production `Dockerfile` are all in place. Check `git log --oneline -20` before assuming anything is missing.

Before writing code of your own, **read the relevant spec and plan** for the subsystem you are touching. The specs define exact file paths, pinned dependency versions, and TDD task sequences; diverging from them silently creates integration mismatches with other subsystems. When a spec and the current code disagree, the **code + its committed pin files win** — see "Spec/code divergences" below for known cases.

## Vendored reference clones (never ship, never edit, never import)

Four top-level directories are external research clones that live in-repo for reference reading only. All are listed in `.gitignore` (lines 72–76: "External reference clones — research-only, never ship in submission"):

- **`openclaw/`** — the Openclaw coding-agent harness we invoke via `openclaw run --case X.e01` as one of the Product's entry points. Has its own `CLAUDE.md`, `package.json`, `pyproject.toml`, `src/` tree. **Treat as opaque.**
- **`hermes-agent/`** — the Hermes MCP sidecar (cross-case L3 memory, per Spec #2 §4 Layer 4). Referenced; not modified.
- **`Linear-Coding-Agent-Harness/`** — reference harness for the build-swarm worker pattern.
- **`.playwright-mcp/`** — scratch data from a competitor-recon session.

Our code imports none of these directly. When a judge runs the Product, only the contents of this repo's **non-vendored** tree ship (plus the `.deb` and Docker image produced by `release.yml`). A future session that edits files inside a vendored directory is almost certainly making a mistake — check `.gitignore` first.

## Quickstart for the impatient

If you want to run the agent against evidence right now, see **`QUICKSTART.md`** at the repo root. Three steps: pick environment (SIFT VM or local), open Claude Code, prompt `investigate <path>`. Everything else in this file is reference material.

For false-positive prevention strategy and analyst checklists, see **`docs/false-positives.md`** — three architectural layers, four operational habits, plus specific FP traps and how to avoid them.

For an example end-to-end investigation report (real evidence, real findings), see **`docs/reports/2026-04-26-srl2018-dc-investigation.md`** — covers the SRL-2018 SANS HACKATHON-2026 dataset, includes a CONFIRMED DKOM finding (MITRE T1014).

## Document hierarchy (authoritative order)

Read these in precedence order. Later documents override earlier ones only where explicitly noted:

1. **`docs/superpowers/specs/2026-04-23-find-evil-automation-master-design.md`** — master design. Defines the 4-subsystem decomposition and the 4 moonshots (M1 leaderboard, M2 crypto chain-of-custody, M3 MCP App widgets, M4 ACH competing-hypothesis agents).
2. **`docs/superpowers/specs/2026-04-23-amendment-option-b-claude-code-mode.md`** — **amendment A1, active.** Overrides the swarm's credential/budget architecture. LiteLLM proxy, `services/swarm/budget.py`, and USD caps are removed; workers use the user's Claude Code subscription via `claude` CLI. The Product accepts three credential modes (`CLAUDE_CODE_OAUTH_TOKEN`, interactive `~/.claude/` session, `ANTHROPIC_API_KEY`).
3. **`docs/superpowers/specs/2026-04-25-amendment-a2-claude-code-primary-interface.md`** — **amendment A2, active.** Drops the custom Python orchestrator (`graph.py`, `api.py`, `cli.py`, `supervisor.py`, specialists/) — Claude Code IS the orchestrator. Adds `services/agent_mcp/` (Python MCP server wrapping M2 + M4 stacks) and `.mcp.json` at repo root registering both MCP servers. `apps/web/` Next.js SPA + `apps/mcp-widgets/` deferred to week-7 polish bonus, NOT on the critical path.
4. **Per-subsystem specs** (in `docs/superpowers/specs/`):
   - `2026-04-23-layered-test-sandbox-design.md` — Spec #3 (L0-L3 sandbox; blocks all other work).
   - `2026-04-24-autonomous-build-swarm-design.md` — Spec #1 (build swarm; interpret through A1).
   - `2026-04-25-the-product-design.md` — Spec #2 (the DFIR tool judges run).
   - `2026-04-26-orchestration-glue-design.md` — Spec #4 (GHA CI; `budget-guard.yml` is a no-op under A1 unless `ANTHROPIC_API_KEY` is set).
5. **Implementation plans** (in `docs/superpowers/plans/`) — one per spec, each step written as a TDD checkbox with the exact failing test → implement → commit sequence.
6. **`BUILD_PLAN_v2.md`** — 9-week roadmap and the v2 architecture the swarm works against. Still authoritative for DFIR fundamentals, rubric analysis, and the demo script.
7. **`Find_Evil_Research_and_Build_Plan.docx`** — v1 research doc; authoritative only for what v2 doesn't contradict.

## Repository layout (current)

Shipped tree — these are the directories that end up in the submission:

```
.
├── Cargo.toml / Cargo.lock / rust-toolchain.toml   # Rust workspace (members = [services/mcp]); Cargo.lock IS committed (app, not library)
├── Dockerfile                                      # Production multi-stage image → ghcr.io/find-evil/find-evil:v<N>
├── LICENSE                                         # Apache-2.0
├── BUILD_PLAN_v2.md / Find_Evil_Research_and_Build_Plan.docx
├── SUBMISSION_NOTES.md                             # Stub; edit before cutting v-submit
├── sift-2026.03.24.ova                             # 9.3 GB SIFT VM image — Packer input; gitignored (*.ova)
├── agent-config/                                   # Runtime DFIR agent identity (SOUL/AGENTS/TOOLS/MEMORY/HEARTBEAT/JUDGING/PLAYBOOK)
├── docs/superpowers/specs/ + plans/                # 5 specs (incl. Amendment A1) + 4 TDD plans
├── services/mcp/                                   # Rust MCP server (rmcp-based; evtx/duckdb/rs_merkle linked; others subprocess-only)
├── services/agent/                                 # Python package findevil_agent — M2 crypto + M4 ACH (FastAPI/LangGraph DROPPED under A2)
├── services/agent_mcp/                             # Python MCP server (A2) wrapping M2+M4 as 10 typed tools for Claude Code
├── services/swarm/                                 # Python build swarm (Option B — Claude CLI subagents)
├── .mcp.json                                       # A2: registers findevil-mcp (Rust) + findevil-agent-mcp (Python) for auto-spawn
├── apps/web/ + apps/mcp-widgets/                   # Next.js SPA + M3 widgets — DEFERRED to bonus per A2 §2.1
├── packer/sift-microvm.pkr.hcl                     # L3 warm-qcow2 build from the OVA
├── docker/                                         # l1-compose.yml, l1-devbase.Dockerfile, l2-siftlite.Dockerfile, swarm-postgres.yml
├── scripts/                                        # swarm-start, swarm-status, l2-dfir-smoke, l3-run-goldens, fetch-fixtures,
│                                                   # build-deb, package-devpost, push-leaderboard-score, competitor-watch,
│                                                   # setup-branch-protection, sift-provision, verify-sandbox, json-to-benchmark-csv.py
│                                                   # find-evil-auto + find_evil_auto.py (Tesla-mode end-to-end orchestrator),
│                                                   # fleet_investigate.py + fleet_correlate.py + render_fleet_report.py (multi-host pipeline),
│                                                   # render_report.py + _report_style.css (per-case PDF rendering)
├── goldens/                                        # nist-hacking-case/, synthetic-benign/ — L3 golden fixtures
└── .github/workflows/                              # l0/l1/l2/l3 + release + competitor-watch + devpost-submit + budget-guard
```

The Python CLI inside the shipped Docker image is invoked as `find-evil` (see `Dockerfile` line 74–78: `exec python3 -m findevil_agent.cli "$@"`). In dev, that's `uv run python -m findevil_agent.cli …`.

## The 4 subsystems (master design §3)

```
#3 Sandbox (L0-L3) ──┐
                     ├──► #1 Build Swarm ──► #2 Product ──► #4 Orchestration Glue
                     └──► #2 Product (directly — sandbox also gates Product CI)
```

- **#3 Sandbox** blocks everything else. L0 lint, L1 unit/build (Docker Ubuntu 22.04), L2 SIFT-lite (Sysbox runtime, advisory), L3 full SIFT VM parity (QEMU microvm + qcow2 snapshot-restore, Packer-built from `sift-2026.03.24.ova`, on GHA KVM larger runners).
- **#1 Build Swarm** is invisible to judges — writes code overnight into draft PRs. LangGraph supervisor + Claude CLI subagents + one git worktree per PR + critic subagent gate. **Option B (A1):** runs on user's Claude Code subscription, not a metered API key.
- **#2 Product** is the submission. Under **A2** the layers collapse to: evidence vault → SIFT tool subprocesses → two MCP servers (Rust DFIR tools + Python crypto/ACH wrappers) → Claude Code (acts as supervisor + ACH pool subagents + audit-log driver). Primary entry point: **`scripts/find-evil`** (or `claude-code .` directly). The Next.js SPA / `find-evil serve` / `find-evil run` / `find-evil verify` are not on the critical path; the equivalent verification is `manifest_verify` + `ots_verify` MCP tools.
- **#4 Orchestration Glue** is thin CI: 9 GHA workflows, branch protection, release pipeline, Devpost submission zip on `v-submit` tag.

## Non-negotiable invariants

These show up across multiple specs and the agent-config files. Violating any of them breaks the judging story or an integration contract:

- **No `execute_shell` MCP tool, ever.** The Rust MCP server's typed surface (12 tools — the 11 from Spec #2 §6 plus `vol_psscan` for DKOM cross-validation) is deliberately narrow. Adding shell pass-through undoes the "reduces the attack surface" pitch.
- **Every Finding cites a `tool_call_id`.** The verifier node vetos any Finding without one (Spec #2, `agent-config/SOUL.md`). UI chips render `[confirmed · tool · sha256]` per finding.
- **Epistemic hierarchy is strict.** `CONFIRMED` (backed by tool output) > `INFERRED` (≥2 confirmed facts, labeled) > `HYPOTHESIS` (prefixed "hypothesis:"). Nothing else is legal.
- **AGPL/GPL tools (Hayabusa, Chainsaw, Volatility3, Velociraptor, YARA) are subprocess-only — never linked.** Violating this contaminates the submission license (must be MIT or Apache-2.0 per SANS rules).
- **Evidence is read-only.** Original `.e01` opened via libewf; write-only working dir elsewhere. No tool mutates evidence. SHA-256 of image verified at `case_open`.
- **Hash-chained audit JSONL is append-only.** Each line has a `prev_hash` field linking to the previous line. Rewriting history breaks the M2 crypto chain-of-custody pitch ("FRE 902(14) self-authenticating"). The full five-link chain (audit prev_hash → rs_merkle → sigstore → OpenTimestamps → Bitcoin) is documented in `docs/cryptographic-attestation.md`; rubric criterion #5 ("Audit Trail Quality") points there.
- **Draft PRs only.** The build swarm never auto-merges or force-pushes `main`. Human merges every PR after morning triage.
- **Execution claims need ≥2 artifact classes** (Prefetch + Amcache+ShimCache, or EDR telemetry). Amcache alone is insufficient — it's catalog-registration time, not execution.
- **All timestamps UTC, ISO-8601, trailing `Z`.** SHA-256 preferred over MD5. Never assert attribution.
- **Judge narrative:** "orchestrator that reduces friction," never "autonomous responder." Rob Lee's explicit preference (memory: `project_judging_signals.md`).

## Credential modes (Amendment A1)

The Product (`scripts/install.sh`) detects three credential paths in priority order:

1. `CLAUDE_CODE_OAUTH_TOKEN` env var (from `claude setup-token`) — non-interactive, script-friendly. Preferred for judges with a subscription.
2. Interactive Claude Code session (`~/.claude/` populated via `claude auth login`) — used in dev.
3. `ANTHROPIC_API_KEY` env var — direct metered API, used when no Claude Code is available.

**For the build swarm specifically:** only modes 1 and 2 apply. Option B removed all LiteLLM/USD-cap code; rate-limit handling is `services/swarm/session_guard.py`, which halts the supervisor cleanly on 429 and resumes from the Postgres checkpoint the next night. There is no in-flight retry.

## Commands

None of these succeed today — the code they target doesn't exist yet. They are the canonical commands the specs and plans will produce code for. Quote them verbatim so swarm-generated code and human work use the same invocations.

**Rust MCP server (`services/mcp/`):**
- Build: `cargo build --workspace --release --locked`
- Lint: `cargo check --workspace && cargo clippy --workspace --all-targets -- -D warnings`
- All tests: `cargo test --workspace --locked`
- Single test (named fn in an integration test file): `cargo test -p findevil-mcp --test tool_smoke test_case_open_returns_handle`
- Single crate's unit tests: `cargo test -p findevil-mcp --lib`

**Python agent + swarm (`services/agent/`, `services/swarm/`):**
- Env sync: `uv sync` (root `pyproject.toml` is a uv workspace)
- Lint + format check: `ruff check . && ruff format --check .`
- All tests: `uv run pytest -xvs --cov`
- Single file: `uv run pytest tests/swarm/test_package_imports.py -v`
- Single test function: `uv run pytest tests/agent/test_graph_smoke.py::test_kill_resume_restores_state -v`
- Run the agent graph directly (dev): `uv run python -m findevil_agent.cli run --case path/to/case.e01` (the installed console script is `find-evil`; see `Dockerfile` line 74)

**Next.js web + MCP widgets (`apps/web/`, `apps/mcp-widgets/`):**
- Install: `pnpm install --frozen-lockfile`
- Typecheck: `pnpm -r exec tsc --noEmit`
- Lint: `pnpm -r lint`
- Build: `pnpm -r build`
- Test all: `pnpm -r test`
- Test one file (web): `pnpm --filter @findevil/web test -- components/narrative/StreamingSpanTree.test.tsx`

**Launchers under Amendment A2 (Claude Code as primary interface):**
- Open an investigation, **local mode** (the demo entry point): `scripts/find-evil` or `claude-code .` from the repo root. `.mcp.json` auto-spawns both MCP servers locally. Use this when the DFIR tool binaries (Hayabusa, Volatility3, Velociraptor) are installed on the host machine.
- Open an investigation, **SIFT-VM mode** (Tesla-mode automation against the SANS-blessed environment): `bash scripts/find-evil-sift` from the repo root. Pre-flight: import `sift-2026.03.24.ova` in VirtualBox, port-forward 2222 → 22, run `bash scripts/sift-vm-setup.sh` once inside the VM, install an SSH key. The launcher swaps `.mcp.json` → `.mcp.json.sift` so the MCP servers spawn over SSH inside SIFT (where Volatility/Hayabusa/Velociraptor/YARA are natively present); restores `.mcp.json` on exit.
- Verify a submitted manifest cryptographically (offline): the agent calls the `manifest_verify` MCP tool from `findevil-agent-mcp`. CLI fallback: `uv run --directory services/agent_mcp python -m findevil_agent_mcp.server` then drive over stdio.
- Verify the Bitcoin anchor: `ots verify run.manifest.ots` (the third-party `opentimestamps-client` CLI; the agent uses the same logic via `ots_verify` MCP tool).
- Pre-A2 launchers (`./find-evil serve|run|verify`, `find-evil` console script, `openclaw run`) are deprecated and not on the critical path.

**Build swarm (Spec #1, interpret through Amendment A1):**
- Pre-flight + start a nightly run: `bash scripts/swarm-start.sh` (verifies Postgres + git clean, then invokes `services/swarm/main.py`)
- Dry-run gate for a specific week: `uv run python -m services.swarm.main --week 4 --dry-run-gate`
- Resume after laptop sleep: `uv run python -m services.swarm.main --resume`
- Morning triage status: `bash scripts/swarm-status.sh`
- Postgres DAG state lives in Docker Compose service: `docker compose -f docker/swarm-postgres.yml up -d`

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
- **Rust tooling:** `cargo test --workspace --locked`, `cargo clippy --deny warnings`. Rust 1.83.
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
- **Python CLI package is `findevil_agent`, not `services.agent`.** The shipped `Dockerfile` calls `python3 -m findevil_agent.cli`; dev invocations should match. The `services/agent/` directory hosts the package source.
- **Rust MCP tool count is 12, not 11.** Spec #2 §6 enumerates 11; we shipped a 12th — `vol_psscan` — to support DKOM cross-validation against `vol_pslist`. The pair is deliberately redundant (active-list walk vs pool-memory signature scan); divergence between them IS the T1014/Rootkit forensic finding. Don't remove psscan or fold it into pslist.

When you spot a new divergence, append it here (one bullet, one line) before continuing with the task — so the next session doesn't re-litigate the same decision.

## Memory system

User-level auto-memory lives at `C:/Users/newbi/.claude/projects/C--Users-newbi-Desktop-PUG-Projects-SANS-Hackathon/memory/` and is auto-loaded into every session. The index (`MEMORY.md`) points to per-topic memory files covering: automation scope, top competitors, DFIR tooling picks, swarm architecture, sandbox stack, judging signals, crypto chain-of-custody stack, MCP Apps readiness, adversarial-agents pattern, the Option B credential decision, and Devpost rules compliance + new intel. Read the index at session start if you need historical context; update the relevant memory file (don't invent a new one) when facts change.


---

## Appendix: external "Protocol SIFT" reference (not authoritative)

The content below was appended from external research material and uses a different conceptual frame ("Protocol SIFT") than the authoritative spec/plan stack above. Where the appendix and the specs disagree, **the specs win**. Known contradictions to reconcile before acting on any appendix instruction:

- The example `settings.json` deny-list blocks `curl` and `wget`, but `scripts/install.sh` (Amendment A1 §3.2) and `scripts/l3-run-goldens.sh` (Spec #3 §4.4) both rely on curl. Treat that deny-list as illustrative, not a drop-in config — the repo's real permissions will live in `.claude/settings.json` per Spec #4.
- The `~/.claude/skills/volatility/SKILL.md` pattern duplicates the typed MCP tool surface pinned in Spec #2 §6 (`services/mcp/src/tools/vol_pslist.rs`, `vol_malfind.rs`). Volatility is invoked as a subprocess from the Rust MCP server, not as a Claude skill.
- The `/ralph-loop` self-learning Stop hook is not defined in any spec, plan, or memory file in this repo. Treat it as background reading only; wiring it in needs its own design doc first.

To provide Claude Code with the full context of **Protocol SIFT**, you should create several specific files in your project root or the `~/.claude/` directory. Claude Code is designed to automatically ingest these files at the start of every session to establish its role, rules, and tool knowledge.

The following sections contain the essential text you need to feed into Claude Code.

### 1. Authoritative Project Memory (`CLAUDE.md`)
This file is the "brain" of the integration. It defines the AI's role and operational boundaries.

```markdown
# Protocol SIFT: Authoritative Project Memory

## WHY (Purpose)
Protocol SIFT is a framework for orchestrating the 400+ forensic tools in the SANS SIFT Workstation ecosystem. It shifts the analyst from manual execution to high-level orchestration to match the speed of modern AI-driven adversarial attacks.

## WHAT (Environment)
- **Role**: Principal DFIR Orchestrator.
- **Environment**: SANS SIFT Workstation (Ubuntu 22.04 LTS).
- **Evidence Mode**: Strict read-only handling to maintain the chain of custody.

## HOW (Operational Rules)
- **Autonomous Operation**: Run workflows start-to-finish without check-ins or confirmation prompts unless a destructive action is detected.
- **Hierarchical Context**: Use progressive disclosure. Read `SKILL.md` files in the `skills/` directory only when specific tools are required.
- **Standard Formatting**: Timestamps must always be in UTC.
- **Chain of Custody**: Document all actions in `./analysis/forensic_audit.log` via automated hooks.

## Routing Table (Core Skills)
- **Timeline Analysis**: Use Plaso (`log2timeline.py`, `psort.py`).
- **Memory Forensics**: Use Volatility 3.
- **Filesystem**: Use The Sleuth Kit (TSK) tools like `fls` and `icat`.
- **Windows Artifacts**: Use Eric Zimmerman's (EZ) Tools natively via .NET.
- **Threat Hunting**: Deploy YARA rules across memory and disk.
```

---

### 2. Global Permissions and Auditing (`settings.json`)
This file configures the underlying software engine to allow forensic tools to run without constant "Allow?" prompts.

```json
{
  "permissions": {
    "allowedTools": [
      "Read",
      "Write(./analysis/*)",
      "Write(./reports/*)",
      "Bash(log2timeline.py *)",
      "Bash(psort.py *)",
      "Bash(volatility *)",
      "Bash(fls *)",
      "Bash(icat *)",
      "Bash(yara *)",
      "Bash(exiftool *)",
      "Bash(md5sum *)",
      "Bash(grep *)"
    ],
    "deny": [
      "rm -rf",
      "dd",
      "wget",
      "curl",
      "WebFetch"
    ],
    "defaultMode": "acceptEdits"
  },
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "echo \"$(date -u): $CONVERSATION_SUMMARY\" >> ./analysis/forensic_audit.log"
      }
    ]
  }
}
```
**

---

### 3. Progressive Disclosure Architecture
To manage the complexity of SIFT, you must use **Progressive Disclosure**. Instead of one giant file, place tool-specific instructions in a `skills/` folder.

**Skill Template (`~/.claude/skills/volatility/SKILL.md`):**
```markdown
---
name: memory-forensics
description: Use for analyzing RAM captures via Volatility 3. Triggers on "memory", "dump", or "process list".
allowed-tools: Bash, Read
---
# Volatility 3 Memory Forensics
1. Always begin by detecting the OS profile using `imageinfo`.
2. Identify anomalies by comparing `pslist` and `psscan` (hidden processes).
3. Check for code injection using the `malfind` plugin.
4. Extract suspicious processes using `procdump` to the `./exports/memdump/` directory.
```
**

---

### 4. Self-Learning Loop (Ralph Wiggum)
For long-running refactors or complex investigations, Protocol SIFT utilizes a **Self-Learning Loop**. This is a **Stop hook** that prevents Claude from exiting if a task is incomplete or if errors persist.

**Mechanism:**
- **Trigger**: The `/ralph-loop` initiates the session.
- **Interceptor**: A Stop hook blocks the exit and re-injects the original prompt along with the terminal error output.
- **Verification**: The loop only terminates when a predefined "completion promise" (e.g., `<promise>COMPLETE</promise>`) is output by the model.

### 5. Installation and Setup Text
**Binary Installation command:**
`curl -fsSL https://claude.ai/install.sh | bash`

**Authentication**:
Run `claude` and complete the OAuth flow via the browser to link your **Anthropic Pro/Max** subscription or API key.

**Initialization**:
Run `/init` in a new case folder to let Claude analyze the evidence structure and create a case-specific memory file.