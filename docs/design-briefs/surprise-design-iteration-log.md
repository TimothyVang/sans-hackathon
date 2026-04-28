# Surprise-design iteration log

Running journal of an autonomous design-iteration loop for the Judge Mode +
Tamper Replay surprise-design. Each iteration screenshots a real
best-in-class reference and `apps/web/` (rendering against
`tmp/auto-runs/auto-b3d9f260-5ec4-4f12-918d-42c0473d2b69` — 15 audit lines,
SRL-2018 dataset, public + safe to capture), compares them, and lands one
or more concrete improvements to the spec or brief.

**Plan:** `C:/Users/newbi/.claude/plans/i-want-you-to-polymorphic-fox.md`
**Initial spec under iteration:** `docs/superpowers/specs/2026-04-27-surprise-design-judge-mode.md`
(commit `cd4695b`).
**Loop bootstrap commit:** populated below once landed.

## Reference benchmark sequence (filled in over time)

| Iter | Reference | URL | Status | Headline finding | Commit |
|---|---|---|---|---|---|
| 1 | Replay.io scrubber | https://www.replay.io/ | landed | Annotations are first-class citizens, not viewer affordances. Re-design Scrubber.tsx as **annotation-first**. | (this commit) |
| 2 | mempool.space block status | https://mempool.space | **REJECTED** | User redirect: "focus on forensics; if crypto-forensics is involved, label it." mempool.space reads as crypto-trading, not DFIR. Spec/brief edits reverted; Bitcoin-framing language rewritten as crypto-FORENSICS. | (redirect commit) |
| 3 | Velociraptor + Timesketch (squarely DFIR) | https://docs.velociraptor.app + https://timesketch.org/ | landed | Multi-source pills + color-coded datetime + per-event annotation icons + tag chips. Maps directly to Judge Mode replay as a forensic notebook, not a video player. | (this commit) |
| 4 | ~~Timesketch (split)~~ | ~~https://timesketch.org/~~ | **MERGED INTO ITER 3** | Timesketch was the natural co-reference with Velociraptor in iter-3; both DFIR timeline tools, complementary patterns. Splitting them was bookkeeping — they belong in the same comparison. |
| 5 | Autopsy Timeline (new — replaces dropped Sigstore Rekor) | https://sleuthkit.org/autopsy/timeline.php | landed | Two display modes (summary stacked-histogram + detail) + clustering of similar events + filter sidebar (Hide Known Files etc.). | (this commit) |
| 6 | ProofSnap evidence verification (was iter-4) | https://getproofsnap.com/verify/index.html | landed | "What Gets Verified" 4-card grid + step-by-step verification flow + FRE 902 / eIDAS / ISO 27037 standards-compliance footer cards. Affidavit page restructure. | (this commit) |
| 7 | Wikipedia diff visualization (was iter-5) | https://en.wikipedia.org/wiki/Help:Diff | pending | — | — |
| 8 | NES.css legitimate examples (was iter-8) | https://nostalgic-css.github.io/NES.css/ | pending | — | — |
| ~ | ~~Sigstore Rekor search~~ | ~~https://search.sigstore.dev/~~ | **DROPPED** | Same crypto-coding risk as mempool.space (transparency log for software-supply-chain attestation reads as "supply-chain dev tool" not "DFIR forensics"). Pattern of "minimalist log-entry detail view" can be re-derived from forensic tools (Autopsy event detail) instead. |
| ~ | ~~The Pudding scrollytelling~~ | ~~https://pudding.cool~~ | **DROPPED** | Narrative-pattern reference no longer needed — Iter 1 (Replay.io annotations) already covers the storytelling gap; spec §4.1 has scrollable narrative via annotation pins. |

## Per-iteration entries

Iterations append below this line as they complete. Each entry has the four
required sections (what ours does well, what ours does poorly vs reference,
1-3 specific improvements, decision applied).

---

### Iter 1 — Replay.io scrubber

**References captured:**
- `screenshots/iter-1/ref/replayio-home.png` — marketing hero (typography + accent palette)
- `screenshots/iter-1/ref/replayio-devtools-overview.png` — DevTools feature menu
- `screenshots/iter-1/ref/replayio-timeline.png` — "Annotate the timeline" docs page (the central concept)
- `screenshots/iter-1/ref/replayio-devtools.png` — 404 page (navigation miss; logged for honesty)

**Ours captured:**
- `screenshots/iter-1/ours/dashboard.png` — current dashboard at `/`
  rendering placeholder NES.css sprites in idle state. SSE connection
  errored ("EventSource error … check the case path") — a real bug
  for analysts but unrelated to the Iter 1 question. The dashboard is
  not a replay surface yet; this is the "before" baseline.

**What ours does well:**
- Clean role separation (5 sprites map 1:1 to AGENTS.md roles).
- The bead string + dashboard idea is conceptually right — there IS a
  timeline implicit in the audit chain. We just haven't surfaced it yet
  with a scrubber.
- NES.css "with-title is-rounded" containers do read as deliberate, not
  default-Tailwind.

**What ours does poorly vs reference:**
1. **No annotations layer.** Replay.io's load-bearing insight is that
   the timeline becomes a *journal*: you drop pins at specific moments
   that anchor markdown notes, code-line links, console-message links,
   network-request links. The user moves from "watching playback" to
   "navigating evidence." Our Judge Mode spec §5.1 specifies a scrubber
   that *plays back* the audit chain, but doesn't treat tool_call_ids,
   finding_ids, contradictions, or judge_selfscore records as anchorable
   pins. We treat the audit chain as a tape; Replay treats theirs as
   an annotated roadmap.
2. **No deep-linking convention.** Replay highlights "Share URLs" — a
   replay link encodes the pause point, focus window, and active
   annotations. Our spec §4.1 mentions `?seq=N` for deep-linking but
   not the broader URL grammar (annotation IDs, focus windows, multi-
   annotation thread linking).
3. **No collaborative read.** Replay's "@-mention team members" and
   "Comment embeds" turn the replay into a discussion surface. For
   Judge Mode, the judge is alone — but the spec misses a chance: the
   *agent* could leave annotations as it runs (e.g. "I escalated this
   pslist=0 to INFERRED because psscan>0; verifier confirmed at seq=12"),
   and the judge later reads them as pre-written reasoning narration.

**Improvements applied to spec:**
1. Promote **AnnotationPin** to a first-class component in §5.1, distinct
   from RubricAnnotation (which is criterion-tagged annotations). The
   agent leaves annotations as it runs; the judge reads them while
   scrubbing.
2. Expand the URL deep-link grammar in §4.1 to include
   `?seq=<n>&focus=<from>:<to>&pin=<annotation_id>` so judges can share
   specific moments with the exact context restored.
3. Add an "Agent annotations" subsection under §3.1 listing the
   annotation kinds the agent emits during a run (escalation rationale,
   verifier challenges, judge merge decisions, correlator vetoes).

**Decision:** Apply all three. Composes cleanly with existing scope —
the agent already emits these as audit-chain records; we just need
explicit pin rendering.

**Commit:** see git log for `docs(design): iter-1 — Replay.io annotations`

---

### Iter 2 — mempool.space block status — **REJECTED**

**References captured (kept on disk for the audit trail):**
- `screenshots/iter-2/ref/mempool-home.png` — main dashboard
- `screenshots/iter-2/ref/mempool-block-detail.png` — Expected vs
  Actual block treemap with delta percentages

**Ours captured:**
- `screenshots/iter-2/ours/dashboard.png` — iter-1 baseline reused
- `screenshots/iter-2/ours/debug.png` — `/debug` route raw-events view

**Why rejected:** user redirect — *"i want to focus it on forensics. if
you are including crypto forensics make it known."*

The mempool.space reference brought genuine UX patterns (per-bead
multi-layer anatomy, expected-vs-actual diff visualization, percentage
health pills, "live → confirmed" animation) but the **source citation
itself was the problem**: a SANS DFIR judge looking at a dashboard
benchmarked against a Bitcoin block explorer reads "this is a crypto
project," not "this is a forensic tool." The patterns can be re-derived
from forensic references (Wikipedia diff view in Iter 5 for the
expected/actual diff; Velociraptor + Timesketch in Iter 6 for the
multi-layer event tile). No spec-level loss from the rejection.

**Lesson encoded in this log for future iterations:** when a reference
brings useful UX patterns but its *domain framing* is misaligned with
the project's identity, the right move is rejection + re-derivation
from a domain-aligned reference, NOT silently borrowing the patterns
under the misaligned reference's name. The patterns we want from
mempool.space all have analogs in DFIR / forensic-courtroom UI.

**Action taken in this commit:**
1. Reverted spec/brief edits via `git checkout HEAD --` on
   `2026-04-27-surprise-design-judge-mode.md` and
   `phase-5-6-sprite-design-brief.md`.
2. Reframed existing "Bitcoin"-coded language in the spec as
   **crypto-forensics**, making the forensic purpose explicit
   wherever the cryptographic chain-of-custody appears (the OTS /
   Bitcoin anchor IS in the project — it's the 5th link of the
   chain-of-custody attestation; the framing now names it as a
   trusted-timestamping primitive for chain-of-custody, not as a
   "Bitcoin block height").
3. Removed the iter-2 row from the active iteration sequence;
   subsequent iterations renumber implicitly (Iter 3 stays Iter 3 —
   the row remains in the table marked REJECTED for the audit
   trail).

**Commit:** `docs(design): iter-2 redirect — drop mempool.space; reframe crypto language as crypto-forensics`

---

### Iter 3 — Velociraptor + Timesketch (squarely DFIR)

**References captured:**
- `screenshots/iter-3/ref/velociraptor-timelines-blog.png` — official
  Rapid7 blog post on Velociraptor timelines, with embedded screenshots
  of the supertimeline merge UI, color-coded time-group lanes, and
  notebook view
- `screenshots/iter-3/ref/velociraptor-notebooks.png` — Velociraptor
  Notebooks docs page with screenshots of the actual product:
  table-style notebook list, VQL+markdown editor, retro-terminal `gui`
  command output
- `screenshots/iter-3/ref/timesketch-home.png` — Timesketch landing
  page with a hero shot of the actual product UI (multi-source pills,
  color-coded datetime column, per-event annotation icons, tag chips,
  message column, time-gap indicator)

**Ours:** same baselines as iter-1/iter-2 (placeholder dashboard +
spartan /debug page).

**What ours does well:**
- Role separation matches Velociraptor's "Hunting" / "Notebooks" /
  "Forensic Analysis" sidebar split (we have role-per-sprite which
  is a stronger version of the same idea — agents over tabs).
- The audit chain IS conceptually a Velociraptor-style notebook
  (interleaved typed events + freeform metadata) — we just haven't
  surfaced it that way visually.

**What ours does poorly vs reference (DFIR-aligned mappings):**

1. **No source pills.** Timesketch shows `DC01_CDrive` + `DESKTOP-SDN1RPT`
   as colored chips at the top of the timeline. Each chip filters the
   merged event stream to its source. Direct map for Judge Mode: the
   five agent roles (Pool A, Pool B, Verifier, Judge, Correlator)
   render as filterable source pills above the audit-chain notebook.
   Click a pill → timeline filters to events emitted by that role.

2. **No per-event annotation icons.** Timesketch's event rows have
   inline ★ (star), 💬 (comment), 🔖 (bookmark) icons. Iter 1 spec'd
   AnnotationPin as a separate component above the timeline; should
   instead render INLINE per-row in a forensic-notebook view, matching
   Timesketch's idiom. The pin/star/bookmark distinction also gives
   us a finer vocabulary: agent's own annotation (★), judge's saved
   bookmark (🔖), conversation thread anchor (💬 — for future cross-
   case use).

3. **No tag chips column.** Timesketch shows multi-tag chips per
   event ("suspicious", "test pg 3", "bad", "master timeline",
   "logon-event"), color-coded. Maps directly to: rubric-criterion
   tags + finding-tier tags + MITRE-technique tags rendered as
   compact pills next to each tool-call row. The RubricAnnotation
   component from spec §5.1 should produce these inline chips
   instead of (or in addition to) the side-panel ribbons.

4. **No time-gap markers.** Timesketch's "25 days" pill between
   distant events makes pauses VISIBLE. Our scrubber should
   render similar markers when audit-chain seq jumps over a
   significant wall-clock gap (the agent paused, was interrupted,
   or the case extended over multiple sessions).

5. **No light theme / forensic aesthetic.** Velociraptor uses light
   backgrounds with monospace tables, practical action toolbars
   (+ for new, ✎ for edit), retro-terminal accents only for the
   `gui` boot output. Timesketch uses dark but with DFIR-coded
   teal-accent palette, not crypto-coded purple. Either is more
   forensic than NES.css's pixel-art primaries. **The dashboard
   `/` keeps NES.css** (per Phase 5/6 brief — that's the analyst
   playful surface). **`/judge` should adopt a forensic-tool
   aesthetic distinct from `/` — light theme, monospace data,
   sidebar nav with collapsible sections, action toolbars over
   tables.** This is the strongest forensics-alignment lever; mempool
   was the wrong reference, but the broader gap (judge route looks
   too much like the dashboard) is real.

6. **No multi-select + bulk operations.** Timesketch's checkboxes
   per row + "Rows per page" + "1-11 of 11" pagination point at
   a missing affordance: the judge should be able to select N events
   and bulk-export, bulk-tag, bulk-share. For Judge Mode v1,
   defer this — but flag in the spec §3.2 (out of scope) so it's
   on a future-roadmap.

7. **No event-distribution histogram.** Timesketch's chart icon
   above the table opens a histogram of events over time. For
   our scrubber, similar pattern: small histogram strip showing
   `kind`-distribution density along the seq axis, helping judges
   spot dense activity periods at a glance.

**Improvements applied (concrete spec edits this iteration):**
1. Spec §0 forensic framing — note that `/judge` adopts a
   **forensic-tool aesthetic** distinct from `/`'s NES.css playful
   surface (light theme, monospace data, sidebar nav, action
   toolbars). Cross-reference Velociraptor + Timesketch as the
   visual references.
2. Spec §3.1 — replace the "scrubber + side panels" mental model
   with a **forensic-notebook** model: timeline + per-row inline
   icons + tag-chip column + source-pills filter + time-gap markers.
   The Scrubber.tsx component is the navigation widget; the body of
   the route is a notebook (NotebookView.tsx, new component).
3. Spec §5.1 — add `NotebookView.tsx` and `SourcePillFilter.tsx` to
   the components list with their prop contracts.
4. Spec §3.2 — explicit "out of scope (deferred to v2)" entries:
   multi-select bulk operations, event histogram strip — both
   Timesketch-borrowed but defer-able.

**Decision:** Apply all four. The forensic-aesthetic split between
`/` and `/judge` is the load-bearing decision — the judge route is
NOT a re-skinned dashboard, it's a forensic notebook the judge
walks through. This dual-aesthetic decision is documented in the
spec for the Phase 5/6 design pass to honor.

**Commit:** `docs(design): iter-3 — Velociraptor + Timesketch as forensic notebook reference`

---

### Iter 5 — Autopsy Timeline (Sleuth Kit Labs)

**References captured:**
- `screenshots/iter-5/ref/autopsy-timeline.png` — official Sleuth Kit
  Labs Autopsy timeline page with embedded screenshots: stacked
  bar-chart aggregate (color-coded by event type, 1997-2013 buckets),
  detailed clustered view (with breadcrumb-style nested grouping
  "img.zip vs.0,0/(vol_vol2)/Documents and Settings (33)"), and a
  left-rail filter sidebar ("Hide-Known Files", "Type Filter", etc.)

**Ours:** dashboard baseline reused.

**What ours does well:**
- Iter 3's NotebookView model is forensic-aligned (compatible with
  Autopsy's detailed view).
- Existing kind palette (per Phase 5/6 brief §2.4) maps to Autopsy's
  stacked-bar event-type colors.

**What ours does poorly vs reference (DFIR-canonical patterns):**

1. **No dual display mode (summary vs detail).** Autopsy explicitly
   ships TWO modes: bar-chart aggregate ("how much occurred when")
   and detailed ("what happened"). Our spec §4.1 only describes the
   detailed walk. Add a **summary mode toggle** to NotebookView: a
   stacked-bar histogram of audit-chain `kind` density over seq-time
   buckets, color-coded by kind. Click a bar to zoom into that
   seq-window in detail mode. Same dual-mode shape forensic
   investigators are already trained on.

2. **No event-clustering for data overload.** Autopsy's load-bearing
   insight: *"all files in the same folder are shown as a single
   event and all URLs from the same domain are shown as a single
   event. If the user wants to see more details about that folder
   or domain, then they can zoom into it."* Direct map: collapse
   successive `tool_call_start` / `tool_call_end` pairs of the
   SAME tool name into a single row "vol_pslist × 7 (3.2s)" with
   an expand chevron. Bookkeeping records (`audit_append`,
   `chain_update`) collapse en masse into a single "+ 14
   bookkeeping events (hidden)" stub.

3. **No filter sidebar.** Autopsy's left-rail filter list ("Hide
   Known Files", "Text Filter", "Type", "File Type", "Web
   Activity") is the DFIR-canonical pattern. Add a **filter
   sidebar** to `/judge` with the equivalents:
     - Hide bookkeeping (audit_append, chain_update,
       manifest_finalize, ots_stamp)
     - Hide HYPOTHESIS-tier findings
     - Filter by pool (Pool A / Pool B / merged)
     - Filter by MITRE technique (T1014, T1055, …)
     - Filter by tool name (vol_pslist, hayabusa_scan, …)
   Multi-select with ctrl/shift; live update of the notebook view.

4. **No "Hide Known Files" equivalent.** This is the most
   forensically-iconic toggle — analysts hide whitelisted noise so
   attacker signal stands out. For the audit chain: a "Hide low-
   value events" master toggle that combines "hide bookkeeping"
   + "hide HYPOTHESIS" + "hide annotation pins" — leaves only
   the CONFIRMED + INFERRED findings + their `tool_call_start`
   anchors. The judge starts in this filtered view; one click
   reveals the full chain.

**Improvements applied (concrete spec edits):**
1. §4.1 — extend the replay flow to describe the **summary
   mode toggle** (stacked-bar histogram view) alongside the
   detailed walk.
2. §3.1 — add `FilterSidebar.tsx` to the components list with
   prop contract for the filter set; `NotebookView.tsx` props
   gain optional `clusterSimilar: boolean` and
   `filterSet: FilterSet` props.
3. §3.1 — add a "Hide low-value events" default filter, named
   explicitly after Autopsy's "Hide Known Files" idiom in a
   comment.

**Decision:** Apply all three. Each is a small, additive
extension to Iter 3's NotebookView; none reorganize the
architecture.

**Commit:** `docs(design): iter-5 — Autopsy clustering + filter sidebar + dual display mode`

---

### Iter 6 — ProofSnap evidence verification

**References captured:**
- `screenshots/iter-6/ref/proofsnap-verify.png` — ProofSnap Trust
  Verifier landing page. Hero: "Verify Digital Evidence Integrity
  Online" with explicit "Court admissible under FRE 901/902 and
  eIDAS Regulation 910/2014" subtitle. Three load-bearing patterns:
  (a) "What Gets Verified" 4-card grid (Digital Signature /
  SHA-256 / Blockchain Timestamp / eIDAS Timestamp), (b) "Chain
  of Custody Verification" 3-card grid (Per-page, Per-step,
  ISO/IEC 27037-2012), (c) "How to Verify" numbered 4-step flow
  (Upload → Cryptographic Checks → Timestamp Verification →
  Results Report).

**Ours:** dashboard baseline reused.

**What ours does well:**
- Existing spec §4.3 affidavit flow already names the right
  artifacts (sigstore cert + trusted-timestamp + Merkle root +
  signature digest) and the right framing (FRE 902(14)).

**What ours does poorly vs reference:**

1. **No "What Gets Verified" card grid.** ProofSnap shows a 4-card
   grid making each verification check inspectable as its own
   visual unit. Our spec §4.3 lists the same artifacts as bullets
   in a stamped document. Direct map: render the affidavit's "what
   was verified" section as a **5-card grid** matching the five
   chain links (sha256 image hash / audit prev_hash chain / Merkle
   root / sigstore identity / trusted-timestamp anchor). Each card
   has icon + title + checkmark/X badge + the actual digest/value
   for the judge to inspect.

2. **No standards-compliance card row.** ProofSnap's "Chain of
   Custody Verification" row cites three specific standards (one
   per card). Our spec mentions FRE 902(14) once. Add a
   **standards-compliance row** to the affidavit footer with three
   cards: FRE 902(14) self-authenticating evidence, ISO/IEC
   27037:2012 digital evidence handling, NIST SP 800-86 forensic
   integration into incident response. Each card cites the standard
   and one-line explains how the manifest satisfies it. Adds
   gravitas without pretending we're a certified forensic vendor.

3. **No step-by-step verification flow.** ProofSnap's "How to
   Verify Digital Evidence Online" walks through 4 numbered steps
   with badges. Map directly: the the affidavit route page renders
   a "How to verify this affidavit yourself" section with 4 steps:
   (1) Download manifest+ots+sigstore-cert from page footer;
   (2) `manifest_verify` via the MCP tool / the recipe in
   `docs/cryptographic-attestation.md`; (3) `ots verify` against
   the OpenTimestamps calendar (Bitcoin chain anchor); (4) compare
   sigstore cert subject against expected identity. Each step
   shows a numbered badge, the exact command to run, and the
   expected output.

4. **No FAQ section.** ProofSnap anticipates judge/regulator
   questions inline. Add a brief FAQ to the affidavit page
   answering: "Is this admissible?" / "Do I need internet to
   verify?" (no, after manifest+ots+cert downloaded) / "What if
   the OTS receipt isn't yet matured?" / "Can I tamper with the
   manifest in this UI to demonstrate?" (yes — link to
   the tamper route). Maybe 4-6 questions; brief, accessible
   answers.

**Improvements applied:**
1. Spec §4.3 — replace the bulleted-list affidavit body with a
   5-card "What Gets Verified" grid + a 3-card "Chain of Custody
   Standards" footer row.
2. Spec §4.3 — add a "How to verify yourself" 4-step section at
   the bottom of the affidavit, pointing at the offline-
   verification recipe in `docs/cryptographic-attestation.md`.
3. Spec §4.3 — add a brief FAQ subsection (4-6 questions) at
   the bottom.
4. §3.1 — split AffidavitCard.tsx into `AffidavitCard.tsx`
   (the 5-card grid) + `StandardsComplianceRow.tsx` +
   `VerificationStepsList.tsx` + `AffidavitFAQ.tsx` so each
   structural section is its own testable component.

**Decision:** Apply all four. ProofSnap's structure is directly
applicable; reusing it sharpens our affidavit from "stamped
document" to "publicly inspectable verification report" — a
stronger fit for a SANS judge skeptical of cryptographic claims.

**Commit:** `docs(design): iter-6 — ProofSnap-aligned affidavit (5-card grid + standards-compliance + step-by-step + FAQ)`
