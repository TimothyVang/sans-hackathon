# Find Evil! — Quickstart

Three things to get you investigating evidence with the agent.

---

## 1. Pick your environment (one-time, ~15 min)

Two paths. Pick whichever matches your situation.

### Path A — SIFT VM (recommended; matches the SANS judging environment)

```bash
# From the repo root, on Windows with VMware Workstation installed
# and the OVA at sift-2026.03.24.ova in the repo root:
bash scripts/sift-vm-bootstrap.sh
```

This converts the OVA, boots the VM headless, installs Rust + DFIR tools inside, sets up the SSH transport, and rewrites `.mcp.json.sift` to point at the running VM. Runs ~15 min on first invocation; subsequent runs detect existing state and skip.

### Path B — Local Windows host (faster iteration)

```bash
# Install the four DFIR-tool binaries on Windows (one-time):
winget install Volatility3 || pip install volatility3
winget install Hayabusa  # or download from github.com/Yamato-Security/hayabusa/releases
winget install Velociraptor  # or github.com/Velocidex/velociraptor/releases
# YARA-X is already in our crate; no separate install needed.

# That's it — `.mcp.json` points at local subprocesses by default.
```

---

## 2. Choose: interactive (Claude Code) or fully-automated (Tesla mode)

### Option 2A — Interactive Claude Code session (best for exploration)

```bash
# Local mode:
scripts/find-evil
# or:
claude

# SIFT-VM mode:
bash scripts/find-evil-sift
```

`.mcp.json` (or `.mcp.json.sift`, swapped automatically) tells Claude Code to spawn both MCP servers — `findevil-mcp` (Rust, 12 typed DFIR tools) and `findevil-agent-mcp` (Python, 10 typed crypto/ACH tools). The agent now has its tool surface.

In the session, prompt:

> investigate `<path-to-evidence>`

The agent reads `agent-config/SOUL.md` → `AGENTS.md` → `PLAYBOOK.md` → `TOOLS.md` → `MEMORY.md` → `HEARTBEAT.md` at session start, then drives the playbook tool sequence for that evidence type.

### Option 2B — `find-evil-auto` (Tesla mode, single command, no human input)

```bash
bash scripts/find-evil-auto <evidence-path-inside-VM> [--unattended] [--no-report]
```

Examples:

```bash
# Memory image:
bash scripts/find-evil-auto /mnt/hgfs/evidence/extracted/base-dc/base-dc-memory.img --unattended

# Single EVTX:
bash scripts/find-evil-auto /home/sansforensics/find-evil/fixtures/single-evtx/Security.evtx --unattended

# Disk image (case_open + chain-of-custody only; deeper analysis requires interactive mode):
bash scripts/find-evil-auto /mnt/hgfs/evidence/disk-images/base-dc-cdrive.E01 --unattended
```

What it does in one command (no interactive prompts):

1. Detects evidence type from the file extension
2. Opens both MCP servers inside the SIFT VM via SSH stdio
3. case_open → tool sequence per type → audit chain → judge → correlator → manifest_finalize
4. Synthesizes Pool A (persistence-biased) and Pool B (exfil-biased) findings deterministically from tool outputs
5. Writes `verdict.json` with the verdict (`SUSPICIOUS` / `NO_EVIL` / `INDETERMINATE` — see [`docs/verdict-semantics.md`](docs/verdict-semantics.md) for the analyst triage flow)
6. Generates a fully-templated PDF investigation report (figures + findings + chain-of-custody attestation; see [`docs/cryptographic-attestation.md`](docs/cryptographic-attestation.md) for offline-verification recipe)

Output (on host, host-local):
```
tmp/auto-runs/auto-<uuid>/
├── audit.jsonl
├── run.manifest.json
├── verdict.json
├── REPORT.md
├── REPORT.html
├── REPORT.pdf
└── figures/
    ├── chain_of_custody.png
    ├── findings_table.png
    └── psscan_timeline.png  (memory images only)
```

Output (inside VM, agent's case dir):
```
/home/sansforensics/find-evil/tmp/auto-<uuid>/
├── audit.jsonl
├── run.manifest.json
└── verdict.json
```

Run it with `--no-report` if you just want the verdict + manifest and skip PDF rendering (saves ~5 seconds).

### Option 2C — Fleet investigation (entire host inventory)

When the case is "we have N memory images, find all the evil," the
fleet pipeline is the operator path. Three scripts compose:

```bash
# 1. Walk every .img under /mnt/hgfs/evidence/extracted/<host>/ and
#    invoke find-evil-auto per host. Sequential by default to avoid
#    VM RAM contention; vol3 keeps a symbol cache so per-image
#    overhead drops after the first run.
python scripts/fleet_investigate.py [--limit N] [--skip BASENAMES]

# 2. Cross-host pattern detection: process names appearing on ≥2
#    hosts, 60-second-window temporal clusters across hosts, MITRE
#    technique density, Merkle-root uniqueness check.
python scripts/fleet_correlate.py [tmp/fleet-runs/<fleet-id>]

# 3. Render the fleet report — 4 matplotlib figures
#    (verdict_distribution, mitre_density, cross_host_processes,
#    temporal_clusters) + Markdown + HTML + PDF, same pandoc +
#    Chrome-headless chain as the per-host reports.
python scripts/render_fleet_report.py [tmp/fleet-runs/<fleet-id>]
```

Output:
```
tmp/fleet-runs/fleet-<timestamp>/
├── fleet.json                 — per-host verdict summary
├── fleet-summary.md           — terse per-host rollup
├── fleet_correlation.json     — cross-host findings (machine-readable)
├── fleet_correlation.md       — cross-host findings (analyst summary)
├── FLEET_REPORT.md/html/pdf   — final analyst-facing report
└── figures/
    ├── verdict_distribution.png
    ├── mitre_density.png
    ├── cross_host_processes.png
    └── temporal_clusters.png
```

The headline visual is `temporal_clusters.png` — each row is a
cluster of process creations across ≥2 hosts within 60 seconds,
color-coded by host. The fingerprint of automated lateral-movement
tradecraft (PsExec waves, WMI execution chains, scheduled-task
pivots) reads off this chart immediately.

Cross-host process correlations filter known-benign enterprise
binaries (McAfee/Trellix endpoint stack, VMware Tools, Windows
infrastructure, Microsoft Defender) via `COMMON_WIN_PROCS` in
`scripts/fleet_correlate.py` — see `docs/false-positives.md`
"Fleet cross-host correlation" for what is and isn't filtered and
why. Sysinternals tools (Autorunsc, PsExec) are *not* filtered
because cross-host runs of those are themselves a finding worth
analyst attention.

---

## 3. (If interactive) the agent drives the playbook

You'll see:

1. `case_open` — SHA-256 of the evidence (chain of custody starts here)
2. **Pool A** (persistence) and **Pool B** (exfil) subagents fork in parallel and run their tool sequences
3. Findings emerge tagged with `tool_call_id`, MITRE ATT&CK technique, and confidence (CONFIRMED / INFERRED / HYPOTHESIS)
4. `detect_contradictions` surfaces Pool A vs Pool B disagreements **before** the judge merges
5. `judge_findings` + `correlate_findings` apply credibility weighting + the SOUL.md ≥2 artifact-class rule
6. `manifest_finalize` builds the Merkle tree, signs with sigstore, writes `run.manifest.json`
7. (Optional) `ots_stamp` anchors the manifest to Bitcoin via OpenTimestamps for FRE 902(14) self-authentication

Output lands at `~/.findevil/cases/<case_id>/` (or inside the VM at `/home/sansforensics/find-evil/tmp/<case_id>/` in SIFT-VM mode).

---

## Recommended reading order if anything goes wrong

| Question | File to read |
|---|---|
| "How do I avoid false positives?" | `docs/false-positives.md` |
| "What do SUSPICIOUS / INDETERMINATE / NO_EVIL actually mean — and which findings do I act on first?" | `docs/verdict-semantics.md` |
| "What does the agent actually do during an investigation?" | `agent-config/PLAYBOOK.md` |
| "What's the architecture?" | `docs/architecture.md` |
| "How does the cryptographic chain-of-custody work end-to-end? What does FRE 902(14) require?" | `docs/cryptographic-attestation.md` |
| "What evidence is available?" | `docs/DATASET.md` |
| "What if a tool is missing?" | The agent will return `BinaryNotFound -32602`. Install the binary OR set the env var pointing at it (e.g. `VOLATILITY_BIN=/path/to/vol`). |
| "How do I verify a manifest someone else produced?" | `manifest_verify` MCP tool. Or `ots verify run.manifest.ots` for the Bitcoin anchor. |
| "How do I extend the tool surface?" | Each new MCP wrapper takes ~30-60 minutes following the pattern at `services/mcp/src/tools/vol_pslist.rs`. See the existing 12 tools for templates. |
| "I changed something — how do I confirm L1 will be happy without `docker compose up`?" | `bash scripts/run-all-smokes.sh` runs all 9 L1 smokes (rust-mcp + agent-mcp + verdict-policy + fleet-policy + demo-script + launcher + divergence + path-existence + smoke-regex-tests) plus the L0 lint gates (ruff check + ruff format --check) — 11 entries in ~25s with per-smoke pass/skip/fail status. |

---

## Anti-patterns

* **Don't** trust HYPOTHESIS-tier findings without verification. The agent prefixes them with the literal word "hypothesis:" — those are leads, not facts.
* **Don't** skip the synthetic-benign baseline (`goldens/synthetic-benign/`) — running on benign data first calibrates your false-positive floor.
* **Don't** modify evidence files. The chain-of-custody invariant (CLAUDE.md) is filesystem-enforced; any write to `/evidence/<case_id>/` from outside the agent invalidates the manifest's claims.
* **Don't** add `execute_shell` or any tool that takes arbitrary commands. The "narrow typed surface" is the architectural pitch; widening it forfeits that.

---

## End-of-investigation checklist

1. [ ] `manifest_verify` returns `overall=True`, all four sub-checks green
2. [ ] Findings table reviewed; CONFIRMED-tier findings traced back to their `tool_call_id` in `audit.jsonl`
3. [ ] Contradictions resolved or explicitly flagged in the report
4. [ ] Cross-host corroboration done (if multi-host case)
5. [ ] Synthetic-benign baseline run produced zero findings
6. [ ] `ots_stamp` Bitcoin anchor receipt obtained (if outbound network available)
7. [ ] Report rendered to PDF (the agent can do this; see `docs/reports/2026-04-26-srl2018-dc-investigation.pdf` for an example)

If all 7 are checked, you're done. If any are skipped, document the reason in the report's §8 (Limitations).
