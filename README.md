# Find Evil!

**SANS Find Evil! 2026 hackathon submission.**

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![Status: pre-submission](https://img.shields.io/badge/status-pre--submission-orange.svg)
![Rust 1.88](https://img.shields.io/badge/rust-1.88-orange.svg)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)

> **Deadline:** 2026-06-15 22:45 CDT · **Reference bar:** [AppliedIR / Valhuntir](https://github.com/AppliedIR/Valhuntir) (Rob Lee, MIT)

---

## What it is

**Find Evil!** is a Claude Code agent that investigates Windows host evidence — memory images, EVTX logs, disk images — and produces a signed verdict (`SUSPICIOUS` / `INDETERMINATE` / `NO_EVIL`) with a cryptographic chain of custody any third party can verify offline.

Four claims, all exercised on every CI run:

1. **A typed MCP tool surface, no `execute_shell`.** 23 narrow Pydantic-validated tools — 12 Rust DFIR (`case_open`, `evtx_query`, `vol_pslist`/`vol_psscan`, `vol_malfind`, `mft_timeline`, `hayabusa_scan`, `yara_scan`, `usnjrnl_query`, `registry_query`, `prefetch_parse`, `vel_collect`) plus 11 Python crypto/ACH/memory/handoff. EVTX parsed in-process via the omerbenamram/evtx Rust crate; AGPL/GPL tools (Hayabusa, Volatility3, Velociraptor) invoked as subprocesses only — Apache-2.0 submission tree stays clean.

2. **Cryptographic chain of custody with FRE 902(14) framing.** Three composed primitives: hash-chained audit JSONL (`prev_hash` per record) → `rs_merkle` Merkle root over canonical-JSON tool outputs → sigstore signature with Rekor transparency-log inclusion proof. Verifiable offline by `manifest_verify` — no network, no third-party servers. (Pre-A5 the chain tail-anchored to Bitcoin via OpenTimestamps; removed because judges scoring offline can't exercise the network call or wait for Bitcoin attestation maturation. Trade-off documented in [`docs/cryptographic-attestation.md`](docs/cryptographic-attestation.md).)

3. **Analysis of Competing Hypotheses as agent topology.** Two pools investigate the same evidence with opposing priors (persistence-biased vs. exfil-biased). Disagreements emit as `kind=contradiction` audit records *before* the judge merges — surfaced as first-class output, not hidden in consensus. Heuer's 1970s intelligence-analysis framework applied as live agent architecture, not a rebrand of single-agent voting.

4. **Self-score inside the cryptographic attestation.** The agent emits 6 `kind=judge_selfscore` audit records (one per SANS rubric criterion) *before* `manifest_finalize`. Because they land before the Merkle tree closes, the agent's own self-assessment is part of the signed manifest — `grep '"kind":"judge_selfscore"' audit.jsonl` and you have the agent's own score against the same rubric you're using.

**The showcase:** [`docs/reports/2026-04-26-srl2018-dc-investigation.md`](docs/reports/2026-04-26-srl2018-dc-investigation.md) (PDF: 1.3 MB) — a real end-to-end investigation of the SANS HACKATHON-2026 *SRL-2018 Compromised Enterprise Network* dataset. Single-host walkthrough plus a 22-host fleet rollup at §9.1: 11 hosts with T1014 (DKOM), 9 with T1055 (Process Injection), and the textbook automated-recon-sweep signature — 6 hosts ran `Autorunsc.exe` at the exact same second.

---

## Try it

Three steps, no other config.

```bash
git clone https://github.com/<your-org>/find-evil.git
cd find-evil

# Pre-flight + Rust+Python build (detects the three Claude credential modes
# from CLAUDE.md "Credential modes (Amendment A1)" — pick whichever you have).
bash scripts/install.sh

# Open Claude Code in the repo. .mcp.json auto-spawns both MCP servers
# (Rust + Python) on session start.
claude
# (or, equivalently, bash scripts/find-evil — same thing with a friendlier
# error message if claude isn't on PATH.)

# Then prompt the agent: "investigate <case path>"
```

Headless single-shot:

```bash
bash scripts/find-evil-auto /mnt/hgfs/evidence/extracted/<host>/<host>-memory.img --unattended
```

Per-mode walkthrough + SIFT-VM setup recipe lives in [QUICKSTART.md](QUICKSTART.md). Trust-boundary diagrams in [docs/architecture.md](docs/architecture.md). For judges: [SUBMISSION_NOTES.md](SUBMISSION_NOTES.md).

---

## Repository layout

```
.
├── agent-config/             — runtime DFIR agent identity (SOUL/AGENTS/PLAYBOOK/
│                               TOOLS/MEMORY/HEARTBEAT/JUDGING)
├── services/mcp/             — Rust MCP server (12 typed DFIR tools)
├── services/agent_mcp/       — Python MCP server (11 crypto/ACH/memory/ACP tools)
├── services/agent/           — findevil_agent package (M2 crypto + M4 ACH primitives)
├── services/swarm/           — overnight build swarm (Option B per Amendment A1)
├── scripts/                  — find-evil / find-evil-sift / find-evil-auto launchers,
│                               fleet pipeline (fleet_*.py + render_fleet_report.py),
│                               smoke harnesses (rust-mcp-smoke + agent-mcp-smoke +
│                               run-all-smokes), report renderer
├── packer/                   — L3 sandbox: warm-qcow2 build from sift-2026.03.24.ova
├── docker/                   — L1/L2 sandbox: docker compose specs + Dockerfiles
├── docs/
│   ├── README.md             — canonical doc INDEX (read first)
│   ├── architecture.md       — five trust boundaries + Mermaid diagrams
│   ├── cryptographic-attestation.md  — three-link chain + FRE 902(14)
│   ├── verdict-semantics.md  — what SUSPICIOUS / INDETERMINATE / NO_EVIL mean
│   ├── false-positives.md    — three architectural FP layers + four habits
│   ├── demo-script-a2.md     — 5-minute Devpost video script
│   ├── reports/              — analyst-facing investigation reports (real evidence)
│   ├── specs/                — 9 architecture specs (master + 4 amendments + 4 subsystems)
│   └── plans/                — 5 retired TDD plans (kept for git-log archaeology)
└── .mcp.json                 — Claude Code auto-spawn registry for both MCP servers
```

---

## License & attribution

Apache-2.0. See [LICENSE](LICENSE).

The vendored reference clones in `openclaw/`, `hermes-agent/`, `Linear-Coding-Agent-Harness/`, and `.playwright-mcp/` are research-only and gitignored — they do not ship in the submission.

---

## Status

This is a hackathon submission, not a maintained product. The code, test suite, agent-config, and demo script are stable; the build swarm and Devpost video are pre-submission work-in-progress. The cryptographic chain-of-custody and the typed MCP tool surface are the load-bearing claims — both are exercised end-to-end on every CI run.

> **For Claude Code agents:** read [CLAUDE.md](CLAUDE.md) first. It encodes the document hierarchy, the non-negotiable invariants, the Karpathy 4 principles, and the spec/code divergence list.
