# Submission Notes — Find Evil!

> **For the SANS Find Evil! 2026 judge.** This file is the
> second thing to read after `README.md`. Everything below is a
> navigation aid into the rest of the repo — claims live in the
> source files cited; this file does not duplicate them.

| Field | Value |
|---|---|
| Project | Find Evil! — Cryptographically-Verifiable DFIR Agent |
| Repo | https://github.com/TimothyVang/sans-hackathon |
| Devpost URL | *(populated at `v-submit` tag time by `scripts/package-devpost.sh`; see the Devpost project page)* |
| License | Apache-2.0 ([LICENSE](LICENSE)) |
| SANS deadline | 2026-06-15 22:45 CDT |
| Notes drafted at | commit `1aa8dc8` (2026-04-26) |

**Elevator pitch.** A DFIR agent built on the SANS SIFT
Workstation that takes a memory image, EVTX log, or disk image
and produces a signed verdict — `SUSPICIOUS`,
`INDETERMINATE`, or `NO_EVIL` — with the full reasoning trace
cryptographically attested through a five-link chain ending in
the Bitcoin blockchain. Two adversarial agent pools (Pool A
persistence-biased, Pool B exfil-biased) investigate the same
evidence in parallel; the contradiction surface is itself a
first-class output. (Source: [README.md](README.md) §"What it
is" + §"What's distinctive".)

---

## Read order — judge's first 30 minutes

| Order | File | Time | Why |
|---|---|---|---|
| 1 | [`README.md`](README.md) | ~2 min | Project framing, the five distinctive claims, repo layout |
| 2 | [`agent-config/JUDGING.md`](agent-config/JUDGING.md) | ~3 min | The SANS 6-criterion rubric verbatim + the agent's own self-score checklist (the agent is graded against this and `grep`-able from the audit chain — see [Tiebreaker](#tiebreaker-self-score) below) |
| 3 | [`docs/demo-script-a2.md`](docs/demo-script-a2.md) | ~5 min | The 5-minute Devpost video walkthrough, beat-by-beat with rubric mapping |
| 4 | [`docs/cryptographic-attestation.md`](docs/cryptographic-attestation.md) | ~5 min | The five-link chain, FRE 902(14) prong-by-prong analysis, third-party offline-verification recipe (rubric criterion 5) |
| 5 | [`docs/false-positives.md`](docs/false-positives.md) | ~3 min | Three architectural FP layers + four operational habits (rubric criterion 2) |
| 6 | [`CLAUDE.md`](CLAUDE.md) §"Project state" + §"Document hierarchy" + §"Spec/code divergences" | ~5 min | Current shipped state, document precedence, 7 documented divergences (all downstream-clean — see [Divergences](#documented-speccode-divergences) below) |

Everything else in `docs/` is depth — read on demand.

---

## Quick verification recipe (no SIFT VM needed, ~5 min)

These three commands confirm the smokes are green and both MCP
servers dispatch correctly. Run them from a clean clone:

```bash
git clone https://github.com/TimothyVang/sans-hackathon.git find-evil
cd find-evil

# 1. The full local smoke loop — Rust + Python + lint + audit + dispatch.
#    Mirrors what L1 GHA enforces. Should print "OK - 14 passed".
bash scripts/run-all-smokes.sh

# 2. The dashboard's Vitest suite (8 tests across audit-tail + path
#    allow-list).
pnpm install --frozen-lockfile
pnpm --filter @findevil/web test

# 3. The Rust workspace test suite, locked.
cargo test --workspace --locked
```

If you have an `.e01` / memory image + a configured SIFT VM,
add a fourth step:

```bash
# 4. End-to-end Tesla mode. Produces case dir + signed manifest +
#    REPORT.pdf in tmp/auto-runs/auto-<uuid>/.
bash scripts/find-evil-auto <evidence-path> --unattended
```

The SIFT VM setup steps are in [`CLAUDE.md`](CLAUDE.md) under
"Launchers under Amendment A2"; see also
[`scripts/sift-vm-setup.sh`](scripts/sift-vm-setup.sh).

---

## What ships vs what's deferred

Setting expectations honestly so you can score the right thing.

### Ships (in this submission)

| Capability | Where it lives |
|---|---|
| 25 typed MCP tools — 12 Rust DFIR + 13 Python crypto/ACH/memory/ACP | [`services/mcp/`](services/mcp/) + [`services/agent_mcp/`](services/agent_mcp/) — table in [`CLAUDE.md`](CLAUDE.md) §"Agent investigation prompt" |
| 7 agent-config role/identity prompts wired for Claude Code | [`agent-config/`](agent-config/) (SOUL, AGENTS, PLAYBOOK, TOOLS, MEMORY, HEARTBEAT, JUDGING) |
| Five-link cryptographic chain-of-custody | [`docs/cryptographic-attestation.md`](docs/cryptographic-attestation.md) |
| Tesla-mode single-command orchestrator | [`scripts/find-evil-auto`](scripts/find-evil-auto) |
| 22-host fleet pipeline (investigate → correlate → render) | `scripts/fleet_*.py` (see [`docs/reports/2026-04-26-srl2018-dc-investigation.md`](docs/reports/2026-04-26-srl2018-dc-investigation.md) for a real run) |
| SSE audit-log tail + dashboard scaffold + `/debug` live event viewer | [`apps/web/`](apps/web/) — Next.js 15 + Tailwind v4, handler at `app/api/audit/route.ts`, iterator at `lib/audit-tail.ts` |
| `kind=judge_selfscore` records in the audit chain BEFORE manifest finalize | [`agent-config/JUDGING.md`](agent-config/JUDGING.md) §"End-of-investigation self-check" |

### Gated on Claude Design pass (Phase 5/6 of A3)

| Capability | Status |
|---|---|
| 5 pixel-art agent sprites (Pool A / Pool B / Verifier / Judge / Correlator) | Component contracts + state-derivation are scaffolded in `apps/web/components/sprites/`; visuals will swap in during the Claude Design pass per [Amendment A3](docs/superpowers/specs/2026-04-26-amendment-a3-agent-army-and-dashboard.md) §3 |
| AuditBeadString chrome polish | Same — bead state derives from the SSE audit stream today; the NES.css visual treatment lands in Phase 5/6 |

### Deferred / out of scope (intentional)

| Item | Why |
|---|---|
| `apps/mcp-widgets/` (M3 Anthropic MCP App widgets) | Deferred per A2 §2.1; A3 §2.1 promotes only `apps/web/` back onto the critical path |
| Pre-A2 in-container `find-evil` CLI + `.deb` package | Cut by PR #4 (2026-04-27); see [`docs/runbooks/dockerfile-a2-decision.md`](docs/runbooks/dockerfile-a2-decision.md) "DECISION TAKEN — Option B" header. Claude Code IS the orchestrator under A2, so the in-container wrapper had no runtime to invoke |
| Networked IBM-ACP HTTP transport | A3 records ACP handoffs to `audit.jsonl` only; HTTP transport for fleet/multi-host is out of scope for the submission ([A3 §2.3](docs/superpowers/specs/2026-04-26-amendment-a3-agent-army-and-dashboard.md)) |
| Hermes runtime sidecar | Deferred per A2; A3 ports the FTS5 cross-case-memory pattern into `services/agent_mcp/` directly without the runtime dep |

---

## Cryptographic attestation (rubric criterion 5)

The load-bearing claim: **a third party can verify any
submitted manifest offline, three years from now, without
trusting Find Evil! or the analyst.**

The five-link chain (full detail:
[`docs/cryptographic-attestation.md`](docs/cryptographic-attestation.md)):

```
evidence file
   ↓ sha2 (Rust, in-process)            ← link 1: image_hash committed at case_open
audit.jsonl with prev_hash chain        ← link 2: append-only, tamper-evident
   ↓ rs_merkle tree over canonical-JSON ← link 3: set membership of records
manifest body
   ↓ sigstore (Fulcio cert + Rekor)     ← link 4: non-repudiable identity
signature
   ↓ opentimestamps (calendar → BTC)    ← link 5: independent time attestation
```

**How a judge verifies offline** (no MCP plumbing needed; direct
library call):

```bash
uv run --directory services/agent python -c "
from pathlib import Path
from findevil_agent.crypto.manifest import verify_manifest
case = Path('<absolute-path-to-case-dir>')
print(verify_manifest(case / 'run.manifest.json',
                      audit_log_path=case / 'audit.jsonl'))
"
```

Returns a `ManifestVerification` with `audit_chain_ok`,
`merkle_root_ok`, `leaf_count_ok`, `signature_present`, and
`overall` — any field becomes a string instead of `True` on
failure, naming the precise reason (e.g. `"audit chain seq=4
prev_hash mismatch"`).

For the Bitcoin anchor (mature ~1 hour after `ots_stamp`):

```bash
ots verify run.manifest.ots
```

The MCP-tool path (`manifest_verify` + `ots_verify`) is the
same logic exposed through the Python MCP server — equivalent
output, useful for in-session verification by the agent itself.
Both paths are exercised on every L1 CI build via
[`scripts/agent-mcp-smoke.py`](scripts/agent-mcp-smoke.py)
(including a deliberate negative test that tampers with a
manifest field and confirms verification fails with the exact
diagnostic).

**Why this matches FRE 902(14)** (self-authenticating
electronic evidence): typed-surface accuracy + Bitcoin-anchored
trusted-timestamp = both prongs satisfied. Prong-by-prong
analysis in
[`docs/cryptographic-attestation.md`](docs/cryptographic-attestation.md)
§"What FRE 902(14) requires and why this meets it".

### Tiebreaker self-score

Per [`agent-config/JUDGING.md`](agent-config/JUDGING.md), the
agent emits 6 `kind=judge_selfscore` records (one per SANS
rubric criterion) **into the audit chain BEFORE
`manifest_finalize`**. Because they land before the Merkle
tree closes, the agent's own self-assessment is itself part of
the cryptographic attestation — the agent could not have
revised the score after seeing it. Judges grep for them:

```bash
grep '"kind":"judge_selfscore"' tmp/auto-runs/auto-<uuid>/audit.jsonl | jq .payload
```

---

## Adversarial agents pattern (rubric criteria 1 + 2)

The agent is **not** a single consensus-seeking model. It is
Heuer's Analysis of Competing Hypotheses applied as agent
topology:

```
        [Supervisor — Claude Code, off-screen]
               │
        ┌──────┴──────┐
     [Pool A]       [Pool B]            ← opposing priors:
   persistence       exfil                A = persistence-biased
        │              │                  B = exfil-biased
        └──────┬───────┘
               ▼
       [detect_contradictions]           ← surfaces disagreement
               ▼                          BEFORE the judge merges,
          [Verifier]                      named in the audit chain
               ▼
           [Judge]                       ← credibility-weighted merge
               ▼
         [Correlator]                    ← enforces SOUL.md ≥2-artifact rule
               ▼
       [manifest_finalize]
```

Why this is genuinely Heuer's ACH (not a rebrand of
ensemble-voting): see
[`agent-config/AGENTS.md`](agent-config/AGENTS.md) §"Why this
structure (Heuer's ACH applied as agent topology)".

**Cross-case memory + structured handoff** (Amendment A3
additions; the prompts know when to call them):

| Tool | Caller | When |
|---|---|---|
| `memory_recall` | Pool A, Pool B (and judge if cross-checking) | Before drafting a Finding — "have we seen this IOC / hash / TTP before?" Returns prior-case hits ranked by BM25 × 90-day decay |
| `memory_remember` | Pool A, Pool B (post-CONFIRMED only) | Seeds the cross-case index after the judge confirms a finding. HYPOTHESIS-tier findings don't get remembered |
| `pool_handoff` | Verifier → Judge (always); Pool A → Pool B (exfil context); supervisor → any role | IBM-ACP envelope written to the audit chain as `kind="acp_handoff"`; `correlation_id` threads replies |

The full prompt text wiring these into Pool A / Pool B /
verifier / judge behavior is in
[`agent-config/AGENTS.md`](agent-config/AGENTS.md)
§"Cross-case memory + structured handoff (A3 §2.2 / §2.3)".

The contradiction surface, the credibility-weighted judge, and
the SOUL.md ≥2-artifact correlator are also the FP-prevention
spine — see
[`docs/false-positives.md`](docs/false-positives.md)
§"Layer 2 — Agent-level filtering".

---

## Documented spec/code divergences

The specs were written 2026-04-23; code has shipped since
2026-04-24. Where they disagree the shipped code wins, but
**every active divergence is documented and machine-checked**.

[`CLAUDE.md`](CLAUDE.md) §"Spec/code divergences (code wins)"
enumerates 7 entries (Rust toolchain pin, committed
`Cargo.lock`, the dropped pre-A2 CLI, the 12th Rust MCP tool,
hand-rolled MCP server, swarm package name, and the A3
MemoryStore phrase-quoting fix). You can confirm the cleanup
is locked by running:

```bash
python scripts/divergence-smoke.py
```

Expected last line:
`OK - all 6 active divergences are downstream-clean.`
(The 7th — `Cargo.lock` is committed — is declarative-only and
asserted by `.gitignore`'s explicit comment, not a regex.)

The smoke scans every active text file in the repo and asserts
no "bad half" of a documented divergence has resurfaced. Wired
into both [`docker/l1-compose.yml`](docker/l1-compose.yml) and
[`scripts/run-all-smokes.sh`](scripts/run-all-smokes.sh).

---

## Anticipated judge questions

**"Why no real-world end-to-end run in the demo video?"**
The demo video shows a Tesla-mode investigation against a real
memory image (Beat 3 of
[`docs/demo-script-a2.md`](docs/demo-script-a2.md)) and a
22-host fleet rollup against the SANS HACKATHON-2026 SRL-2018
dataset (Beat 6). The full analyst-facing investigation report
is
[`docs/reports/2026-04-26-srl2018-dc-investigation.md`](docs/reports/2026-04-26-srl2018-dc-investigation.md)
(PDF: 1.3 MB; 22-host fleet rollup at §9.1). The fleet
artifacts live under `tmp/fleet-runs/fleet-20260426T055440Z/`.

**"Why doesn't the dashboard have real sprites?"**
Component contracts and state derivation are scaffolded in
[`apps/web/components/sprites/`](apps/web/components/sprites/);
the pixel-art visuals are gated on the Claude Design pass
called out in [Amendment A3](docs/superpowers/specs/2026-04-26-amendment-a3-agent-army-and-dashboard.md)
Phase 5/6. The audit-bead string and hash-chain badge already
update live from the SSE stream
([`apps/web/lib/audit-tail.ts`](apps/web/lib/audit-tail.ts) +
[`apps/web/app/api/audit/route.ts`](apps/web/app/api/audit/route.ts)).

**"What happens if I install on Windows?"**
Windows-friendly throughout. The smoke runner gates ANSI
colors on `[ -t 1 ]` so Windows `cmd` without VT escapes stays
plain ASCII. The `find-evil` family of launchers is bash, but
runs cleanly under Git Bash / WSL. The Tesla-mode orchestrator
SSHes into a SIFT VM regardless of the host OS, so the host
platform does not need DFIR tools installed.

**"Where's the LangGraph supervisor / FastAPI service /
in-container CLI?"**
Dropped per [Amendment A2](docs/superpowers/specs/2026-04-25-amendment-a2-claude-code-primary-interface.md)
§2.1. Claude Code IS the orchestrator; the streaming UX is
Claude Code's terminal; the entry point is `scripts/find-evil`
(or `claude` directly). The dropped pre-A2 modules are
guarded against re-introduction by the L0 amendment-A2-guard
GHA job.

**"`Cargo.lock` is committed — is that a mistake?"**
No — `findevil-mcp` ships as a binary (not a library), so the
lockfile is committed deliberately.
[`.gitignore`](.gitignore) carries an explicit comment to that
effect; documented as the 2nd divergence in
[`CLAUDE.md`](CLAUDE.md).

---

## Contact

| Channel | Where |
|---|---|
| Maintainer | TimothyVang on GitHub |
| Issues | https://github.com/TimothyVang/sans-hackathon/issues |
| Pull requests | https://github.com/TimothyVang/sans-hackathon/pulls |

For Claude-Code-driven investigation questions, the agent-config
prompts ([`agent-config/`](agent-config/)) are self-contained —
opening `claude` from the repo root auto-loads them via
[`.mcp.json`](.mcp.json) and the agent-investigation prompt at
the top of [`CLAUDE.md`](CLAUDE.md).
