# Find Evil!

**SANS Find Evil! 2026 hackathon submission** — a cryptographically-verifiable DFIR agent that investigates Windows host evidence end-to-end and produces a sigstore-signed, Rekor-logged audit chain on every finding (verifiable offline).

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![Status: pre-submission](https://img.shields.io/badge/status-pre--submission-orange.svg)
![Rust 1.88](https://img.shields.io/badge/rust-1.88-orange.svg)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)

> **Deadline:** 2026-06-15 22:45 CDT · **Reference bar:** [AppliedIR / Valhuntir](https://github.com/AppliedIR/Valhuntir) (Rob Lee, MIT)

## What it is

A DFIR agent built on the SANS SIFT Workstation that takes a memory image, EVTX log, or disk image and produces a signed verdict — `SUSPICIOUS`, `INDETERMINATE`, or `NO_EVIL` — with the full reasoning trace cryptographically attested to.

```
$ bash scripts/find-evil-auto /mnt/hgfs/evidence/extracted/<host>/<host>-memory.img --unattended
=== case_open ===
  case_id    = <uuid4>
  image_hash = <sha256-of-evidence>
=== memory image investigation ===
  vol_pslist:  N1 processes          <- active-list walk
  vol_psscan:  N2 processes          <- EPROCESS pool signature scan
  -> if N1 << N2: DKOM/T1014 (Rootkit) signal -- the 22-host SRL-2018
                  fleet showed this on 11 hosts (docs/reports/...).
=== reasoning phase ===
  contradictions: K     judge merged: F findings    correlator: F' kept
=== judge self-score ===
  6 audit records, kind=judge_selfscore, written BEFORE manifest_finalize
  so the score is part of the cryptographic attestation.
=== manifest finalize ===
  merkle_root_hex  = <hex digest>
  verdict          = SUSPICIOUS | INDETERMINATE | NO_EVIL
                     (per docs/verdict-semantics.md compute_verdict policy)
```

(Stylized. Real artifacts from a 22-host fleet investigation live at
`docs/reports/2026-04-26-srl2018-dc-investigation.md` + the embedded
`figures-2026-04-26/` set + `tmp/fleet-runs/fleet-20260426T055440Z/`.)

The chain of custody: `dc3dd` → `sha256sum` (analyst receipt) → `case_open` SHA-256 (Rust `sha2`, in-process) → audit-log `prev_hash` chain → `rs_merkle` Merkle leaf → sigstore signature (Rekor transparency-log inclusion proof). Any third party verifies the run offline via the `manifest_verify` MCP tool. (Pre-A5 the chain also tail-anchored to Bitcoin via OpenTimestamps; that tier was removed — see `docs/cryptographic-attestation.md` for the trade-off.)

## What's distinctive

1. **Cryptographic chain-of-custody at every link.** Hash-chained audit log + rs_merkle root + sigstore signature (Rekor inclusion proof). Supports a FRE 902(14) self-authenticating-evidence claim — a court-of-law bar, not just a CI green check.

2. **ACH dual-pool architecture.** Two agent pools investigate the same evidence in parallel with opposing priors (persistence vs exfil). Contradictions surface BEFORE the judge merges, in the audit chain. Heuer's intelligence-analysis framework applied as live agent topology — not a rebrand of consensus-seeking.

3. **12 typed Rust MCP tools, no `execute_shell` anywhere.** EVTX parsed in-process (omerbenamram/evtx crate, ~1600× faster than python-evtx); Hayabusa / Chainsaw / Volatility3 / Velociraptor invoked through subprocess boundaries only — keeps AGPL/GPL out of the Apache-2.0 submission tree. The deliberately redundant `vol_pslist` + `vol_psscan` pair catches DKOM rootkits the active-list walker would miss alone.

4. **Judge self-score before manifest finalize.** Per [`agent-config/JUDGING.md`](agent-config/JUDGING.md), the agent self-scores against the SANS 6-criterion rubric and writes the score into the audit chain *before* signing. Judges can `grep '"kind":"judge_selfscore"' audit.jsonl` and see the agent's own assessment cryptographically locked.

5. **Real evidence, not fixtures.** The included [`docs/reports/2026-04-26-srl2018-dc-investigation.md`](docs/reports/2026-04-26-srl2018-dc-investigation.md) (PDF: 1.3 MB) walks through an end-to-end investigation of the SANS HACKATHON-2026 *SRL-2018 Compromised Enterprise Network* dataset. The follow-on 22-host fleet investigation surfaced 11 hosts with T1014 (DKOM) findings, 9 with T1055 (Process Injection), and the textbook automated-recon-sweep signature: 6 hosts ran `Autorunsc.exe` at the exact same second.

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

For headless single-shot runs:

```bash
bash scripts/find-evil-auto /mnt/hgfs/evidence/extracted/<host>/<host>-memory.img --unattended
```

For multi-host fleet investigations:

```bash
python scripts/fleet_investigate.py            # walks the evidence tree
python scripts/fleet_correlate.py              # cross-host pattern detection
python scripts/render_fleet_report.py          # produces FLEET_REPORT.pdf
```

See [QUICKSTART.md](QUICKSTART.md) for the full per-mode walkthrough and [docs/architecture.md](docs/architecture.md) for the trust-boundary diagrams.

## Repository layout

```
.
├── agent-config/             — runtime DFIR agent identity
│                               (SOUL/AGENTS/PLAYBOOK/TOOLS/MEMORY/HEARTBEAT/JUDGING)
├── services/mcp/             — Rust MCP server (12 typed DFIR tools)
├── services/agent_mcp/       — Python MCP server (11 crypto/ACH/memory/ACP tools)
├── services/agent/           — findevil_agent package (M2 crypto + M4 ACH primitives)
├── services/swarm/           — overnight build swarm (Option B per Amendment A1)
├── scripts/
│   ├── find-evil             — local-mode launcher
│   ├── find-evil-sift        — SIFT-VM SSH-bridge launcher
│   ├── find-evil-auto        — headless / Tesla-mode orchestrator
│   ├── fleet_investigate.py  — walk evidence tree → per-host investigations
│   ├── fleet_correlate.py    — cross-host pattern detection
│   ├── render_fleet_report.py — fleet-level PDF report (figures + selfscore aggregate)
│   ├── render_report.py      — per-case PDF report (with selfscore table)
│   ├── rust-mcp-smoke.py     — end-to-end Rust MCP tool surface check
│   └── agent-mcp-smoke.py    — end-to-end Python MCP surface check (synthetic + real-evidence)
├── packer/                   — L3 sandbox: warm-qcow2 build from sift-2026.03.24.ova
├── docker/                   — L1/L2 sandbox: docker compose specs + Dockerfiles
├── docs/
│   ├── architecture.md       — five trust boundaries + Mermaid diagrams
│   ├── cryptographic-attestation.md — the three-link chain (audit → Merkle → sigstore → FRE 902(14))
│   ├── verdict-semantics.md  — what SUSPICIOUS / INDETERMINATE / NO_EVIL mean + triage flow
│   ├── false-positives.md    — three architectural FP layers + four operational habits
│   ├── demo-script-a2.md     — 5-minute Devpost video script (per-beat narration)
│   ├── reports/              — analyst-facing investigation reports (real evidence)
│   └── superpowers/          — specs (5) + plans (4) for the 4 subsystems
└── .mcp.json                 — Claude Code auto-spawn registry for both MCP servers
```

## License & attribution

Apache-2.0. See [LICENSE](LICENSE).

The vendored reference clones in `openclaw/`, `hermes-agent/`, `Linear-Coding-Agent-Harness/`, and `.playwright-mcp/` are research-only and gitignored — they do not ship in the submission.

## Status

This is a hackathon submission, not a maintained product. The code, test suite, agent-config, and demo script are stable; the build swarm and Devpost video are pre-submission work-in-progress. The cryptographic chain-of-custody and the typed MCP tool surface are the load-bearing claims — both are exercised end-to-end on every CI run.

> **For Claude Code agents:** read [CLAUDE.md](CLAUDE.md) first. It encodes the document hierarchy, the non-negotiable invariants, the Karpathy 4 principles, and the spec/code divergence list.
