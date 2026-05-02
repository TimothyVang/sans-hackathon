# Find Evil! — ${RELEASE_TAG}

**Submission for the SANS Find Evil! hackathon** ([findevil.devpost.com](https://findevil.devpost.com/)) — automated, cryptographically-verifiable DFIR pipeline for the SANS SIFT Workstation.

**Demo video:** ${DEMO_VIDEO_URL}

**Accuracy on NIST CFReDS Hacking Case:** ${ACCURACY}%

**Release date:** ${DATE}

**License:** Apache-2.0

---

## What it does

Find Evil! investigates Windows host evidence (`.e01` disk images, memory captures, EVTX logs) end-to-end and produces findings with:

1. **Cryptographic chain-of-custody** — every MCP tool call is signed with `sigstore` (Rekor transparency-log inclusion proof), every finding is rooted in an `rs_merkle` append-only tree, and the per-run manifest is hash-chained record-by-record. Any party can verify the full run offline in under 60 seconds via the `manifest_verify` MCP tool — no network, no third-party servers — supporting a FRE 902(14) self-authenticating-evidence claim. (The OpenTimestamps + Bitcoin anchor that strengthened this story was removed under Amendment A5; see `docs/cryptographic-attestation.md` for the honest trade-off.)

2. **LLM-powered Analysis of Competing Hypotheses (ACH)** — two agent pools investigate the same evidence in parallel with opposing priors (persistence-biased vs. exfiltration-biased). A `ContradictionFound` event emits BEFORE reconciliation, surfacing real disagreements to the analyst instead of hiding them in a consensus-seeking single-agent output. Credibility-weighted judge merges at the end. This is Heuer's 1970s intelligence-analysis framework applied as live agent architecture.

3. **Typed Rust MCP server** — 11 narrow, typed tools (no `execute_shell` anywhere). Built-in EVTX parsing via the `omerbenamram/evtx` crate (~1600× faster than python-evtx); Hayabusa / Chainsaw / Volatility3 / Velociraptor invoked through subprocess boundaries only, keeping AGPL/GPL out of our MIT-Apache submission tree.

4. **Published accuracy benchmark** — the submission publishes its DFIR-Metric score (700 MCQs + 150 CTF tasks + 500 NIST cases) to [findevil-bench.dev](https://findevil-bench.dev/). No reference DFIR agent has previously published one.

## How it's built

Five trust boundaries (see `docs/architecture.md` for Mermaid diagrams):

```
Evidence vault (read-only .e01)
  → SIFT tool subprocesses (unprivileged, sandboxed)
  → Two typed MCP servers
      • findevil-mcp (Rust)        — 12 DFIR tools, no execute_shell
      • findevil-agent-mcp (Python) — 11 crypto/ACH/memory/ACP tools
  → Claude Code agent loop (supervisor + forked Pool A/B subagents
    + verifier + judge + correlator + contradiction surface)
  → Crypto chain-of-custody (audit hash chain + rs_merkle + sigstore)
```

**Architectural approach per SANS rules:** **Direct Agent Extension (§1) + Custom MCP Server (§2).** Claude Code IS the agent; the typed MCP surface is the only verb set it has. There is no execute_shell, anywhere. (Optional Next.js SPA + MCP Apps widgets are scheduled as a week-7 polish bonus per Amendment A2 §2.1, not on the critical path.)

**Trust boundaries** are explicit in `docs/architecture.md`. Prompt-based guardrails (SOUL.md epistemic hierarchy, HEARTBEAT canary) are clearly distinguished from architectural guardrails (read-only mount, typed MCP surface, Pydantic schema on findings, cryptographic manifest signing).

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

Under Amendment A2, Claude Code IS the primary interface — the entry point is the repo itself.

```bash
# Open an investigation. .mcp.json auto-spawns both MCP servers
# (findevil-mcp + findevil-agent-mcp) over stdio.
scripts/find-evil
# … or equivalently from this repo's root:
claude

# Then prompt the agent, e.g.:
#   "investigate fixtures/nist-hacking-case/SCHARDT.001"
# It will call case_open → fork Pool A/B subagents → run DFIR tools →
# detect_contradictions → judge → correlate → manifest_finalize.

# Verify a completed run's cryptographic chain-of-custody offline.
# manifest_verify (audit chain + Merkle root + sigstore signature) is
# exposed as an MCP tool from findevil-agent-mcp; any MCP client
# (Claude Desktop, Claude Code, ChatGPT) can drive it. No network,
# no third-party servers — supports a FRE 902(14) self-authenticating
# claim per docs/cryptographic-attestation.md.
```

## Accuracy report

Self-reported per SANS rules, from the `L3 nightly goldens` CI workflow:

- **NIST CFReDS Hacking Case:** ${ACCURACY}% recall on 14 canonical findings
- **Synthetic benign baseline:** 0 findings (correct — negative control passes)
- **Hallucination rate:** tracked per run via verifier-rejected-finding count
- **Full matrix:** [findevil-bench.dev](https://findevil-bench.dev/)

See `goldens/<fixture>/expected-findings.json` for the ground-truth declarations and `fixtures/` for the source datasets (not bundled — pulled via `scripts/fetch-fixtures.sh`).

## Try it

1. Clone this repo.
2. Install SIFT (from sans.org/tools/sift-workstation) or run in the `findevil/l1-devbase` Docker image.
3. Run `scripts/install.sh` (handles credential detection — three modes accepted).
4. Run `scripts/fetch-fixtures.sh` (pulls NIST + OTRF + Volatility samples).
5. Run `scripts/find-evil` (opens a Claude Code session with both MCP servers auto-spawned via `.mcp.json`).
6. In the session, prompt: *"investigate fixtures/nist-hacking-case/SCHARDT.001"*. The agent drives the full pipeline end-to-end and writes `run.manifest.json`.
7. Drive the agent's `manifest_verify` MCP tool against `run.manifest.json` to replay the audit chain + Merkle root + sigstore signature offline (no network).

## What we learned

- Option B (Claude Code subscription for the build swarm) beats Option A (metered API) when the build process itself is the cost center — the subscription's session-based limits are predictable and the developer never pays per-token.
- The ACH pattern is the quietest differentiator. Competitors see the cryptographic chain-of-custody and position against it; the dual-agent contradiction surface is the architectural move they can't match by adding code.
- DFIR-Metric benchmark publication is our single highest-ROI differentiator because the reference submission (Valhuntir) explicitly declines to publish accuracy numbers.

## What's next

- Expand to macOS/Linux evidence (deferred per `docs/superpowers/specs/2026-04-25-the-product-design.md` §14).
- Live network-capture ingestion.
- ACH pool strength tuning (multi-round debate is cost-prohibitive today).
- Community contributions to the DFIR-Metric benchmark to sharpen the leaderboard.

## Links

- Repository: https://github.com/<OWNER>/<REPO>
- Public benchmark: https://findevil-bench.dev/
- Architecture deep-dive: [`docs/architecture.md`](docs/architecture.md)
- Design specs: [`docs/superpowers/specs/`](docs/superpowers/specs/)
- Dataset documentation: [`docs/DATASET.md`](docs/DATASET.md)

## License

Apache-2.0 — see [`LICENSE`](LICENSE). Submission + all original code MIT/Apache-2.0 compatible per SANS rules. AGPL/GPL tools (Hayabusa, Chainsaw, Volatility3, Velociraptor) are invoked as subprocesses only; they are not linked into the submission binaries.
