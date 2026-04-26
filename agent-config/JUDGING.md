# JUDGING.md — Rubric the agent self-scores against

The SANS Find Evil! 2026 judging criteria, verbatim. Read at session
start (CLAUDE.md "Agent investigation prompt" §0). Every investigation
must produce evidence each judge can point at — not just satisfy the
criteria internally. The mapping below names *which artifact in the
audit trail* answers each criterion.

## 1. Autonomous Execution Quality (tiebreaker)
> Does the agent reason about next steps, handle failures, and
> self-correct in real time?

**Demonstrate via:** the audit JSONL itself. Every iteration writes a
plan-step → tool-call → observation → next-plan-step record. Tool
failures appear as `tool_call.error` entries followed by a planner
record adjusting course (e.g. fallback tool, narrower scope, or
explicit "deferring" with reason). HEARTBEAT.md self-tests count too.
**Anti-pattern:** silent retry. Failures must be logged and named.

## 2. IR Accuracy
> Are findings correct? Hallucinations caught and flagged? Confirmed
> findings distinguished from inferences?

**Demonstrate via:** SOUL.md epistemic hierarchy. Every Finding carries
`level ∈ {CONFIRMED, INFERRED, HYPOTHESIS}`. CONFIRMED ↔ tool_call_id
+ raw excerpt. INFERRED ↔ ≥2 confirmed facts + `derived_from` cite.
HYPOTHESIS ↔ `"hypothesis:"` prefix. The verifier role re-runs every
cited tool_call before report write-out. The `detect_contradictions`
MCP tool flags within-run hallucinations; the judge merges
credibility-weighted across Pool A/B.

## 3. Breadth and Depth of Analysis
> How much case data can the agent handle? Depth on fewer types beats
> shallow coverage of many.

**Demonstrate via:** the case manifest's `evidence_inventory[]` lists
every artifact class touched (Prefetch, MFT, EVTX, Amcache, ShimCache,
USN, Registry, Memory, YARA hits, …) with bytes-scanned and rows-
returned per class. Depth is shown by the cross-artifact corroboration
chain — execution claims **must** cite ≥2 artifact classes (CLAUDE.md
non-negotiable + SOUL.md hard rule). One deep persistence chain across
4 artifact classes scores higher than 12 shallow EVTX queries.

## 4. Constraint Implementation
> Are guardrails architectural or prompt-based? Judges evaluate where
> security boundaries are enforced and whether they were tested for
> bypass.

**Demonstrate via:** the typed Rust MCP tool surface (Spec #2 §6, 11
tools). No `execute_shell`, no path traversal, every tool serializes
typed Input/Output. Architectural enforcement points:
- Read-only evidence opener (libewf in `case_open`, no mutation path).
- SHA-256 verification of image at open and at every tool re-execution.
- Hash-chained append-only audit JSONL (each line cites `prev_hash`).
- Tool-level `readOnlyHint`/`destructiveHint` annotations (commit
  `151510a`).
- L0 CI invariants guard for Amendment A2 (commit `ad4a36e`).
- Bypass tests live in `services/mcp/tests/` — UTF-8 truncation panic
  fix (`405117a`) is one example of a tested bypass attempt.
**Anti-pattern:** "the prompt says don't do X." Prompt-only guardrails
score lower than typed-surface enforcement.

## 5. Audit Trail Quality
> Can judges trace any finding back to the specific tool execution
> that produced it?

**Demonstrate via:** Finding → `tool_call_id` → JSONL audit record →
SHA-256 of the tool's stdout → `manifest_finalize` Merkle root →
`ots_stamp` Bitcoin anchor. The chain is verifiable offline by the
`manifest_verify` + `ots_verify` MCP tools — judges run these against
the submitted run manifest and reach the underlying tool execution
with one path. M2 crypto stack is the load-bearing answer; FRE
902(14) self-authenticating is the framing.

## 6. Usability and Documentation
> Can another practitioner deploy and build on this?

**Demonstrate via:** `scripts/find-evil` (local-mode launcher),
`scripts/find-evil-sift` (SIFT-VM SSH-bridge mode), `scripts/install.sh`
(three credential paths per Amendment A1), the Apache-2.0 license,
the published accuracy-benchmark repo (BUILD_PLAN_v2 §differentiator
10), and the four spec/plan documents (`docs/superpowers/`). A judge
who clones the repo and runs `scripts/find-evil` should reach a
working investigation in <5 minutes; a developer should be able to
add a new MCP tool by following the pattern in `services/mcp/src/
tools/prefetch_parse.rs` (reference implementation) without reading
external docs.

## End-of-investigation self-check

Before closing the case (before `manifest_finalize`), the supervisor
runs through this checklist and emits one record per criterion:

| # | Question | Answer style |
|---|----------|--------------|
| 1 | Did any tool call fail this run? If yes, did the audit log show explicit course-correction? | `failures=N corrections=N` |
| 2 | What % of Findings are CONFIRMED vs INFERRED vs HYPOTHESIS? | `C=X% I=Y% H=Z%` |
| 3 | How many artifact classes did this case touch? Which Findings cross ≥2? | `classes=[…] crossed=[…]` |
| 4 | Were any tool calls rejected by typed-surface validation this run? | `rejected=N reasons=[…]` |
| 5 | Does every Finding cite a tool_call_id? (must be 100%; verifier vetoes otherwise) | `cited=N/N` |
| 6 | Is the run reproducible from the manifest alone (no external state)? | `reproducible=yes/no` |

The six lines append to the audit JSONL with `kind="judge_selfscore"`
just before `manifest_finalize`. Judges can grep `kind=judge_selfscore`
to find the agent's own assessment alongside their own scoring.
