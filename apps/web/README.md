# `@findevil/web` — Find Evil! NES.css live dashboard

**Status:** Scaffold (Phase 4 Task 4.1). Subsequent PRs add the audit-log tail (4.2), the audit event-type codegen (4.3), the five pixel-art sprites for Pool A / Pool B / verifier / judge / correlator (Phase 5), and the AuditBeadString + HashChainBadge + FindingChip chrome (Phase 6).

**Spec:** `docs/superpowers/specs/2026-04-26-amendment-a3-agent-army-and-dashboard.md` §2.2 (apps/web/).
**Plan:** `docs/superpowers/plans/2026-04-26-amendment-a3-plan.md` Phase 4.

## Run locally

```bash
pnpm install --frozen-lockfile
pnpm --filter @findevil/web dev
# open http://localhost:3000
```

The build:

```bash
pnpm --filter @findevil/web build
```

## Stack

| Layer | Pick | Why |
|---|---|---|
| Framework | Next.js 15 (App Router) | Spec #2 §6 + Amendment A3 |
| UI library | React 19 | Next 15's default |
| CSS | Tailwind v4 (CSS-first config via `@import "tailwindcss"` + `@theme`) | Cleaner than v3's config.js for this scope |
| Component library | nes.css ~2.3 (8-bit / NES-style) | Amendment A3 §1.2 aesthetic |
| TypeScript | 5.7+ strict | Project default |

## Why no `tailwind.config.ts`

Tailwind v4 moves config from JS to CSS — the `@theme` block in `app/globals.css` (added in Phase 5/6) is the equivalent. A `tailwind.config.ts` shim is only needed if you wire in JS plugins or do programmatic theme generation, neither of which we do.

## Why no `tailwind.config.ts` AND why no WebSocket route in this PR

This PR is the scaffold only. The WebSocket / SSE audit-log tail (`app/api/audit/route.ts` + `lib/audit-tail.ts`) lands in Task 4.2 along with an integration test. Same shape: keep PRs small enough to review thoroughly.
