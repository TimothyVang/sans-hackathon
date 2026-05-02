# Find Evil! — ${RELEASE_TAG}

**Submission for the SANS Find Evil! hackathon** ([findevil.devpost.com](https://findevil.devpost.com/)) — a Claude Code agent that investigates Windows host evidence and produces a signed verdict any third party can verify offline.

**Demo video:** ${DEMO_VIDEO_URL}

**Accuracy on NIST CFReDS Hacking Case:** ${ACCURACY}%

**Release date:** ${DATE}

**License:** Apache-2.0

---

## What it does

Find Evil! investigates Windows host evidence (`.e01` disk images, memory captures, EVTX logs) end-to-end and produces a signed verdict (`SUSPICIOUS` / `INDETERMINATE` / `NO_EVIL`) with four load-bearing properties:

1. **A typed MCP tool surface, no `execute_shell`.** 23 narrow Pydantic-validated tools — 12 Rust DFIR (`case_open`, `evtx_query`, `vol_pslist`/`vol_psscan`, `vol_malfind`, `mft_timeline`, `hayabusa_scan`, `yara_scan`, `usnjrnl_query`, `registry_query`, `prefetch_parse`, `vel_collect`) plus 11 Python crypto/ACH/memory/handoff. EVTX parsed in-process via the omerbenamram/evtx Rust crate (~1600× faster than python-evtx); AGPL/GPL tools (Hayabusa, Volatility3, Velociraptor) invoked through subprocess boundaries only — Apache-2.0 submission tree stays clean.

2. **Cryptographic chain of custody supporting a FRE 902(14) self-authenticating-evidence claim.** Three composed primitives: hash-chained audit JSONL (`prev_hash` per record) → `rs_merkle` Merkle root over canonical-JSON tool outputs → sigstore signature with Rekor transparency-log inclusion proof. Verifiable offline by `manifest_verify` — no network, no third-party servers. (Pre-A5 the chain tail-anchored to Bitcoin via OpenTimestamps; removed because judges scoring offline can't exercise the network call. Trade-off: `docs/cryptographic-attestation.md`.)

3. **Analysis of Competing Hypotheses as agent topology.** Two pools investigate the same evidence with opposing priors (persistence-biased vs. exfil-biased). Disagreements emit as `kind=contradiction` audit records *before* the judge merges — surfaced as first-class output, not hidden in consensus. Heuer's 1970s intelligence-analysis framework applied as live agent architecture.

4. **Self-score inside the cryptographic attestation.** The agent emits 6 `kind=judge_selfscore` audit records (one per SANS rubric criterion) *before* `manifest_finalize`. Because they land before the Merkle tree closes, the agent's own self-assessment is part of the signed manifest — judges can `grep '"kind":"judge_selfscore"' audit.jsonl` and see the agent's own score.

## How it's built

Five trust boundaries (see `docs/architecture.md` for Mermaid diagrams):

```
Evidence vault (read-only .e01)
  → SIFT tool subprocesses (unprivileged, sandboxed)
  → Two typed MCP servers
      • findevil-mcp (Rust)         — 12 DFIR tools, no execute_shell
      • findevil-agent-mcp (Python) — 11 crypto/ACH/memory/ACP tools
  → Claude Code agent loop (supervisor + forked Pool A/B subagents
    + verifier + judge + correlator + contradiction surface)
  → Crypto chain-of-custody (audit hash chain + rs_merkle + sigstore)
```

**Architectural approach per SANS rules:** **Direct Agent Extension (§1) + Custom MCP Server (§2).** Claude Code IS the agent; the typed MCP surface is the only verb set it has. There is no `execute_shell`, anywhere.

## Install

The tool accepts three credential modes; pick whichever you have:

```bash
# 1. Claude Code long-lived token (recommended for non-interactive judging)
export CLAUDE_CODE_OAUTH_TOKEN=<token>  # generated via 'claude setup-token'

# 2. Claude Code interactive session
claude auth login

# 3. Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...   # from console.anthropic.com; <$1/run

# Any of the above, then:
curl -fsSL https://raw.githubusercontent.com/<OWNER>/<REPO>/main/scripts/install.sh | bash
```

`scripts/install.sh` detects credentials in priority order and fails fast with a clear error listing all three options if none are present.

## Run

```bash
# Open an investigation. .mcp.json auto-spawns both MCP servers
# (findevil-mcp + findevil-agent-mcp) over stdio.
scripts/find-evil
# … or equivalently from this repo's root:
claude

# Then prompt: "investigate fixtures/nist-hacking-case/SCHARDT.001"
# The agent calls case_open → fork Pool A/B subagents → run DFIR tools →
# detect_contradictions → judge → correlate → manifest_finalize.

# Verify a completed run's chain-of-custody offline:
# Drive the manifest_verify MCP tool from any MCP client (Claude Desktop,
# Claude Code, ChatGPT) — no network, no third-party servers.
```

Headless single-shot: `bash scripts/find-evil-auto <evidence-path> --unattended`. Multi-host fleet: `python scripts/fleet_investigate.py && python scripts/fleet_correlate.py && python scripts/render_fleet_report.py`.

## Accuracy report

Self-reported per SANS rules, from the L3 nightly goldens CI workflow:

- **NIST CFReDS Hacking Case:** ${ACCURACY}% recall on 14 canonical findings
- **Synthetic benign baseline:** 0 findings (correct — negative control passes)
- **Hallucination rate:** tracked per run via verifier-rejected-finding count

See `goldens/<fixture>/expected-findings.json` for ground-truth declarations and `fixtures/` for source datasets (not bundled — pulled via `scripts/fetch-fixtures.sh`).

## Links

- Repository: https://github.com/<OWNER>/<REPO>
- Architecture deep-dive: `docs/architecture.md`
- Doc INDEX (status badge per file): `docs/README.md`
- Cryptographic attestation deep-dive: `docs/cryptographic-attestation.md`
- Showcase investigation report: `docs/reports/2026-04-26-srl2018-dc-investigation.md`
- Dataset documentation: `docs/DATASET.md`

## License

Apache-2.0 — see `LICENSE`. Submission + all original code MIT/Apache-2.0 compatible per SANS rules. AGPL/GPL tools (Hayabusa, Chainsaw, Volatility3, Velociraptor) are invoked as subprocesses only; they are not linked into the submission binaries.
