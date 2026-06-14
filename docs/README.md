# docs/ — canonical index

Read this first when navigating the documentation tree. The root README is the judge-facing landing page; this file is the maintainer/operator map.

## Start Here

| Need | Read |
|---|---|
| Install from a cold clone (canonical) | [`../INSTALL.md`](../INSTALL.md) — clone → install → verify → first run |
| Pick an environment + run modes | [`../QUICKSTART.md`](../QUICKSTART.md) — the one command is `scripts/verdict <evidence>` |
| Run it — every flag, run modes, output layout | [`using/running-verdict.md`](using/running-verdict.md) |
| Full MCP-server / tool / dependency / env inventory | [`reference/mcp-and-tools.md`](reference/mcp-and-tools.md), [`reference/dependencies.md`](reference/dependencies.md), [`reference/environment-variables.md`](reference/environment-variables.md) |
| Understand the architecture | [`architecture.md`](architecture.md) |
| Verify custody/manifest claims | [`cryptographic-attestation.md`](cryptographic-attestation.md) |
| Interpret verdicts safely | [`verdict-semantics.md`](verdict-semantics.md) |
| Review release evidence | [`release-evidence/README.md`](release-evidence/README.md) |
| Map local evidence to scoreable answer keys | [`evidence-answer-keys.md`](evidence-answer-keys.md) |
| Understand what is intentionally omitted | [`release-surface.md`](release-surface.md) |

Status legend:

| Badge | Meaning |
|---|---|
| **SHIPPED** | The work this doc describes is built and live in code. The doc is still useful as architectural reference; don't re-execute it as a TDD plan. |
| **ACTIVE** | Currently authoritative for ongoing work. Edit when the underlying surface changes. |
| **RESEARCH** | Background, exploration, or external reference. Not load-bearing for the submission. |
| **RETIRED** | Work shipped; doc is kept for git-log archaeology only. Each retired file carries a status banner naming where the live code lives. |
| **REQUIRED** | Devpost / SANS rules require this doc; ships with the submission. |

The authoritative *precedence* hierarchy (which spec overrides which) lives in `CLAUDE.md` "Document hierarchy" — this index just makes per-file purpose scannable.

---

## Repo-root docs

| File | Status | Purpose |
|---|---|---|
| `CLAUDE.md` | **ACTIVE** | Agent instructions, document hierarchy, non-negotiable invariants, spec/code divergences. Always loaded into Claude Code sessions. |
| `AGENTS.md` | **ACTIVE** | Codex-compatible adapter instructions that defer to `CLAUDE.md` and preserve the narrow MCP surface. |
| `README.md` | **ACTIVE** | Public-facing project landing page. |
| `INSTALL.md` | **ACTIVE** | Canonical install guide: clone → install → verify → first run, plus the container path. |
| `CONTRIBUTING.md` | **ACTIVE** | How to build, test (mirrors CI), and submit changes; the invariants and Conventional-Commit rules. |
| `QUICKSTART.md` | **ACTIVE** | Three-step quickstart for impatient users. |
| `CHANGELOG.md` | **ACTIVE** | Chronological project changelog. |

## `docs/` top level (analyst + judge facing)

| File | Status | Purpose |
|---|---|---|
| `architecture.md` | **REQUIRED** | Devpost Required Component #3. Trust-boundary diagram + runtime architecture. The single page judges reach first. |
| `accuracy-report.md` | **REQUIRED** | Devpost Required Component #9. Scoring method, benchmark status, and honest gaps. |
| `artifact-semantics.md` | **ACTIVE** | Analyst reference: what each artifact type (Prefetch, Amcache, ShimCache, MFT, EVTX, memory, YARA, etc.) proves and doesn't prove, plus the ≥2 artifact-class corroboration table. |
| `codex-compatibility.md` | **ACTIVE** | Operator guide for using Codex with the same two product MCP servers, without broad external MCP defaults. |
| `competitive-analysis.md` | **ACTIVE** | Public positioning against adjacent DFIR and agent tools. |
| `cryptographic-attestation.md` | **REQUIRED** | Three-link chain-of-custody story (rubric criterion #5). How `manifest_verify` produces FRE 902(14) self-authenticating evidence post-A5. |
| `DATASET.md` | **REQUIRED** | Devpost Required Component #5. Every fixture the agent was tested against, with SHA-256 + license + expected findings. |
| `evidence-answer-keys.md` | **ACTIVE** | Local `evidence/` drop-zone cases mapped to committed `goldens/` answer keys and score commands. |
| `extending-the-tool-surface.md` | **ACTIVE** | How to add typed tools without widening the product into arbitrary shell access. |
| `glossary.md` | **ACTIVE** | Plain-language definitions (Case/Observable/Finding/Verdict, the three Verdicts, ACH, audit chain) + a short FAQ. |
| `false-positives.md` | **ACTIVE** | Operator's guide. Three architectural FP layers + four operational habits + per-tool FP risk table. |
| `finding-to-action.md` | **ACTIVE** | Per-MITRE-technique IR playbook: from a SUSPICIOUS/CONFIRMED finding to analyst next steps (T1014, T1055, T1547, T1543, T1053, T1070, T1041/T1048). |
| `investigation-phases.md` | **ACTIVE** | Phase-by-phase walkthrough: case_open → Pool A/B → contradictions → verify → judge → correlate → finalize. What each phase produces in audit.jsonl and verdict.json. |
| `live-test-matrix.md` | **ACTIVE** | Evidence-type live-test expectations and current parser/runtime gaps. |
| `replay-determinism.md` | **ACTIVE** | Replay determinism notes for stable verifier behavior. |
| `release-surface.md` | **ACTIVE** | What ships in source, what archive exports intentionally omit, and why. |
| `troubleshooting.md` | **ACTIVE** | Failure modes and remediation commands for install/run/report issues. |
| `verdict-semantics.md` | **ACTIVE** | Analyst-facing meaning of `SUSPICIOUS` / `INDETERMINATE` / `NO_EVIL`; mirrors `compute_verdict` in `scripts/find_evil_auto.py`. |

### Current automation outputs

- `scripts/verdict <evidence>` is THE ONE COMMAND: preflight → investigate → open the live dashboard → signed verdict + report. Flags: `--sift` (run DFIR tools in the SANS SIFT VM), `--no-dashboard`, `--skip-build`, `--dry-run`, `--run-summary`. `find-evil-run` and `find-evil-live` are deprecated shims that forward to `verdict`; the headless automation engine is internal; `find-evil-sift` is the SIFT-VM helper.
- `scripts/verdict --run-summary <path>` writes a machine-readable run summary outside the normal case artifact set while delegating to the internal automation engine. It points to the local run directory and records artifact paths, report QA, release-gate/expert-signoff state, signer, readiness state, blockers, warnings, and final result/error.
- `scripts/readiness-gate.ps1` is the packet-producing readiness flow. Full mode writes `readiness-summary.json` and `readiness-packet.zip` under `tmp/readiness-gates/<run-id>/`, with packet/readiness-packet-manifest.json listing copied artifacts; fixed `-RunId` reruns refresh generated packet contents and may use a timestamped local-build child run; passing states mean ready for human expert review, not customer release.
- `scripts/readiness-gate.sh` is POSIX strict/check-only. It can print `SUBMISSION_READY` for its legacy checks, but it does not create the readiness packet ZIP.
- The dev "done" gate is a passing **live test**: run `scripts/verdict <evidence>` against real evidence and confirm a real verdict in `verdict.json` (each Finding citing a `tool_call_id`) plus `manifest_verify.json` `overall=true`. Per-evidence-type expectations and current gaps live in [`live-test-matrix.md`](live-test-matrix.md) and `CLAUDE.md` "Running A Case".
- Local smoke runners (`bash scripts/run-all-smokes.sh` for POSIX/Git Bash, `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-all-smokes.ps1` for native Windows) are a **CI predictor** — they mirror what L1 runs, not a live test. Do not copy old hard-coded smoke counts; the scripts print the current tally.
- Demo-video tooling is optional release support, not product runtime. `bash scripts/make-demo-video.sh` renders Remotion/edge-tts videos when the script package and source beats are present; reduced source checkouts may omit historical demo scripts and keep only generated release videos.

## `docs/reference/` (canonical inventories)

| File | Status | Purpose |
|---|---|---|
| `mcp-and-tools.md` | **ACTIVE** | Single source of truth for MCP servers (6 registered: 2 product + 4 non-product incl. `qmd` dev-memory) + the 43 product tools + the no-`execute_shell` invariant. Resolves the server "undercount." |
| `dependencies.md` | **ACTIVE** | Dependency + external-DFIR-tool + version matrix mirroring `scripts/doctor.sh`; licenses + expected-failure-when-missing. |
| `environment-variables.md` | **ACTIVE** | The ~35 `FIND_EVIL_*`/`FINDEVIL_*`/credential/SIFT/n8n env vars in one table. |

## `docs/using/` (operator how-to)

| File | Status | Purpose |
|---|---|---|
| `running-verdict.md` | **ACTIVE** | Canonical usage guide: `scripts/verdict` + every flag, the three run modes, dashboard, output layout under `tmp/auto-runs/<case-id>/`. |
| `fleet-analysis.md` | **ACTIVE** | The 3-stage fleet pipeline (`fleet_investigate` → `fleet_correlate` → `render_fleet_report`). |
| `evidence-intake.md` | **ACTIVE** | Evidence staging conventions + which evidence type triggers which PLAYBOOK path. |
| `reports.md` | **ACTIVE** | `render_report.py`: REPORT.html/PDF, re-rendering after expert edits, customization. |

## `docs/analyst/` (interpretation)

| File | Status | Purpose |
|---|---|---|
| `verdict-interpretation.md` | **ACTIVE** | Hub for "I have a Verdict/Finding — now what?" Ties together verdict semantics + false-positives + finding-to-action (originals stay authoritative). |
| `tool-playbooks.md` | **ACTIVE** | Per-tool operator guidance (zeek/sysmon/registry/vel_collect/yara) + a per-tool expected-failure / troubleshooting table. |

## `agent-config/` (runtime DFIR agent identity)

These are read by the agent at investigation start (per `CLAUDE.md` "Investigation Read Order").

| File | Status | Purpose |
|---|---|---|
| `agent-config/SOUL.md` | **ACTIVE** | Mission + epistemic hierarchy (CONFIRMED > INFERRED > HYPOTHESIS) + FRE 902(14) stance + cross-artifact rule + no-attribution rule. |
| `agent-config/AGENTS.md` | **ACTIVE** | Supervisor / Pool A / Pool B / judge / verifier / correlator role descriptions. |
| `agent-config/PLAYBOOK.md` | **ACTIVE** | Tool sequences per evidence type (`.e01`, `.mem`, `.evtx`, Velociraptor `.zip`, mixed dirs). |
| `agent-config/TOOLS.md` | **ACTIVE** | Typed tool surface — 31 Rust + 12 Python MCP tools. |
| `agent-config/MEMORY.md` | **ACTIVE** | Tier-1 DFIR caveats (Amcache LastModified ≠ execution, ShimCache order changed at Win8.1, Logon Type 3 vs 10, etc.). |
| `agent-config/HEARTBEAT.md` | **ACTIVE** | Per-iteration self-check loop. |
| `agent-config/JUDGING.md` | **ACTIVE** | Pre-submission self-assessment rubric (6 quality criteria) that `scripts/self-score.py` grades a completed case against. Not part of the investigation pipeline. |

## Historical specs

The large historical `docs/specs/` set is intentionally omitted from reduced source exports. Current architecture and trust boundaries live in [`architecture.md`](architecture.md), [`cryptographic-attestation.md`](cryptographic-attestation.md), and `CLAUDE.md`; omission policy lives in [`release-surface.md`](release-surface.md).

## `docs/plans/` (current retained plans)

| File | Status | Where it lives now |
|---|---|---|
| `parser-coverage-execution.md` | **ACTIVE** | Parser coverage and execution-claim corroboration work. |

## `docs/runbooks/` (operational procedures)

| File | Status | Purpose |
|---|---|---|
| `ci-smoke-checklist.md` | **ACTIVE** | End-to-end pipeline verification before submission. |
| `dockerfile-a2-decision.md` | **RESEARCH** (decision archive) | Cut the in-container `find-evil` wrapper + `.deb` packaging (PR #4, 2026-04-27, "Option B"). Body retained as decision record. |
| `github-remote-bootstrap.md` | **HISTORICAL / ACTIVE RELEASE-REMOTE REFERENCE** | Historical bootstrap plus current `release` remote checks for `TimothyVang/verdict-dfir`; `v-submit` is already published. |
| `local-smoke-gate.md` | **ACTIVE** | Prerequisites, per-smoke coverage map, and common failure → fix pairs for `bash scripts/run-all-smokes.sh`. |
| `n8n-automation-integration.md` | **ACTIVE** | Optional: wire n8n as an operator-local harness *around* the product — repeatable runs + post-verdict finding-to-action (via `n8n-mcp`, user-scope). Not bundled, not the orchestrator, not in the audit chain. |
| `readiness-packet-windows.md` | **ACTIVE** | Three invocation modes for `scripts/readiness-gate.ps1`, readiness-state meanings, and `READINESS_BLOCKED` unblocking guide. |

## Adversarial Validation

| File | Status | Purpose |
|---|---|---|
| `red-team-challenge.md` | **ACTIVE** | "Break VERDICT" challenge matrix for unsupported artifacts, benign-admin false positives, single-source execution traps, DKOM-vs-smear, exfil-without-network, and parser failures. |

## `docs/release-evidence/`

| File | Status | Purpose |
|---|---|---|
| `README.md` | **ACTIVE** | Explains why release evidence summaries are committed and what they are not. |
| `l3-local-sift.json` | **ACTIVE** | Validated local VMware/SIFT L3 fallback evidence for the `v-submit` release path. |

## Omitted historical surfaces

`docs/templates/`, `docs/legacy/`, `docs/specs/`, `docs/sample-run/`, and `docs/reports/` are historical or generated release surfaces and may be absent from this reduced checkout. See [`release-surface.md`](release-surface.md) for the source/export boundary.

## What this index does NOT cover

- Source code (`services/`, `apps/`, `scripts/`) — see the repository layout in `CLAUDE.md` plus per-service `README.md` files.
- External clones and local operator memory (`obsidian-mind/`, `n8n-references/`) are gitignored, optional, never evidence, and never audit-chain inputs.
