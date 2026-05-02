# `@findevil/web` — Find Evil! NES.css live dashboard

**Status:** Scaffold (Phase 4 Task 4.1). Subsequent PRs add the audit-log tail (4.2), the audit event-type codegen (4.3), the five pixel-art sprites for Pool A / Pool B / verifier / judge / correlator (Phase 5), and the AuditBeadString + HashChainBadge + FindingChip chrome (Phase 6).

**Spec:** `docs/specs/2026-04-26-amendment-a3-agent-army-and-dashboard.md` §2.2 (apps/web/).
**Plan:** `docs/plans/2026-04-26-amendment-a3-plan.md` Phase 4.

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

## Path allow-list for `/api/audit`

The SSE tail at `GET /api/audit?case=<dir>` (`app/api/audit/route.ts`) validates `<dir>` against an allow-list in `lib/audit-tail.ts` (`isAllowedCasePath`) before opening any file handle. A path outside the allow-list returns `400` with a JSON body `{ error: "case path not in allow-list", reason: "..." }` and is never read.

Default allow-listed roots (resolved against `process.cwd()`, which for the dashboard is the repo root):

- `goldens/` — committed L3 test fixtures
- `tmp/auto-runs/` — `find-evil-auto` headless output
- `tmp/smoke/` — synthetic smoke output
- `test-forensics/` — operator's local DFIR corpus (gitignored)

To add roots without code changes, set the `FINDEVIL_DASHBOARD_EXTRA_ROOTS` env var. It uses the platform path delimiter (`:` on POSIX, `;` on Windows — i.e. `path.delimiter`):

```bash
# POSIX
FINDEVIL_DASHBOARD_EXTRA_ROOTS="/srv/evidence:/mnt/dfir-share" pnpm --filter @findevil/web dev

# Windows
set FINDEVIL_DASHBOARD_EXTRA_ROOTS=D:\evidence;E:\dfir-share
pnpm --filter @findevil/web dev
```

The allow-list closes the path-traversal hole flagged in PR #7's `route.ts` comment — a malicious browser tab pointed at the dashboard URL can no longer trick the route into reading arbitrary filesystem paths.
