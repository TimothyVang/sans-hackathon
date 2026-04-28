# Surprise Design: Judge Mode + Tamper Replay

**Status:** spec, awaiting user review (auto-selected approach 2026-04-27 per
`Run for 4 hrs` directive — exploration of 11 alternatives in
`docs/design-briefs/surprise-design-exploration.md`).

**Origin:** user request "I need a design, a user workflow and front-end
experience that surprise the judges" (2026-04-27).

**Composes with, doesn't replace:** the Phase 5/6 sprite + chrome work in
`docs/design-briefs/phase-5-6-sprite-design-brief.md`. Judge Mode is a new
route under `/judge` that re-uses the same SSE + audit-chain primitives.

---

## 0. Forensic framing (read first)

This is a **forensic tool** for the SANS Find Evil! 2026 hackathon. Where
the design references cryptographic primitives (audit hash chain, sigstore
attestation, OpenTimestamps anchor), the framing is always
**crypto-forensics** — the discipline of using cryptographic constructs
to establish chain of custody, evidence integrity, and self-authenticating
trust for forensic artifacts. This is the same epistemic territory as
RFC 3161 trusted timestamping, FRE 902(14) self-authenticating electronic
evidence, and the National Institute of Standards' guidance on forensic
audit trails.

**It is not a crypto-trading project, a blockchain explorer, or a
financial primitive.** Bitcoin appears only as the 5th link of the
chain-of-custody attestation chain — used as a write-once distributed
timestamp authority via the OpenTimestamps protocol. The Bitcoin block
height appearing in a verified manifest is forensic metadata, not a
financial reading.

When the spec describes UI for the cryptographic chain (HashChainBadge,
AffidavitCard, OTS receipt, sigstore certificate), the visual language
is **forensic and courtroom-evidentiary** — federal-court stamp seals,
chain-of-custody log aesthetics, expert-witness affidavit treatment.
NOT exchange-dashboard, NOT DeFi, NOT block-explorer aesthetics.

This framing is load-bearing for the Find Evil! pitch. A judge who
reads the dashboard as "crypto-trading" rather than "DFIR with
crypto-forensic chain of custody" is confused at the level of identity,
not aesthetic preference. Iter 2 of the design-iteration loop
(mempool.space) was rejected on exactly this ground — see
`docs/design-briefs/surprise-design-iteration-log.md` Iter 2 entry.

---

## 1. The pitch (90 seconds)

The dashboard at `/` is for analysts watching an investigation run. Judge
Mode at `/judge` is for **the SANS judge themselves**, with three things
the existing dashboard does not do:

1. **A time-travel scrubber over a curated case.** The judge slides through
   the audit chain at 1× / 2× / 8× / instant; sprites animate accordingly;
   each tool call is annotated with the SANS rubric criterion it satisfies
   ("this satisfies criterion #5 — audit-trail traceability").

2. **A "tamper this byte" button.** The judge picks a byte in a sandbox-copy
   of the audit log, flips it, and watches the HashChainBadge flip red and
   `manifest_verify` return its precise diagnostic ("audit chain seq=4
   prev_hash mismatch"). The strongest demonstration of cryptographic
   correctness is the ability to break it on demand.

3. **A stamped court affidavit view.** The verified manifest renders as a
   federal-court-style affidavit with the chain-of-custody primitives:
   sigstore certificate ID, trusted-timestamp anchor (OpenTimestamps
   over Bitcoin — used here as a write-once timestamp authority, NOT
   as a financial primitive — see §0 forensic framing), Merkle root,
   signature digest. Materializes the FRE 902(14) self-authenticating-
   evidence framing into something visually concrete: the kind of
   document an expert witness would attach to a deposition.

The pitch in one line: *judges do not have to take our word for any
cryptographic claim — they can scrub the chain, break it, and read the
affidavit.*

## 2. Why this surprises (rubric-criterion mapping)

| SANS rubric criterion | Where the surprise lands |
|---|---|
| 1. Autonomous Execution Quality | Scrubber annotates each tool failure → planner correction in real time. Self-correction becomes visible behavior, not buried in JSONL. |
| 2. IR Accuracy | Reasoning split shows Pool A / Pool B side-by-side; contradictions surface as red highlights at the moment they emerged. The CONFIRMED / INFERRED / HYPOTHESIS distinction is annotated per Finding. |
| 3. Breadth/Depth | Scrubber timeline shows artifact-class density per beat; >2 artifact classes corroborated → green chain link; <2 → yellow warning. |
| 4. Constraint Implementation | Tamper-replay demonstrates typed-surface enforcement live: judge tries to inject `execute_shell` via a doctored audit line; verifier MCP tool rejects with the exact error code. |
| 5. Audit Trail Quality | The whole route IS criterion 5. Scrubber + tamper + affidavit together make the five-link chain-of-custody attestation (sha256 → audit prev_hash chain → Merkle root → sigstore identity → trusted timestamp anchor) concrete and inspectable. |
| 6. Usability and Documentation | Judge route includes inline links to `agent-config/JUDGING.md` and `docs/cryptographic-attestation.md`; deep-linkable URL `/?case=...&seq=42` so judges can share specific moments. |

## 3. Scope

### 3.1 In scope (this spec)

- New route `/judge` under `apps/web/app/judge/`
- Subroute `/judge/replay` — scrubber-driven curated replay
- Subroute `/judge/tamper` — byte-flip sandbox + re-verify
- Subroute `/judge/affidavit` — stamped affidavit view
- New components under `apps/web/components/judge/`:
  - `Scrubber.tsx`
  - `RubricAnnotation.tsx` — criterion-tagged overlay (the criteria #1-#6 ribbons)
  - `AnnotationPin.tsx` — *agent-emitted* pin on the scrubber (Iter 1 / Replay.io-derived). The agent leaves these as it runs; the judge reads them while scrubbing. Distinct from RubricAnnotation, which is rubric-criterion-tagged.
  - `TamperButton.tsx`
  - `AffidavitCard.tsx`
  - `ReasoningSplit.tsx`

**Agent annotation kinds (Iter 1 / Replay.io-derived):** during a run,
the agent emits annotations as audit-chain records with `kind` in
{`annotation_escalation`, `annotation_verifier_challenge`,
`annotation_judge_merge`, `annotation_correlator_veto`}. The scrubber
renders these as pins anchored to the seq number where they were
emitted, with the markdown body shown in the side-panel on click. The
agent prompts in `agent-config/AGENTS.md` will need a small addition
to emit these during the corresponding decisions; out of scope for
this spec but flagged as a downstream prompt-config change.
- New API route `apps/web/app/api/judge/case/route.ts` — serves the curated case bundle
- New API route `apps/web/app/api/judge/verify/route.ts` — runs `verify_manifest` + `audit_verify` server-side, returns structured result
- One curated case dir at `goldens/judge-case/` containing a real audit.jsonl, run.manifest.json, sigstore cert, ots receipt — captured from a recent SRL-2018 fleet investigation
- Documentation: `docs/judge-mode-walkthrough.md` (3-5 minute read)
- Demo-script update: insert new Beat 5b (or replace existing Beat 5)

### 3.2 Out of scope

- Modifications to existing dashboard at `/` — composes, doesn't change
- Modifications to `services/agent_mcp/` or `services/mcp/` — server-side
  uses existing tools (`manifest_verify`, `audit_verify`) via API route
- Phase 5/6 sprite art — that work continues independently per its brief
- Networked deployment (the judge route runs locally for the demo video
  recording; cloud deployment is out of scope)
- Authentication on `/judge` — the route is read-only against a curated
  case bundle; there is no privileged operation behind a login
- New audit event types — replay drives off the existing JSONL schema

## 4. User workflow

A SANS judge cloning the repo and trying Judge Mode follows this path:

```
$ git clone https://github.com/TimothyVang/sans-hackathon find-evil
$ cd find-evil
$ pnpm install --frozen-lockfile
$ pnpm --filter @findevil/web dev
$ open http://localhost:3000/judge
```

The `/judge` landing page shows three cards:

1. **"Watch a curated investigation"** → `/judge/replay`
2. **"Try to break the cryptographic chain"** → `/judge/tamper`
3. **"Read the affidavit"** → `/judge/affidavit`

Each card has a one-line description of what it demonstrates and which
rubric criteria it lifts.

### 4.1 Replay flow

- Page opens with the scrubber at seq=0 + sprites all idle
- Judge presses Play (or selects 8× speed for 60-second replay)
- As events play, sprites animate per existing `deriveRoleStates` logic
- Each tool call shows a side-panel "rubric tag" (criterion N — short
  explanation) that fades after 4s
- AuditBeadString grows left-to-right; current bead pulses
- **Annotation pins** (Iter 1 / Replay.io-derived): the agent emits
  annotations as it runs (escalation rationale, verifier challenges,
  judge merge decisions, correlator vetoes — see §3.1). The scrubber
  renders them as pinned markers above the timeline; clicking a pin
  pauses playback, opens the side-panel with the annotation's markdown
  body, and highlights the cited audit records.
- Pause anytime; deep-link via the URL grammar
  `?seq=<n>&focus=<from>:<to>&pin=<annotation_id>` so a judge can
  share an exact moment with the surrounding focus window restored
  and the relevant pin pre-opened.

### 4.2 Tamper flow

- Page shows a hex view of the curated audit.jsonl (first 64 lines, scroll
  for more)
- Judge clicks a byte; modal asks "flip 0x{XX} → 0x{YY}?" with a "do it"
  button
- Client copies the audit log into memory, applies the flip, calls
  `/api/judge/verify` with the mutated bytes
- API returns the structured ManifestVerification result
- Page renders the result as the HashChainBadge flipping red + a
  diagnostic banner showing the exact field that failed (e.g.
  `audit_chain_ok: "audit chain seq=4 prev_hash mismatch"`)
- "Reset to original" button restores the page state without round-trip
- Judges who want a more dramatic demo can pick a byte inside the
  `payload.tool_call_id` field — the verifier flags the broken citation
  rather than the chain hash

### 4.3 Affidavit flow

- Page renders a single stamped document with:
  - Title: "Audit Affidavit — Find Evil! Investigation"
  - Case metadata: case_id, image_hash, evidence path
  - Manifest summary: leaf count, Merkle root, signature digest
  - Sigstore certificate: subject, issuer, transparency log URL
  - Trusted-timestamp anchor (OpenTimestamps): block height + block
    time of the Bitcoin block in which the manifest's Merkle root was
    timestamped (used here as a write-once timestamp authority for
    chain-of-custody — *not* as a financial reference; see §0).
    Plus the calendar URL for third-party re-verification.
  - "Verified locally" stamp with timestamp of verification
  - QR code link to opentimestamps.org block + sigstore tlog entry
- Visual treatment: serif type, gold-ink stamp, watermark, signature line
- Print-friendly CSS so judges can save it as PDF

## 5. Architecture

### 5.1 Component contracts

```tsx
interface ScrubberProps {
  events: AuditLine[];
  currentSeq: number;
  speed: 1 | 2 | 8 | "instant";
  focus?: { from: number; to: number };  // optional zoom window
  pinnedAnnotationId?: string;           // pre-open this pin if URL-deep-linked
  onSeqChange: (seq: number) => void;
  onPlayPauseToggle: () => void;
  onFocusChange?: (focus: { from: number; to: number } | undefined) => void;
  onPinClick?: (annotationId: string) => void;
}

// Iter 1 / Replay.io-derived. Distinct from RubricAnnotationProps —
// rubric annotations are criterion-tagged ribbons; agent annotations
// are pins the agent dropped during the run.
interface AnnotationPin {
  id: string;            // stable across reloads; e.g. annotation_<seq>_<hash[:8]>
  seq: number;           // anchored at this audit-chain seq
  kind:
    | "annotation_escalation"
    | "annotation_verifier_challenge"
    | "annotation_judge_merge"
    | "annotation_correlator_veto";
  body: string;          // markdown
  citedSeqs: number[];   // seq numbers of audit records the pin references
}

interface AnnotationPinProps {
  pin: AnnotationPin;
  isOpen: boolean;
  onToggle: (id: string) => void;
}

interface RubricAnnotationProps {
  event: AuditLine;
  criterion: 1 | 2 | 3 | 4 | 5 | 6;
  fadeOutMs?: number;  // default 4000
}

interface TamperButtonProps {
  originalBytes: Uint8Array;
  byteOffset: number;
  newValue: number;  // 0..255
  onResult: (verification: ManifestVerification) => void;
}

interface AffidavitCardProps {
  manifest: RunManifest;
  sigstoreCert: SigstoreCertificate | null;
  otsReceipt: OtsReceipt | null;
}

interface ReasoningSplitProps {
  poolAEvents: AuditLine[];
  poolBEvents: AuditLine[];
  contradictions: ContradictionRecord[];
}
```

All component props use existing types from `apps/web/lib/events.ts`
(generated from Pydantic) plus three new types (`SigstoreCertificate`,
`OtsReceipt`, `ContradictionRecord`) co-located in `apps/web/lib/judge.ts`.

### 5.2 API routes

`/api/judge/case` (GET):
- Returns a JSON bundle: `{ events: AuditLine[], manifest: RunManifest,
  sigstore: SigstoreCertificate | null, ots: OtsReceipt | null }`
- Reads from `goldens/judge-case/` (path is hard-coded — this route is
  intentionally not parameterized; it always serves the curated case)
- 5-second cache so repeated page loads don't re-read disk

`/api/judge/verify` (POST):
- Body: `{ bytes: base64-encoded mutated audit.jsonl, manifestPath: string }`
- Server-side: writes bytes to a tempfile, invokes `verify_manifest` from
  `findevil_agent.crypto.manifest`, returns `ManifestVerification`
- Tempfile cleaned up after each request
- 1MB body cap — no abuse vector since this is a local-dev tool

### 5.3 Data flow

```
goldens/judge-case/                  apps/web/                                Browser
    audit.jsonl ─┐                                                                 │
    manifest.json├──> /api/judge/case ──> { events, manifest, ... } ──> /judge/replay
    sigstore.crt ┘                                                       /judge/tamper
    manifest.ots                                                         /judge/affidavit

      Tamper:                          /api/judge/verify
                                       calls verify_manifest
        mutated bytes ──────────────> ──────────────────────> ManifestVerification ─> HashChainBadge
```

### 5.4 Curated case dir

`goldens/judge-case/` contents:
- `audit.jsonl` (~50-200 events, captured from a real SRL-2018 host)
- `run.manifest.json` (signed)
- `sigstore.crt` (Fulcio cert)
- `manifest.ots` (OpenTimestamps receipt; matures into a Bitcoin-anchored
  trusted timestamp within ~1 hour of stamping — chain-of-custody
  primitive, not a financial artifact)
- `case_meta.json` (display-friendly summary: hostname, evidence type,
  timeline summary)
- `README.md` (provenance: which fleet run, which host, why this case is
  the curated one)

Provenance script: `scripts/curate-judge-case.sh` — picks the most recent
SRL-2018 SUSPICIOUS verdict from `tmp/fleet-runs/`, copies the artifacts
into `goldens/judge-case/`, regenerates `case_meta.json`. Re-runnable.

## 6. Error handling

- **Missing curated case dir:** `/api/judge/case` returns 503 with the
  error `"no judge case configured; run scripts/curate-judge-case.sh"`.
  All three judge sub-pages render an error card with the same message
  and a one-line fix.
- **Sigstore cert missing:** AffidavitCard renders a "verified by local
  Merkle root only" notice instead of the sigstore subject line. Affidavit
  remains valid; just narrower in attestation scope.
- **OTS receipt missing OR not yet matured:** AffidavitCard renders
  "trusted-timestamp anchor pending — receipt was stamped at <ts>;
  matures within ~1 hour into a Bitcoin-anchored timestamp" with
  a refresh button.
- **Tamper-mode body > 1MB:** `/api/judge/verify` rejects with 413; client
  shows "audit log too large for in-browser tamper mode; use scripts/agent-mcp-smoke.py
  instead".
- **Tamper-mode malformed bytes:** `verify_manifest` returns the structured
  failure; the page renders it without modification (failure IS the demo).

## 7. Testing

### 7.1 Unit (Vitest)
- One test file per component under `apps/web/__tests__/judge/`:
  - `scrubber.test.tsx` — seq stepping, play/pause, deep-link
  - `rubric-annotation.test.tsx` — criterion-rendering + fade timing
  - `tamper-button.test.tsx` — byte-flip math + result wiring
  - `affidavit-card.test.tsx` — sigstore present / absent / OTS pending paths
  - `reasoning-split.test.tsx` — pool routing + contradiction highlighting

### 7.2 API route tests (Vitest)
- `__tests__/api/judge-case.test.ts` — bundle shape, missing-dir handling
- `__tests__/api/judge-verify.test.ts` — happy path + tampered-byte path +
  size-cap rejection. Re-uses the existing `verify_manifest` smoke harness
  pattern.

### 7.3 E2E (Playwright)
- `__tests__/e2e/judge-replay.spec.ts` — load `/judge/replay`, press play
  at 8× speed, assert all 5 sprites animate, assert at least 3 rubric
  annotations appear, assert AuditBeadString grows
- `__tests__/e2e/judge-tamper.spec.ts` — load `/judge/tamper`, click byte
  at known offset, assert HashChainBadge flips red within 500ms of click,
  assert diagnostic banner shows the expected error
- `__tests__/e2e/judge-affidavit.spec.ts` — load `/judge/affidavit`,
  assert sigstore subject visible, assert OTS block height visible, assert
  print stylesheet applied via `@media print` query

### 7.4 CI integration
- New L1 smoke `scripts/judge-mode-smoke.py` exercises `/api/judge/case` +
  `/api/judge/verify` headlessly (Next.js dev server in subprocess).
  ~30s wall clock. Wired into `docker/l1-compose.yml` and
  `scripts/run-all-smokes.sh` as the 10th entry.
- All 8 existing Vitest tests continue to pass — no regression.

## 8. Demo video integration

Insert as **Beat 5b** (between current Beat 5 "Crypto chain-of-custody"
and Beat 6 "Fleet investigation"). Time budget: 30 seconds.

```
On-screen: cut from terminal to browser at http://localhost:3000/judge.
Card 1 click → /judge/tamper. Hex view appears. Click byte at offset 0x1A2.
Modal: "flip 0x6B → 0x00?" → "do it". HashChainBadge flips red. Diagnostic:
"audit chain seq=4 prev_hash mismatch". Pause 1s. Click "Reset". Badge
flips green. Cut back to terminal for Beat 6.

Voice-over (~75 words at 150 wpm = 30s):
"The judges have a route built for them. They can break the chain on
demand — flip one byte, the verifier names the exact link that fails,
and the cryptographic claim is no longer something they have to trust.
The audit trail is FRE 902(14) self-authenticating, but more
importantly: it is publicly falsifiable, and we ship the falsifier."
```

This beat is the strongest argument for criterion #5 (Audit Trail Quality)
in a 30-second window — it converts an abstract claim into a tactile demo.

## 9. Acceptance criteria

- [ ] `/judge` route loads in <2s on first hit (cold next.js)
- [ ] `/judge/replay` 60-second replay completes successfully against the
      curated case at 8× speed
- [ ] `/judge/tamper` byte flip → HashChainBadge red within 500ms
- [ ] `/judge/tamper` reset → HashChainBadge green within 200ms
- [ ] `/judge/affidavit` renders in print stylesheet without layout breakage
      (manual visual check; not CI-locked)
- [ ] All Vitest tests green (8 existing + ~10 new = 18+)
- [ ] All Playwright tests green (3 new judge specs)
- [ ] L1 CI passes including the new judge-mode-smoke
- [ ] No regression in existing `/` dashboard
- [ ] `docs/judge-mode-walkthrough.md` reads in 3-5 minutes and walks a
      judge through all three sub-routes
- [ ] Demo Beat 5b script written into `docs/demo-script-a2.md` (and the
      timing table updated to keep 5:00 hard cap)
- [ ] `goldens/judge-case/` populated by `scripts/curate-judge-case.sh`
      using a real SRL-2018 fleet run
- [ ] No new top-level deps in `apps/web/package.json`

## 10. Rollback path

Each of the three sub-routes is independently revertable:

1. **Tamper flow rollback:** delete `/judge/tamper/`, `TamperButton.tsx`,
   `/api/judge/verify/route.ts`. ~10 minutes. The replay flow keeps working.
2. **Affidavit flow rollback:** delete `/judge/affidavit/` and
   `AffidavitCard.tsx`. ~5 minutes. Replay + tamper still work.
3. **Replay flow rollback:** delete `/judge/replay/`, `Scrubber.tsx`,
   `RubricAnnotation.tsx`. ~10 minutes. Tamper + affidavit still work
   (they're scrubber-independent).

Full Judge Mode rollback: delete `apps/web/app/judge/`,
`apps/web/components/judge/`, `apps/web/lib/judge.ts`,
`/api/judge/{case,verify}/route.ts`, `goldens/judge-case/`,
`scripts/curate-judge-case.sh`, `docs/judge-mode-walkthrough.md`. ~30
minutes. Existing dashboard at `/` and the Phase 5/6 sprites are untouched.

## 11. Decision log

**2026-04-27, autonomous-mode selection during user-stepped-away window:**

- **Approach selection:** chose A (Judge Mode + Tamper Replay) from
  3-candidate set in `surprise-design-exploration.md`. Rationale:
  highest combined score on (1) targets actual viewer, (2) lifts
  criterion #5 hardest, (3) composes on existing Phase 5/6 work.
- **Curated-case-only:** Judge Mode does not parameterize over arbitrary
  case dirs — it serves one curated case. This avoids attack surface
  (arbitrary-path file read) and demo brittleness (mid-take case-dir
  selection).
- **Server-side `verify_manifest`:** the tamper flow calls Python via an
  API route rather than reimplementing in TypeScript. Keeps the verifier
  logic single-source-of-truth; one fewer place to drift.
- **No auth on `/judge`:** intentional. The route is read-only against a
  read-only golden case dir, and the tamper sandbox writes only to a
  per-request tempfile. Nothing privileged behind a login.
- **`/judge` deliberately separate from `/`:** the existing `/` is for
  analysts watching live runs; mixing audiences into one route would
  dilute both.

## 12. Open questions for user review

- Q1: Is "Judge Mode" the right name? Alternatives: "Audit Theatre",
  "Court View", "Trust the Trust". Naming hits the README hero claim
  ("self-authenticating"); worth getting right.
- Q2: Should Beat 5b ADD to the demo (re-balancing other beats) or
  REPLACE Beat 5? Adding gives the surprise its own moment; replacing
  keeps the 5:00 cap clean without re-balancing.
- Q3: Do we ship `goldens/judge-case/` in-repo (large-ish, ~200KB-2MB),
  or fetch on-demand from a release artifact? In-repo is simpler;
  release-artifact keeps the repo lean.
- Q4: Scope-creep risk: should we also ship the "Reasoning Split" panel
  (idea #2 from the exploration brief) as part of the same route, or
  defer to a follow-on spec? Adding it is +50% effort; deferring keeps
  this spec single-deliverable.
- Q5: Should we integrate the `/judge` route into the existing demo
  walkthrough's deep-link convention (`?case=...`), or keep `/judge`
  fixed at the curated case?
