# Submission Notes — Find Evil!

> **For the SANS Find Evil! 2026 judge.** Second thing to read after [`README.md`](README.md). This file is a navigation aid into the rest of the repo — claims live in the source files cited; this file does not duplicate them.

| Field | Value |
|---|---|
| Project | Find Evil! — Cryptographically-Verifiable DFIR Agent |
| Repo | https://github.com/TimothyVang/sans-hackathon |
| Devpost URL | *(populated at `v-submit` tag time by `scripts/package-devpost.sh`; see the Devpost project page)* |
| License | Apache-2.0 ([LICENSE](LICENSE)) |
| SANS deadline | 2026-06-15 22:45 CDT |

**Elevator pitch.** A Claude Code agent that investigates Windows host evidence — memory images, EVTX logs, disk images — and produces a signed verdict (`SUSPICIOUS` / `INDETERMINATE` / `NO_EVIL`) with a cryptographic chain of custody any third party can verify offline. Two adversarial agent pools (Pool A persistence-biased, Pool B exfil-biased) investigate the same evidence in parallel; the contradiction surface is itself a first-class output. The agent self-scores against the SANS rubric and writes the score into the audit chain *before* signing — judges can grep it. Full pitch: [`README.md`](README.md) "What it is."

---

## Read order — judge's first 30 minutes

| Order | File | Time | Why |
|---|---|---|---|
| 1 | [`README.md`](README.md) | ~3 min | Project framing, four distinctive claims, repo layout |
| 2 | [`agent-config/JUDGING.md`](agent-config/JUDGING.md) | ~3 min | The SANS 6-criterion rubric verbatim + the agent's own self-score checklist (the agent is graded against this and `grep`-able from the audit chain) |
| 3 | [`docs/demo-script-a2.md`](docs/demo-script-a2.md) | ~5 min | The 5-minute Devpost video walkthrough, beat-by-beat with rubric mapping |
| 4 | [`docs/cryptographic-attestation.md`](docs/cryptographic-attestation.md) | ~5 min | The three-link chain, FRE 902(14) prong-by-prong analysis (with the honest A5 trade-off on prong b), third-party offline-verification recipe (rubric criterion 5) |
| 5 | [`docs/false-positives.md`](docs/false-positives.md) | ~3 min | Three architectural FP layers + four operational habits (rubric criterion 2) |
| 6 | [`CLAUDE.md`](CLAUDE.md) §"Project state" + §"Document hierarchy" + §"Spec/code divergences" | ~5 min | Current shipped state, document precedence, documented divergences (all downstream-clean — `python scripts/divergence-smoke.py` confirms) |

For the full doc map (every file with status badge + one-line purpose): [`docs/README.md`](docs/README.md).

---

## Quick verification recipe (no SIFT VM needed, ~5 min)

These commands confirm the smokes are green and both MCP servers dispatch correctly. Run from a clean clone:

```bash
git clone https://github.com/TimothyVang/sans-hackathon.git find-evil
cd find-evil

# 1. Full local smoke loop — Rust + Python + lint + audit + dispatch.
#    Mirrors what L1 GHA enforces. Should print "OK - 14 passed".
bash scripts/run-all-smokes.sh

# 2. Dashboard's Vitest suite (8 tests across audit-tail + path allow-list).
pnpm install --frozen-lockfile
pnpm --filter @findevil/web test

# 3. Rust workspace test suite, locked.
cargo test --workspace --locked
```

If you have an `.e01` / memory image + a configured SIFT VM, add a fourth step:

```bash
# 4. End-to-end Tesla mode. Produces case dir + signed manifest + REPORT.pdf
#    in tmp/auto-runs/auto-<uuid>/.
bash scripts/find-evil-auto <evidence-path> --unattended
```

SIFT VM setup: [`QUICKSTART.md`](QUICKSTART.md) Path A + [`scripts/sift-vm-bootstrap.sh`](scripts/sift-vm-bootstrap.sh).

---

## What ships vs what's deferred

### Ships in this submission

| Capability | Where it lives |
|---|---|
| 23 typed MCP tools — 12 Rust DFIR + 11 Python crypto/ACH/memory/ACP | [`services/mcp/`](services/mcp/) + [`services/agent_mcp/`](services/agent_mcp/) — table in [`CLAUDE.md`](CLAUDE.md) §"Agent investigation prompt" |
| 7 agent-config role/identity prompts | [`agent-config/`](agent-config/) (SOUL, AGENTS, PLAYBOOK, TOOLS, MEMORY, HEARTBEAT, JUDGING) |
| Three-link cryptographic chain-of-custody (audit hash chain → rs_merkle → sigstore/Rekor) | [`docs/cryptographic-attestation.md`](docs/cryptographic-attestation.md) |
| Tesla-mode single-command orchestrator | [`scripts/find-evil-auto`](scripts/find-evil-auto) |
| 22-host fleet pipeline (investigate → correlate → render) | `scripts/fleet_*.py` (showcase: [`docs/reports/2026-04-26-srl2018-dc-investigation.md`](docs/reports/2026-04-26-srl2018-dc-investigation.md)) |
| SSE audit-log tail + dashboard scaffold + `/debug` live event viewer | [`apps/web/`](apps/web/) — Next.js 15 + Tailwind v4, handler at `app/api/audit/route.ts` |
| `kind=judge_selfscore` records in the audit chain BEFORE manifest finalize | [`agent-config/JUDGING.md`](agent-config/JUDGING.md) §"End-of-investigation self-check" |

### Deferred / out of scope (intentional)

| Item | Why |
|---|---|
| Phase 5/6 pixel-art sprites + AuditBeadString chrome | Gated on a Claude Design prototyping pass. Brief: [`docs/design-briefs/phase-5-6-sprite-design-brief.md`](docs/design-briefs/phase-5-6-sprite-design-brief.md). |
| `apps/mcp-widgets/` (M3 Anthropic MCP App widgets) | Deferred per A2 §2.1; A3 promotes only `apps/web/` back onto the critical path |
| Pre-A2 in-container `find-evil` CLI + `.deb` package | Cut by PR #4 (2026-04-27); see [`docs/runbooks/dockerfile-a2-decision.md`](docs/runbooks/dockerfile-a2-decision.md) |
| Networked IBM-ACP HTTP transport | A3 records ACP handoffs to `audit.jsonl` only; HTTP transport is out of scope |
| Hermes runtime sidecar | Deferred per A2; A3 ports the FTS5 cross-case-memory pattern into `services/agent_mcp/` directly |
| Bitcoin / OpenTimestamps anchor on the crypto chain | Removed under Amendment A5 — judges scoring offline can't exercise the network call or wait for Bitcoin attestation maturation. Trade-off documented in [`docs/cryptographic-attestation.md`](docs/cryptographic-attestation.md). |

---

## Where the load-bearing claims live (deep-link map)

These are the canonical sources for the claims in [`README.md`](README.md). Each is a one-stop link — no need to scan multiple files for the same claim.

| Claim | Canonical doc |
|---|---|
| **Cryptographic chain of custody** (rubric #5) | [`docs/cryptographic-attestation.md`](docs/cryptographic-attestation.md) — the three-link chain, FRE 902(14) prong-by-prong, offline-verification recipe |
| **Adversarial agents (ACH dual-pool)** (rubric #1, #2) | [`agent-config/AGENTS.md`](agent-config/AGENTS.md) §"Why this structure (Heuer's ACH applied as agent topology)" |
| **Typed MCP tool surface** (rubric #4) | [`agent-config/TOOLS.md`](agent-config/TOOLS.md) — every tool with input/output schema + when to call |
| **Judge self-score in the audit chain** (tiebreaker for rubric #1, #5) | [`agent-config/JUDGING.md`](agent-config/JUDGING.md) §"End-of-investigation self-check" |
| **Documented spec/code divergences** | [`CLAUDE.md`](CLAUDE.md) §"Spec/code divergences (code wins)" — confirm clean: `python scripts/divergence-smoke.py` |

---

## Anticipated judge questions

**"Why no real-world end-to-end run in the demo video?"**
The demo video shows a Tesla-mode investigation against a real memory image (Beat 3 of [`docs/demo-script-a2.md`](docs/demo-script-a2.md)) and a 22-host fleet rollup against the SANS HACKATHON-2026 SRL-2018 dataset (Beat 6). Full report: [`docs/reports/2026-04-26-srl2018-dc-investigation.md`](docs/reports/2026-04-26-srl2018-dc-investigation.md) (PDF: 1.3 MB; fleet rollup at §9.1). Fleet artifacts: `tmp/fleet-runs/fleet-20260426T055440Z/`.

**"Why doesn't the dashboard have real sprites?"**
Component contracts and state derivation are scaffolded in [`apps/web/components/sprites/`](apps/web/components/sprites/); the pixel-art visuals are gated on the Claude Design pass per [Amendment A3](docs/specs/2026-04-26-amendment-a3-agent-army-and-dashboard.md) Phase 5/6. The audit-bead string and hash-chain badge already update live from the SSE stream.

**"What happens if I install on Windows?"**
Windows-friendly throughout. Smoke runner gates ANSI colors on `[ -t 1 ]` so Windows `cmd` without VT escapes stays plain ASCII. The `find-evil` family of launchers is bash, runs cleanly under Git Bash / WSL. The Tesla-mode orchestrator SSHes into a SIFT VM regardless of host OS, so the host platform does not need DFIR tools installed. Hypervisor: VMware Workstation only today (`scripts/find-evil-sift` lines 10–12).

**"Where's the LangGraph supervisor / FastAPI service / in-container CLI?"**
Dropped per [Amendment A2](docs/specs/2026-04-25-amendment-a2-claude-code-primary-interface.md) §2.1. Claude Code IS the orchestrator; the streaming UX is Claude Code's terminal; the entry point is `scripts/find-evil` (or `claude` directly). Re-introduction guarded by the L0 `amendment-a2-guard` GHA job.

**"Why no Bitcoin anchor on the crypto chain?"**
Removed under Amendment A5 (2026-04-30). The pre-A5 design tail-anchored to Bitcoin via OpenTimestamps; that tier required network reach to a calendar server plus a multi-hour wait for Bitcoin attestation maturation, neither of which a judge scoring offline can exercise. The orchestrator never called `ots_stamp` in the first place — it was listed as "(Optional) Step 10" in `find_evil_auto.py`'s docstring with no code path invoking it. FRE 902(14) prong (b) is now satisfied by Sigstore's Rekor transparency log instead. Trade-off: [`docs/cryptographic-attestation.md`](docs/cryptographic-attestation.md) §"What FRE 902(14) requires."

**"`Cargo.lock` is committed — is that a mistake?"**
No — `findevil-mcp` ships as a binary (not a library), so the lockfile is committed deliberately. [`.gitignore`](.gitignore) carries an explicit comment to that effect; documented in [`CLAUDE.md`](CLAUDE.md) §"Spec/code divergences."

---

## Contact

| Channel | Where |
|---|---|
| Maintainer | TimothyVang on GitHub |
| Issues | https://github.com/TimothyVang/sans-hackathon/issues |
| Pull requests | https://github.com/TimothyVang/sans-hackathon/pulls |

For Claude-Code-driven investigation questions, the `agent-config/` prompts are self-contained — opening `claude` from the repo root auto-loads them via [`.mcp.json`](.mcp.json) and the agent-investigation prompt at the top of [`CLAUDE.md`](CLAUDE.md).
