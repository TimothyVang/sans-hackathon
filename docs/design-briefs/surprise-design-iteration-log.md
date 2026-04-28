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
| 3 | Sigstore Rekor search | https://search.sigstore.dev/ | pending | — | — |
| 4 | ProofSnap verification | https://getproofsnap.com/verify/index.html | pending | — | — |
| 5 | Wikipedia diff visualization | https://en.wikipedia.org/wiki/Help:Diff | pending | — | — |
| 6 | Velociraptor timeline | https://docs.velociraptor.app/blog/2024/2024-09-12-timelines/ | pending | — | — |
| 7 | The Pudding scrollytelling | https://pudding.cool | pending | — | — |
| 8 | NES.css legitimate examples | https://nostalgic-css.github.io/NES.css/ | pending | — | — |

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
