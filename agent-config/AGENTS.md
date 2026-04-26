# AGENTS.md — Roles and Routing

Under Amendment A2 the agent runtime is Claude Code itself; the
roles below are spawned as forked subagents (`CLAUDE_CODE_FORK_SUBAGENT=1`)
from a single supervisor session. They are conceptual roles, not
separate processes — each one runs the same Claude with a
narrowly-scoped system prompt.

## supervisor
Owns the investigation plan. Reads `agent-config/PLAYBOOK.md` to pick
the per-evidence-type tool sequence, decomposes goals into sub-tasks
across Pool A and Pool B, dispatches the pools in parallel, then
calls verifier → judge → correlator → manifest_finalize → ots_stamp.
Never touches evidence directly; only dispatches and merges.
Emits the six `kind=judge_selfscore` audit records before
`manifest_finalize` per `agent-config/JUDGING.md`.

## Pool A — persistence-biased
Investigates the evidence assuming the attacker is *staying*. Uses
the typed MCP surface to look at:
- Run keys, RunOnce, Services (`registry_query`)
- Scheduled tasks (`evtx_query` event ID 4698, `registry_query`)
- WMI subscriptions, IFEO debugger hijacks (`registry_query`)
- LSASS-resident modules, driver tampering (`vol_pslist` +
  `vol_psscan` + `vol_malfind`)
- Prefetch + Amcache for execution provenance (`prefetch_parse`)

Pool A's bias means it weights persistence-shaped evidence higher
in confidence. Run the tools; emit Findings with `pool_origin=A`.

## Pool B — exfiltration-biased
Investigates assuming the attacker is *taking something*. Looks at:
- Staging directories, archive creation patterns (`mft_timeline`,
  `usnjrnl_query`)
- `certutil` / `bitsadmin` / `Invoke-WebRequest` execution
  (`evtx_query` 4688, `prefetch_parse`)
- Large-file rename-then-delete patterns (`usnjrnl_query`)
- USB writes, removable-media events (`evtx_query`)
- Suspicious outbound endpoints in EVTX or memory
  (`vol_pslist` cmdlines, `evtx_query` 5156)

Same MCP surface, different reasoning prior. Emit Findings with
`pool_origin=B`. The two pools run in parallel and may cite the
same `tool_call_id` with different confidence labels — that's a
contradiction, surfaced before the judge.

## verifier
Re-runs every Finding's cited `tool_call_id` via the
`verify_finding` MCP tool. The verifier spawns its own short-lived
findevil-mcp child process; output's SHA-256 must match the
original audit-log entry byte-for-byte. **Veto power:** any
Finding without a `tool_call_id` is rejected outright.
Disagreement on hash means the cited tool was re-run with the
same args and produced a different output — the verifier
downgrades or rejects depending on severity.

## judge
Calls `judge_findings` MCP tool. Credibility-weighted merge: each
pool's score = `base_confidence × pool_credibility`. Pools that
produced corroborating CONFIRMED findings build credibility;
pools that produced HYPOTHESIS-only get downweighted. Output is a
merged list with reconciled confidence labels and a per-Finding
explanation of which pool contributed what.

## correlator
Calls `correlate_findings` MCP tool. Enforces the SOUL.md ≥2
artifact-class rule: any "X executed" Finding must cite ≥2 distinct
artifact classes (Prefetch + Amcache+ShimCache, or EDR + memory).
Single-source claims auto-downgrade. Outcome is `kept` or
`downgraded` per Finding with a reason.

## Routing rules

- **Persistence questions** → Pool A is the lead, Pool B may
  contradict if it sees evidence the persistence is staging for
  exfil. Resolve via judge.
- **Exfiltration questions** → Pool B is the lead, Pool A may
  contradict if it sees evidence the staging is actually long-term
  storage (no outbound).
- **Both: identity/account questions** → both pools `evtx_query`
  the Security log; Pool A reads it as authentication-persistence
  (account creation, lateral movement to a new host as part of
  staying), Pool B reads it as exfil-precursor (RDP from a host
  that just downloaded a tool).
- **Live-process questions** → both pools run `vol_pslist` +
  `vol_psscan` + `vol_malfind`. Pool A flags processes by
  persistence path (run from `Temp`, lives in `services.exe`
  child tree); Pool B flags them by network behavior (cmdline
  contains internet IPs, has open sockets).
- **Report assembly** → supervisor, gated by verifier. Verifier
  rejects → supervisor re-dispatches (one retry, then escalates
  the Finding to HYPOTHESIS).

## Why this structure (Heuer's ACH applied as agent topology)

A consensus-seeking single-agent architecture would resolve
contradictions internally — invisible to the analyst. Find Evil's
Pool A + Pool B + judge surfaces the disagreement as a
first-class output (`kind=contradiction` audit record) BEFORE
reconciliation. The analyst sees both arguments and the
reconciliation; they can override the judge if they think Pool A
or B was right.

This is not a multi-LLM voting trick. It's Heuer's 1999 *Psychology
of Intelligence Analysis* operationalized: structure the reasoning
to disprove hypotheses, not to confirm them.
