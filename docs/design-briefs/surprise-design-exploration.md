# Surprise-design exploration — DRAFT notes (uncommitted)

**Status:** in-progress brainstorming exploration. Paused 2026-04-27 when the
user shifted to harness mode (`autonomous-loop.py --max-hours 4`). Re-open
this file at the start of the next interactive session to resume the
brainstorming flow per the superpowers:brainstorming skill.

**Original ask:** "I need a design, a user workflow and front-end experience
that surprises the judges."

---

## What judges already expect (the baseline)

The submission's existing pitch lands these as table stakes — these will NOT
surprise:

1. Cryptographic chain-of-custody (FRE 902(14) framing)
2. ACH dual-pool architecture (Pool A vs Pool B)
3. 12 typed Rust MCP tools, no `execute_shell`
4. Judge self-score before manifest finalize
5. Real-evidence run on the 22-host SRL-2018 dataset

The 9-beat demo (`docs/demo-script-a2.md`) is built around watching the agent
army work in the terminal + pre-rendered fleet PDFs. The Phase 5/6 sprite
brief at `docs/design-briefs/phase-5-6-sprite-design-brief.md` adds NES.css
sprites + AuditBeadString + HashChainBadge + FindingChip — these will land
nice but won't deeply surprise either.

## What's NOT yet pitched — the surprise space (12 candidates)

Each tagged with rubric criteria it would lift (1=Autonomy, 2=Accuracy,
3=Breadth, 4=Constraints, 5=Audit, 6=Usability):

1. **Time-travel scrubber.** Timeline slider that scrubs the audit chain.
   Judges pause at any moment; see what tool was running, what each pool
   was thinking, what verifier was about to challenge. Crypto chain becomes
   *interactive evidence*, not a static seal. **Hits: 5, 1.**

2. **Side-by-side ACH dialogue.** Pool A and Pool B as a courtroom
   transcript — left column persistence reasoning, right column exfil
   reasoning, contradictions in red as they appear. Makes Heuer's framework
   visible rather than just claimed. **Hits: 2, 1.**

3. **Audit chain as interactive proof.** Click any Finding → traces back
   through chain to tool call → tool output bytes → image_hash. Five-link
   chain becomes a clickable thread. Currently it's just a green badge.
   **Hits: 5.**

4. **Court-room aesthetic for the cryptographic side.** When manifest
   verifies, render a "stamped" affidavit with sigstore certificate ID +
   Bitcoin block height + timestamp. Makes the FRE 902(14) framing concrete.
   **Hits: 5, 6.**

5. **Adversarial replay — "break it on demand."** Button that lets the
   judge tamper with one byte of the audit log (sandbox copy) and watch
   verification fail in real time. The strongest demonstration of
   correctness is the ability to BREAK it. **Hits: 5, 4.**

6. **Three-mode dashboard.** Investigator mode (sprite dashboard), Auditor
   mode (court-of-law affidavit view), Detective mode (Find Evil!-as-a-game
   where the user picks the next tool call). **Hits: 6, 1.**

7. **Beat-aware UX.** Dashboard knows which beat of the demo it's in and
   adapts emphasis (during ACH disagreement beat, contradiction chips
   pulse, pool sprites face each other). **Hits: 6.**

8. **Compositional sprite states.** Beyond idle/working/waiting/verdict —
   sprites carry "evidence held" markers (small icons of artifact classes
   they've drawn from), debate "speech bubbles" with hypotheses, a
   "credibility meter" derived from confirmed/inferred ratio. **Hits: 2, 3.**

9. **Cryptographic trophy room.** End-of-investigation zoom-out showing
   all the receipts — OTS proof file, sigstore signature, Merkle tree
   visualized as an actual tree. Bitcoin block clickable to
   opentimestamps.org. **Hits: 5.**

10. **Judges' dashboard.** Separate route `/judge` that auto-replays a
    curated investigation in 60 seconds with annotations matching the 6
    SANS criteria — a self-grading walkthrough. **Hits: ALL 6.**

11. **Cross-case memory visualization.** The Hermes-pattern FTS5 store as
    a filing-cabinet sprite that opens when memory_recall fires. "This
    IOC was seen in 3 prior cases." **Hits: 3, 1.**

12. **Live ACP message envelopes.** When `pool_handoff` fires, an envelope
    sprite physically travels between pools showing the IBM-ACP envelope
    format. **Hits: 1, 6.**

## Top-3 candidates by surprise × rubric coverage × buildable-in-50-days

The combinations that punch above their weight:

**A. The "Judge Mode" run** (idea #10 + #5 combined):
- `/judge` route — 60-second curated replay with rubric-criterion annotations
- Includes the live "tamper a byte, watch it fail" demonstration
- Hits all 6 criteria, especially #5 (audit) and #4 (constraints)
- Uniquely targets the actual user (the SANS judge)
- Has a clear demo-video moment (Beat 5 or new beat)
- ~2 weeks to build

**B. The "Time-travel + Court Affidavit"** (ideas #1 + #3 + #4 combined):
- Timeline scrubber on the audit chain
- Each Finding clickable, traces back to tool call → bytes → image_hash
- Successful verification renders a stamped court affidavit
- Hits criteria 5, 1, 2 hard
- Visual story is "the agent's reasoning is forensically navigable"
- ~3 weeks to build

**C. The "ACH Theatre"** (ideas #2 + #8 combined):
- Render Pool A/B reasoning as a courtroom dialogue
- Sprites with speech bubbles, evidence-held markers, credibility meters
- Contradictions surface dramatically as red highlight
- Hits criteria 1, 2 hard; makes Heuer's framework legible
- Visual story is "two analysts arguing, audit chain refereeing"
- ~3 weeks to build

**Recommendation when this resumes:** Pick **A (Judge Mode + Tamper Replay)**
because it directly addresses the actual viewer (the judge), bundles the
strongest crypto-attestation moment (criterion 5), and is the most defensible
"this is the surprise" claim — the judge literally has a route built FOR them.

---

## Open clarifying questions when brainstorming resumes

1. Surprise budget: shippable in 4 weeks (must be done well before video
   recording) or 6+ weeks (closer to deadline)?
2. Whether the surprise should land in the demo video (5-min hard cap) or
   primarily in repo exploration (judge clones the repo and discovers it).
3. Whether to surprise on UX (the dashboard) or on UX-adjacent (a new flow
   the agent supports — e.g., "explain this finding to a non-DFIR judge"
   mode powered by an LLM second pass).
4. Whether "surprise the judges" overrides the existing scaffolded Phase
   5/6 work, or composes on top of it. (Composing is cheaper.)
5. Visual ambition: do we want this to feel like a forensic tool, a
   courtroom artifact, or a game?

---

## How to resume

1. Open this file
2. Re-read `docs/design-briefs/phase-5-6-sprite-design-brief.md` for what's
   already locked
3. Re-invoke superpowers:brainstorming — start at "Ask clarifying
   questions" using the 5 questions above as the starting set
4. Move toward design spec at `docs/superpowers/specs/`
