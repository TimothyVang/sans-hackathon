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
| 1 | Replay.io scrubber | https://www.replay.io/ | pending | — | — |
| 2 | mempool.space block status | https://mempool.space | pending | — | — |
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
