# Surprise-design iteration loop — summary

**Loop ran:** 2026-04-27, autonomous in-session execution per the
plan at `~/.claude/plans/i-want-you-to-polymorphic-fox.md`.
**Bootstrap commit:** `d835161`. **Final commit:** see `git log`.
**Smoke status:** 13/13 throughout — no smoke failures across the
8 iteration commits.

## Reference benchmark sequence (final)

| Iter | Reference | Status | Headline outcome | Commit |
|---|---|---|---|---|
| 1 | Replay.io scrubber | landed | Annotations promoted to first-class scrubber primitives. New `AnnotationPin.tsx` distinct from rubric ribbons. URL deep-link grammar expanded. | `f37c6c2` |
| 2 | mempool.space | **REJECTED** | User redirect: "focus on forensics; if crypto-forensics is involved, label it." mempool reads as crypto-trading; useful patterns re-derived from forensic references later. Spec edits reverted; explicit §0 forensic framing added. | `ba377fe` |
| 3 | Velociraptor + Timesketch | landed | **The load-bearing iteration.** Forensic-notebook model: NotebookView replaces video-player mental model; SourcePillFilter for role-based filtering; TimeGapMarker for visible pauses; inline annotation icons + tag chips. Dual-aesthetic split between `/` (NES.css playful) and `/judge` (forensic-tool) codified in §0.1. | `aa7a0ac` |
| 4 | Timesketch (split) | **MERGED INTO ITER 3** | Bookkeeping; Timesketch belonged with Velociraptor. | — |
| 5 | Autopsy Timeline | landed | DFIR-canonical patterns: clustering of similar events, FilterSidebar (with default-on "Hide low-value events"), SummaryModeToggle (stacked-bar histogram + detail). Sharpens iter-3's NotebookView. | `3bc7fd6` |
| 6 | ProofSnap evidence verification | landed | Affidavit page rebuilt as a 5-card grid (one per chain link) + standards-compliance row (FRE 902(14) + ISO 27037 + NIST SP 800-86) + 4-step "verify yourself" guide + inline FAQ. Court-admissible structure. | `(iter-6 commit)` |
| 7 | Wikipedia diff visualization | landed | Side-by-side diff for the tamper flow: line-number anchors, character-level highlighting, three-mode toggle, plus a PropagationCascade visualization showing hash-chain breakage radiating across downstream fields. Resurrects the "Expected vs Actual" idea (rejected in iter-2) in a forensics-defensible form. | `(iter-7 commit)` |
| 8 | NES.css legitimate examples | landed | Confirms iter-3's aesthetic split. Pins the specific NES.css component vocabulary the Phase 5/6 brief should use; cross-references that NES.css is for `/` only. | `(iter-8 commit)` |
| ~ | Sigstore Rekor search | DROPPED | Same crypto-coding risk as mempool. | — |
| ~ | The Pudding scrollytelling | DROPPED | iter-1's annotation flow already covers narrative. | — |

## What landed (consolidated)

**New `/judge` route components specced** (in addition to the original
6 from `cd4695b`):

| Component | Source iteration | Purpose |
|---|---|---|
| `AnnotationPin.tsx` | iter-1 | Agent-emitted pins (escalation rationale, verifier challenges, judge merges, correlator vetoes) anchored to seq numbers |
| `NotebookView.tsx` | iter-3 | Forensic notebook body — interleaved tool-call rows + inline annotation icons + tag chips |
| `SourcePillFilter.tsx` | iter-3 | Role-based filter pills (Pool A / Pool B / Verifier / Judge / Correlator) |
| `TimeGapMarker.tsx` | iter-3 | Inter-event gap dividers ("23 minutes", "2 days") for visible pauses |
| `FilterSidebar.tsx` | iter-5 | Multi-select forensic filters (hide bookkeeping, hide HYPOTHESIS, by pool, by MITRE, by tool name) with default-on "Hide low-value events" |
| `SummaryModeToggle.tsx` | iter-5 | Stacked-bar histogram (Summary) ↔ per-row notebook (Detail) |
| `StandardsComplianceRow.tsx` | iter-6 | FRE 902(14) + ISO/IEC 27037 + NIST SP 800-86 cards |
| `VerificationStepsList.tsx` | iter-6 | "How to verify this yourself" 4-step guide |
| `AffidavitFAQ.tsx` | iter-6 | Inline FAQ with 5 anticipated judge questions |
| `DiffPanel.tsx` | iter-7 | Wikipedia-style side-by-side diff (Side-by-side / Unified / Field-only modes) |
| `PropagationCascade.tsx` | iter-7 | Hash-chain breakage cascade visualization |

Plus rewrites to `AffidavitCard.tsx` (now a 5-card grid) and
`Scrubber.tsx` (focus + pinnedAnnotationId props).

**Spec sections added/rewritten:**
- §0 forensic framing (load-bearing identity stance)
- §0.1 dual-aesthetic split between `/` and `/judge`
- §3.2 deferred-to-v2 entries (multi-select bulk ops, event histogram, cross-case search)
- §4.1 replay flow extended with Summary mode default + filter sidebar
- §4.2 tamper flow extended with DiffPanel + PropagationCascade
- §4.3 affidavit flow rewritten as 5 structural sections (hero, grid, standards, steps, FAQ)
- §5.1 component contract block with AnnotationPin + AnnotationPinProps types

**Phase 5/6 sprite brief sharpened:**
- §2.2 NES.css component vocabulary pinned (canonical showcase URL cited)
- §2.2 cross-reference confirming NES.css scope is `/` only

## Crypto-forensics framing (recurring lesson)

Per the user redirect at iter-2: the project IS forensic; cryptographic
primitives appear ONLY as crypto-FORENSICS (chain of custody, RFC 3161
trusted timestamping, FRE 902(14) self-authenticating evidence). All
references to Bitcoin, OpenTimestamps, sigstore now carry explicit
forensic-purpose framing — they're not financial primitives. The §0
header in the spec makes this stance non-negotiable; future contributors
who try to re-borrow crypto-trading aesthetics should be redirected.

## Audit trail

Every iteration produced (1) committed reference + ours screenshot
pairs under the per-iteration directory (e.g.
`docs/design-briefs/screenshots/iter-1/`), (2) a
structured critique entry in `surprise-design-iteration-log.md`, (3)
one or more concrete spec or brief edits, (4) a small commit. A
future reader can `git log --oneline d835161..HEAD` and read the
iteration arc as a story; for any specific iteration, the screenshot
pair + log entry + spec diff are reachable from the commit.

## Resume-ability

If you (the user) want to extend the loop with additional references,
the plan at `~/.claude/plans/i-want-you-to-polymorphic-fox.md` and
this summary are the entry points. Suggested next references if a
v2 loop runs:

- **Cellebrite UFED Reader / Magnet AXIOM Process** — commercial
  DFIR-tool case-history panels for ideas on how analysts navigate
  long investigations.
- **PACER (federal court e-filing)** — for the affidavit page's
  legal-document treatment, beyond ProofSnap's verification UI.
- **Bellingcat investigations** — open-source-investigation
  storytelling format, useful if Judge Mode wants a narrative
  walking-tour overlay.
- **GitHub Pull Request file diff** — alternative diff treatment
  for iter-7's tamper flow if the Wikipedia treatment proves too
  noisy.

## Stop reason

8 iterations completed (target was 8). Iter 4 merged into iter 3 as
duplicate; sigstore Rekor + The Pudding dropped. Final iteration
(iter-8) was a confirmation pass rather than new direction —
natural stopping point. No smoke failures, no contradictions
between iterations, spec converged on a coherent forensic +
legally-defensible design.

## Verification

To re-run the smoke suite that gated each iteration:

```bash
cd /path/to/SANS-Hackathon
SKIP_SLOW_RUST=1 bash scripts/run-all-smokes.sh
```

To inspect the iteration arc:

```bash
git log --oneline d835161..HEAD
```

To see any iteration's reference + ours pair:

```bash
ls docs/design-briefs/screenshots/iter-1/    # or iter-2, iter-3, etc.
```
