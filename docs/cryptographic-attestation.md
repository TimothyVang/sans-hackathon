# Cryptographic Chain of Custody

This document is the canonical answer to "how does Find Evil's
cryptographic attestation work, and how do I verify a manifest
someone else produced?" The story is scattered across CLAUDE.md,
README.md, the DC investigation report, and the demo script — this
file collects the load-bearing claims in one place.

> **Why this matters:** SANS Find Evil! 2026 rubric criterion #5
> ("Audit Trail Quality") asks whether the agent's findings are
> independently verifiable by a third party with no trust in the
> agent itself. Find Evil's answer is "yes, by `manifest_verify`
> alone, plus optionally Bitcoin via `ots_verify` for time
> attestation." This is FRE 902(14) self-authenticating evidence —
> a court-of-law bar, not just a CI green check.

---

## The five-link chain

Every Find Evil! investigation produces a `run.manifest.json`
backed by five composed cryptographic primitives:

```
   evidence file (.e01 / .img / .evtx)
       │
       ▼  sha2 = 0.10 (Rust, in-process)
   image_hash (32-byte SHA-256, committed at case_open)
       │
       ▼  audit_append (append-only JSONL with prev_hash)
   audit chain  (each record: { kind, payload, prev_hash, seq, ts })
       │
       ▼  rs_merkle = 1.4 (Rust, in-process)
   Merkle tree over canonical-JSON record bytes
       │
       ▼  sigstore-python = 3.x (sigstore Fulcio cert + Rekor log)
   signature  (signed over the manifest body bytes)
       │
       ▼  opentimestamps-client (calendar → Bitcoin)
   OpenTimestamps proof (.ots) — ~1 hr to mature, then offline
```

Each link's role:

| # | Primitive | What it proves | Library |
|---|---|---|---|
| 1 | SHA-256 of the evidence | The image we read is the image we received | `sha2 = 0.10` (Rust) |
| 2 | Audit hash chain | No record was deleted, reordered, or back-dated after the fact | `services/agent/findevil_agent/crypto/audit.py` |
| 3 | rs_merkle tree | The set of records named in the manifest is the set the agent actually wrote | `rs_merkle = 1.4.0` (Rust) |
| 4 | sigstore signature | The manifest was produced by a key whose Fulcio cert is logged in Rekor — non-repudiable provenance | `sigstore = 3.x` (Python) |
| 5 | OpenTimestamps proof | The manifest existed AT OR BEFORE the named Bitcoin block — independent time attestation | `opentimestamps-client` |

**No single primitive is load-bearing alone.** A SHA-256 by itself
proves byte equality but not freshness; a Merkle root proves set
membership but not who built the set; a sigstore signature proves
identity but not time. The composition is the attestation.

---

## Where each link lives in the code

```
services/mcp/                                    ← (Rust DFIR tool MCP)
├── src/tools/case_open.rs                       — link 1: sha2 hash of evidence
└── (every tool emits _meta.output_sha256 over its canonical JSON output)

services/agent/findevil_agent/crypto/            ← (M2 crypto stack)
├── audit.py                                     — link 2: prev_hash chain
├── merkle.py                                    — link 3: rs_merkle tree
├── signer.py                                    — link 4: sigstore Fulcio + Rekor
├── manifest.py                                  — composes 2/3/4 into run.manifest.json
└── ots.py                                       — link 5: OpenTimestamps stamp + verify

services/agent_mcp/findevil_agent_mcp/tools/     ← (Python MCP wrapping the above)
├── audit_append.py                              ↘  one MCP tool per link
├── audit_verify.py                              ↘  10 tools total — see TOOLS.md
├── manifest_finalize.py                         ↘
├── manifest_verify.py                           ↘
├── ots_stamp.py                                 ↘
└── ots_verify.py                                ↘
```

The Rust side does the in-process content addressing (links 1 and
the per-tool output_sha256 that feeds the Merkle leaves). The
Python side composes the chain and signs.

---

## How a third party verifies offline

A judge, regulator, or counter-party who has zero trust in the
agent can verify a Find Evil! manifest with these tools alone:

```bash
# 1. The sigstore signature, audit chain, and Merkle root.
#    No network required (the manifest is self-contained).
#    Direct library call — no MCP server, no JSON-RPC plumbing.
uv run --directory services/agent python -c "
from pathlib import Path
from findevil_agent.crypto.manifest import verify_manifest
case = Path('<absolute-path-to-case-dir>')
r = verify_manifest(case / 'run.manifest.json',
                    audit_log_path=case / 'audit.jsonl')
print(r)
"
# Returns: ManifestVerification(audit_chain_ok=True, merkle_root_ok=True,
#                               leaf_count_ok=True, signature_present=True,
#                               overall=True)
# Any field becomes a string instead of True on failure, naming the
# precise reason (e.g. 'audit chain seq=4 prev_hash mismatch').

# 2. The Bitcoin anchor (mature ~1hr after ots_stamp).
#    Requires the third-party `opentimestamps-client` CLI.
ots verify run.manifest.ots
# Returns: success + Bitcoin block height + UTC timestamp
```

For a fuller workout that also exercises `audit_verify`,
`detect_contradictions`, `judge_findings`, and `correlate_findings`
through the actual MCP server (matching the live agent's flow),
run the smoke harness against the same case dir:

```bash
uv run --directory services/agent_mcp \
    python ../../scripts/agent-mcp-smoke.py \
    --real-evidence <absolute-path-to-case-dir>
```

The smoke spawns the server as a subprocess (matching `.mcp.json`),
drives it over piped stdio, and reports pass/fail per stage. This is
heavier than the direct library call but proves the MCP wire format
also passes — useful when verifying that what the live agent emits
is what the verifier consumes.

`manifest_verify` rebuilds:

1. The audit chain by walking `prev_hash` SHA-256 links from `seq=0`
   forward — first mismatch reports the seq + field that diverged.
2. The Merkle tree from the manifest's `leaves[]` array — declared
   `merkle_root_hex` must match the rebuilt root byte-for-byte.
3. The sigstore signature against the canonical body bytes — body
   is `merkle_root_hex || finalized_at || case_id || run_id || ...`
   in the canonical-JSON ordering enforced by `manifest.py`.

If all three pass, `overall=true`. Any one fails → `overall=false`
with a precise diagnostic naming the field and the expected vs
actual value. Tampering is loud; silent tampering is impossible.

---

## What FRE 902(14) requires and why this meets it

[Federal Rule of Evidence 902(14)](https://www.law.cornell.edu/rules/fre/rule_902)
("Certified Records Generated by an Electronic Process or System")
admits a digital record as **self-authenticating** — meaning the
proponent doesn't need to call a witness to authenticate it — when:

1. The record was generated by a process or system shown to produce
   an accurate result, and
2. A certification accompanies the record establishing its
   integrity through:
   a. Cryptographic evidence (hashing, digital signatures), AND
   b. A trusted timestamp from an independent third party.

Find Evil!'s manifest meets both prongs:

- **Prong (a) — accurate process:** the typed Rust MCP server has no
  `execute_shell`; every tool is a narrow Pydantic-validated wrapper
  with `deny_unknown_fields`. Tool outputs are content-addressed by
  SHA-256. The `verify_finding` MCP tool re-executes any cited
  `tool_call_id` and confirms the original output's hash matches.
  Reproducibility is built in.
- **Prong (b) — trusted timestamp:** OpenTimestamps anchors the
  manifest's Merkle root in the Bitcoin blockchain via independent
  calendar servers (default: `alice.btc.calendar.opentimestamps.org`,
  `bob.btc.calendar.opentimestamps.org`, `finney.calendar.eternitywall.com`).
  Once the proof matures (~1 hour wall-clock), the timestamp is
  offline-verifiable forever — no need to trust the calendars or
  the agent.

The combination is the load-bearing claim: a judge looking at a
`run.manifest.json` + `run.manifest.ots` three years from now can
verify the run's integrity without trusting Find Evil!, the
analyst, or any party except Bitcoin's proof-of-work chain.

---

## The negative test (live demonstration)

The DC investigation report (§7) demonstrates tamper detection
end-to-end. Flip any byte of any field; verification fails with a
diagnostic that names exactly what diverged:

```bash
# Tamper with the Merkle root field of an existing manifest:
python -c "
import json, pathlib
p = pathlib.Path('run.manifest.json')
d = json.loads(p.read_text())
d['merkle_root_hex'] = 'ff' * 32   # 64 hex chars = 32 bytes
p.write_text(json.dumps(d, indent=2, sort_keys=True))
"

# Verify — expect failure with diagnostic:
# manifest_verify { manifest_path: "run.manifest.json" }
# →
# {
#   "overall": false,
#   "audit_chain_ok": true,
#   "merkle_root_ok": false,
#   "merkle_root_detail": "declared root ff..ff != rebuilt fbc25852755b...",
#   "signature_present": true
# }
```

The audit chain still verifies (we didn't tamper with the chain),
but the Merkle root fails — the rebuilt root from `leaves[]` is
the original `fbc25852755b...`, not the `ff..ff` we wrote in.
Same shape if you tamper with any audit record (chain breaks at
the seq you altered) or any signed body field (signature
verification fails).

This is exercised on every `agent-mcp-smoke.py` run as a deliberate
negative test — see `scripts/agent-mcp-smoke.py` "10. tampered
manifest is rejected" step.

---

## Where the judge_selfscore fits

Per `agent-config/JUDGING.md`, the supervisor emits 6
`kind=judge_selfscore` audit records before `manifest_finalize`,
one per SANS rubric criterion. Because the records land in the
audit chain BEFORE the Merkle tree closes, **the agent's own
self-score is itself part of the cryptographic attestation**.

What this means in practice: a judge `grep`ing
`'"kind":"judge_selfscore"' audit.jsonl` sees the agent's
assessment of how it did against the same rubric the judge is
using. The agent could not have edited the score after seeing
the result — the chain → Merkle → signature triangle would
break. This is the tiebreaker move in the Devpost demo
(Beat 8 of `docs/demo-script-a2.md`).

---

## What this attestation does NOT prove

Honest disclosure (per `docs/false-positives.md` and SOUL.md):

- **Not the truth of the findings.** The chain proves the agent ran
  the named tool calls and recorded the named outputs — it does
  not prove those outputs *correctly identify* malicious activity.
  An agent emitting wrong analysis with cryptographic precision
  is still emitting wrong analysis. The `verify_finding` veto +
  the SOUL.md ≥2-artifact correlator + the Pool A vs B
  contradiction surface are the *epistemic* guardrails; the chain
  is the *integrity* guardrail. Both are needed.
- **Not the trustworthiness of the SIFT VM or Volatility's symbol
  cache.** If the SIFT VM's vol3 is compromised before the
  agent runs, the SHA-256 of the tool output is the SHA-256 of
  the *compromised* output. Defense-in-depth (read-only mounts,
  unprivileged user, no `execute_shell`) is the architectural
  layer; the cryptographic layer assumes those guardrails hold.
- **Not the absence of evidence.** A clean manifest covers the
  evidence the agent looked at. Evidence not collected (e.g. a
  full disk image from a host where only memory was acquired)
  is not part of the chain. The DC investigation report §8
  enumerates this caveat explicitly.

---

## References

- CLAUDE.md "Non-negotiable invariants" (audit-log append-only,
  every Finding cites a `tool_call_id`)
- `agent-config/SOUL.md` (epistemic hierarchy: CONFIRMED >
  INFERRED > HYPOTHESIS)
- `agent-config/JUDGING.md` (rubric + judge_selfscore wiring)
- `docs/reports/2026-04-26-srl2018-dc-investigation.md` (real-
  evidence end-to-end run, including §7 tamper detection live demo)
- `scripts/agent-mcp-smoke.py` (the negative test runs in CI on
  every L1 build per `docker/l1-compose.yml`)
- [Federal Rule of Evidence 902(14)](https://www.law.cornell.edu/rules/fre/rule_902)
- [sigstore-python documentation](https://github.com/sigstore/sigstore-python)
- [OpenTimestamps protocol](https://opentimestamps.org)
