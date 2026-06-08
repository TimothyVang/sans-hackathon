---
date: 2026-06-08
description: Recurring VERDICT patterns — investigation tradecraft, the corroboration rule, and how to code in this repo.
tags: [brain, patterns]
---

# Patterns

## Investigation patterns

- **The ≥2-artifact-class rule for execution.** "X executed" requires two distinct artifact
  classes (Prefetch + Amcache/ShimCache/UserAssist, or EDR + memory). `correlate_findings`
  auto-downgrades single-source claims. This is the SOUL.md rule and it is load-bearing.
- **DKOM disambiguation before T1014.** `vol_pslist` vs `vol_psscan` divergence is the classic
  rootkit signal — but confirm it isn't an acquisition smear first (`vol_psxview`,
  `KeNumberProcessors`, duplicate `System` EPROCESS). See [[Gotchas]].
- **Verify by replay.** `verify_finding` re-runs a Finding's cited `tool_call_id` in a fresh
  short-lived MCP child and compares the output SHA-256 byte-for-byte. Determinism is the bar.
- **Surface contradictions before judging.** `detect_contradictions` emits Pool A vs Pool B
  disagreements as first-class records *before* `judge_findings` merges them (Heuer's ACH).
- **Pair network leads with endpoint evidence.** A Zeek/Sysmon connection is a lead, not exfil
  proof; corroborate with process/Prefetch evidence before raising confidence.

## Build patterns (how to code in this repo)

- **TDD loop per plan task:** failing test → RED → implement → GREEN → one commit with the exact
  message the plan specifies. Never batch tasks into one commit.
- **Conventional Commits:** `feat(scope):`, `fix(scope):`, `test(scope):`, `chore(scope):`,
  `docs(scope):`. Existing scopes: `mcp`, `sandbox`, `ci`, `plan`, `report`, `scoring`, `setup`.
- **Never** `--no-verify`, `--no-gpg-sign`, or `git commit --amend` in plan execution. Hook
  failure → fix root cause → new commit.
- **Surgical changes.** Touch only what the task needs; match existing style; remove only the
  imports/variables your change made unused.
- **Pinned versions; code wins over spec.** When code ships a different pin than a spec, the
  shipped pin is authoritative and the spec is the thing to update. See [[Key Decisions]].
- **DFIR vocabulary, not software vocabulary:** Case (not run/job), Observable (not file/blob),
  Finding (not result), Verdict (not conclusion), Confidence (not score). "artifact class" and
  "hit" (YARA/Sigma) are correct DFIR terms — don't rename them.

## Tooling patterns

- **Python:** `uv` for envs/lockfile, `pytest`, `ruff`, Python 3.11.
- **Rust:** `cargo test --workspace --locked`, `cargo clippy --deny warnings`, Rust 1.88
  (`rust-toolchain.toml` authoritative).
- **Node:** `pnpm --frozen-lockfile`, Node 20 for the product/dashboard. The obsidian-mind memory
  layer uses Node 22 side-by-side (nvm) — see [[Skills]].

## Goldens & recall scoring

- A **golden** = the answer key for a case: `goldens/<case-id>/expected-findings.json` listing the
  findings a correct run must surface (`finding_id`, `description`, `mitre_technique`, `confidence`,
  `artifact_class`, `artifact_hint`) plus `verdict` and `min_recall_percent`. Evidence = the exam;
  the agent's run = the answers; the golden = the answer key.
- **A golden needs a real answer key.** Without published ground truth (NIST answer key, scenario
  solution), do NOT author one — a guessed golden makes the score meaningless. Competition cases
  (ROCBA, base-dc) have only *background* briefs → live-run-only, not scoreable. See [[Gotchas]].
- **Scoring:** `scripts/score-recall.py` reads `<case>/verdict.json` + the golden and computes
  recall = (expected findings surfaced) / (total expected). Matching is **maximum bipartite
  matching** (1:1, no run finding satisfies two claims) on description-token **coverage ≥ 0.5**
  (normalized by the expected token set, not Jaccard); MITRE technique is deliberately NOT a match
  shortcut (homogeneous techniques would inflate recall). PASS = recall ≥ `min_recall_percent`
  AND verdict polarity consistent (asymmetric: a NEUTRAL/INDETERMINATE run is never punished, but
  escalating to a definite verdict when the golden expects uncertainty fails — the false-positive
  control). Verified by adversarial drop-tests (removing a finding drops exactly its claim).
- `min_recall_percent` is a deliberate per-case bar, not auto-derived (nitroba 80, NIST 71). Raising
  it demands real new agent capability, not a config tweak.

Related: [[North Star]] · [[Key Decisions]] · [[Gotchas]] · [[Memories]]
