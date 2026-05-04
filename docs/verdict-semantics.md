# Verdict Semantics

This document is the analyst-facing answer to "what does each
verdict mean, and how seriously should I take it?" The verdict is
the top-line summary in `verdict.json`, the per-case `REPORT.pdf`,
and the fleet `FLEET_REPORT.pdf` rollup. The triage policy below
mirrors the rule in `scripts/find_evil_auto.py::compute_verdict`.

## The three verdicts

### `SUSPICIOUS`

The agent surfaced findings that warrant immediate analyst review.
At least one of:

1. **Any `CONFIRMED`-tier finding.** A finding the verifier
   re-executed and matched against the original tool output's
   SHA-256 byte-for-byte. The cited `tool_call_id` is real, the
   tool output is reproducible, the claim is fact-grounded. Do
   not dismiss without reviewing.
2. **DKOM (T1014) at `INFERRED`-tier or higher.** The
   `vol_pslist` + `vol_psscan` divergence is the textbook
   rootkit-unlinking signature; the agent emits this as
   `INFERRED` because two independent tool outputs corroborate.
   The judge may downgrade the *merged* confidence, but the
   underlying pslist/psscan number difference is objectively
   visible — bumping the verdict to SUSPICIOUS for T1014 ensures
   the rootkit signal isn't silently buried.
3. **Any T1055 (Process Injection) at `INFERRED`-tier or higher.**
   `vol_malfind` flagged RWX VADs with MZ headers in unexpected
   locations. Two-tool corroboration (the VAD scan plus the
   parent-process attribution from `vol_pslist`) makes this
   INFERRED-grade evidence.

**What to do:** triage immediately. Pull the per-case
`REPORT.pdf`, read the Findings detail section, scan the audit
chain. If the finding is CONFIRMED, the cited tool call is
guaranteed to reproduce — re-run `verify_finding` to convince
yourself. Do not act on the verdict alone; act on the evidence
the verdict points at.

### `INDETERMINATE`

Findings exist but at HYPOTHESIS-only tier, or covering
low-severity techniques. The agent saw something, named what it
saw, did not have enough corroboration to upgrade to INFERRED or
CONFIRMED.

**What to do:** review when convenient. The per-case `REPORT.pdf`
explains every HYPOTHESIS finding's reasoning; some will be true
positives the agent couldn't corroborate (e.g. only one artifact
class touched, or the verifier downgraded a Pool A claim that
Pool B contradicted). Some will be false positives. The analyst
decides which.

If a fleet has many INDETERMINATE hosts (10/22 in the
`fleet-20260426T055440Z` run), the cross-host correlations in
`FLEET_REPORT.pdf` are usually more useful than triaging each
host's HYPOTHESES individually. Cross-host recurrence is a
correlation lead, not a second artifact class; execution or
compromise claims still need artifact-class corroboration on the
affected host.

### `NO_EVIL`

The agent ran the per-evidence-type playbook and emitted **zero**
findings. Either the evidence really is clean, or the agent's
tool surface didn't reach the artifact class where the badness
lives. Not a clean bill of health by itself.

**What to do:** confirm the playbook actually ran (audit JSONL
should have ≥4 tool_call_start records for memory, ≥3 for evtx).
If the agent only got as far as `case_open` (e.g. the evidence
type detected as `unknown`), upgrade the manual triage —
`NO_EVIL` from a one-tool run is meaningless. The `findings_summary`
field in `verdict.json` includes the by_confidence breakdown
({CONFIRMED: 0, INFERRED: 0, HYPOTHESIS: 0, total: 0} for a true
NO_EVIL); a `total: 0` with `agent: "find-evil-auto"` and a
healthy audit chain (≥6 records) is high-confidence clean.

## What the verdict does NOT mean

Honest disclosure (echoing `docs/false-positives.md`):

- **Not "the host is compromised" / "the host is clean".** The
  verdict reflects what the agent *saw*. Evidence the agent did
  not collect (network captures, EDR telemetry from another
  vendor, browser history) is outside the chain. SUSPICIOUS does
  not mean "compromised"; INDETERMINATE does not mean "more work
  needed" by itself; NO_EVIL does not mean "definitely safe".
- **Not a substitute for SOUL.md epistemic hierarchy.** Inside a
  SUSPICIOUS verdict there are still per-finding tiers
  (CONFIRMED > INFERRED > HYPOTHESIS). The verdict aggregates;
  the per-finding tiers are how you decide which claim to act on
  first.
- **Not a claim that parsed EVTX rows are suspicious by themselves.**
  EVTX row counts, Event ID histograms, and normalized timeline rows
  are coverage/summary data. They become verdict-driving findings
  only when the event semantics support an analyst-reviewable claim.
- **Not a final-and-binding judgement.** The verdict is computed
  deterministically from the merged findings; it is not an
  "intelligent recommendation". The intelligence is in the
  finding emission and ACH judging upstream of `compute_verdict`;
  the verdict itself is a pure function of the merged
  finding list, designed to be reproducible across runs of the
  same evidence (modulo Volatility symbol-cache state).

## Triage flow

```
fleet investigation done
       │
       ▼
12 SUSPICIOUS hosts ────► triage immediately
                          - Open per-case REPORT.pdf
                          - For each Finding: tool_call_id, MITRE
                            technique, confidence
                          - CONFIRMED → re-run verify_finding to
                            personally see the tool output
                          - INFERRED → identify the ≥2 artifact
                            classes; check the agent's reasoning
                          - HYPOTHESIS → decide: pursue or dismiss
       │
       ▼
10 INDETERMINATE hosts ─► defer to FLEET_REPORT cross-host pass
                          - cross_host_processes table (≥4-host
                            entries are real signal)
                          - temporal_clusters figure (multi-host
                            simultaneous-second runs are
                            attacker-tooling-or-IR signature)
                          - judge_selfscore aggregate (criterion 3:
                            artifact classes touched per host)
       │
       ▼
0 NO_EVIL hosts ────────► spot-check 1-2 to confirm playbook ran
                          (audit JSONL ≥6 records). If yes, mark
                          done.
```

## When to override the verdict

The compute_verdict function deliberately lives in 25 lines of
Python — it is not a black box. If your operational context
disagrees with the policy (e.g. you treat T1098 Account
Manipulation at HYPOTHESIS-tier as SUSPICIOUS where the policy
says INDETERMINATE), edit
`scripts/find_evil_auto.py::compute_verdict`. The verdict is
deterministic policy, not learned classifier; changing the policy
is a code change with a clear diff and CI run.

## References

- `scripts/find_evil_auto.py::compute_verdict` — the
  authoritative implementation (25 lines).
- `agent-config/SOUL.md` — the epistemic hierarchy that defines
  CONFIRMED / INFERRED / HYPOTHESIS at the per-finding level.
- `agent-config/JUDGING.md` §End-of-investigation — the SANS
  rubric criteria the agent self-scores against.
- `docs/false-positives.md` — the architectural and operational
  layers that reduce false-positive rate.
- `docs/cryptographic-attestation.md` — the chain that proves
  the verdict was computed from the actual tool outputs the agent
  recorded.
