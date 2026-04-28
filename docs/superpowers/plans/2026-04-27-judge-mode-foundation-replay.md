# Judge Mode Plan A — Foundation + Replay route

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `/judge` route shell + `/judge/replay` sub-route with the forensic-notebook walking tour (NotebookView, Scrubber, SourcePillFilter, AnnotationPin, RubricAnnotation, TimeGapMarker, FilterSidebar, SummaryModeToggle), backed by a curated case dir served via a new API route. Plans B (tamper) and C (affidavit) compose on this foundation.

**Architecture:** Next.js 15 App Router subroute under `apps/web/app/judge/`. Forensic-tool aesthetic (light theme, monospace tables, sidebar nav) per spec §0.1, deliberately distinct from `/`'s NES.css playful surface. Server-side curated case bundle served by `/api/judge/case` reading from `goldens/judge-case/`; client-side Vitest+happy-dom component tests; Playwright E2E for the replay flow.

**Tech Stack:** Next.js 15 (App Router), React 19, Tailwind v4, Vitest (existing), `@testing-library/react` + `happy-dom` (new), Playwright (new test dep — distinct from the Playwright MCP). All TypeScript. No new server-side runtime deps.

**Spec under implementation:** `docs/superpowers/specs/2026-04-27-surprise-design-judge-mode.md` §0–§5.

---

## File structure (locked before tasks)

**Created files:**
- `apps/web/app/judge/layout.tsx` — shared forensic-aesthetic layout
- `apps/web/app/judge/page.tsx` — landing page with 3 sub-route cards
- `apps/web/app/judge/replay/page.tsx` — replay surface
- `apps/web/app/api/judge/case/route.ts` — case-bundle API
- `apps/web/components/judge/Scrubber.tsx`
- `apps/web/components/judge/NotebookView.tsx`
- `apps/web/components/judge/SourcePillFilter.tsx`
- `apps/web/components/judge/RubricAnnotation.tsx`
- `apps/web/components/judge/AnnotationPin.tsx`
- `apps/web/components/judge/TimeGapMarker.tsx`
- `apps/web/components/judge/FilterSidebar.tsx`
- `apps/web/components/judge/SummaryModeToggle.tsx`
- `apps/web/lib/judge.ts` — types + helpers (CaseBundle, FilterSet, AnnotationKind, applyFilters, etc.)
- `apps/web/__tests__/judge/*.test.tsx` — one Vitest file per component (8 files)
- `apps/web/__tests__/api/judge-case.test.ts` — API route test
- `apps/web/e2e/judge-replay.spec.ts` — Playwright E2E
- `apps/web/playwright.config.ts` — Playwright config
- `goldens/judge-case/audit.jsonl` — curated audit trail
- `goldens/judge-case/run.manifest.json` — signed manifest
- `goldens/judge-case/sigstore.crt` — Fulcio cert (or sentinel "not-yet-signed" if real one isn't available at curate time)
- `goldens/judge-case/manifest.ots` — OpenTimestamps receipt
- `goldens/judge-case/case_meta.json` — display-friendly summary
- `goldens/judge-case/README.md` — provenance
- `scripts/curate-judge-case.sh` — populates `goldens/judge-case/` from `tmp/auto-runs/`

**Modified files:**
- `apps/web/package.json` — add `@testing-library/react`, `happy-dom`, `@playwright/test`
- `apps/web/vitest.config.ts` — switch `environment: "node"` → `"happy-dom"` for component tests
- `docker/l1-compose.yml` — extend the apps/web test step
- `apps/web/README.md` — status block update
- `CHANGELOG.md` — entry under [Unreleased]

---

## Task 1: Add component-test infrastructure (Vitest + happy-dom + RTL)

**Files:**
- Modify: `apps/web/package.json` (add devDependencies)
- Modify: `apps/web/vitest.config.ts:9-15` (env switch)
- Create: `apps/web/__tests__/judge/_smoke.test.tsx` (sanity test)

- [ ] **Step 1: Write the failing sanity test**

Create `apps/web/__tests__/judge/_smoke.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("RTL smoke", () => {
  it("renders a div with text", () => {
    render(<div>hello forensics</div>);
    expect(screen.getByText("hello forensics")).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to verify FAIL**

Run: `pnpm --filter @findevil/web test __tests__/judge/_smoke.test.tsx`
Expected: FAIL with module-not-found on `@testing-library/react` (deps missing).

- [ ] **Step 3: Add devDependencies**

```bash
cd apps/web
pnpm add -D @testing-library/react@^16.0.0 @testing-library/jest-dom@^6.5.0 happy-dom@^15.0.0
```

- [ ] **Step 4: Switch Vitest to happy-dom env**

Edit `apps/web/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    environment: "happy-dom",
    globals: true,
    include: ["__tests__/**/*.test.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
});
```

- [ ] **Step 5: Run smoke test, expect PASS**

Run: `pnpm --filter @findevil/web test __tests__/judge/_smoke.test.tsx`
Expected: PASS with 1/1 test.

- [ ] **Step 6: Run full smoke suite to confirm no regression**

Run: `cd ../.. && SKIP_SLOW_RUST=1 bash scripts/run-all-smokes.sh`
Expected: 13/13 pass.

- [ ] **Step 7: Commit**

```bash
git add apps/web/package.json apps/web/pnpm-lock.yaml apps/web/vitest.config.ts apps/web/__tests__/judge/_smoke.test.tsx
git commit -m "test(web): add Vitest+RTL+happy-dom for component testing (Judge Mode foundation)"
```

---

## Task 2: Curate the judge case dir

**Files:**
- Create: `scripts/curate-judge-case.sh`
- Create: `goldens/judge-case/README.md` (placeholder; the script writes case_meta.json, audit.jsonl, etc.)
- Test: by running the script and asserting outputs

- [ ] **Step 1: Write the script**

Create `scripts/curate-judge-case.sh`:

```bash
#!/usr/bin/env bash
# Populate goldens/judge-case/ from the most recent tmp/auto-runs/ case
# dir with a non-empty audit.jsonl.  Re-runnable; overwrites prior
# contents.  Caller MUST commit the resulting goldens/judge-case/
# tree manually after inspecting it.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC_ROOT="$REPO/tmp/auto-runs"
DEST="$REPO/goldens/judge-case"

if [ ! -d "$SRC_ROOT" ]; then
  echo "ERROR: $SRC_ROOT does not exist; no auto-runs to curate from" >&2
  exit 2
fi

# Pick the most recent case dir with the most audit lines (>=10).
best=""
best_lines=0
for d in "$SRC_ROOT"/auto-*/; do
  [ -f "$d/audit.jsonl" ] || continue
  lines=$(wc -l < "$d/audit.jsonl" | tr -d ' ')
  if [ "$lines" -ge 10 ] && [ "$lines" -gt "$best_lines" ]; then
    best="$d"
    best_lines="$lines"
  fi
done

if [ -z "$best" ]; then
  echo "ERROR: no auto-run dir with >=10 audit lines found in $SRC_ROOT" >&2
  exit 3
fi

case_id=$(basename "$best" | sed 's/^auto-//; s|/$||')
echo "[curate-judge-case] source: $best ($best_lines lines)"
echo "[curate-judge-case] dest:   $DEST"

mkdir -p "$DEST"
cp "$best/audit.jsonl" "$DEST/audit.jsonl"
[ -f "$best/run.manifest.json" ] && cp "$best/run.manifest.json" "$DEST/run.manifest.json" || echo '{"placeholder":true}' > "$DEST/run.manifest.json"
[ -f "$best/manifest.ots" ] && cp "$best/manifest.ots" "$DEST/manifest.ots" || : > "$DEST/manifest.ots"
[ -f "$best/sigstore.crt" ] && cp "$best/sigstore.crt" "$DEST/sigstore.crt" || : > "$DEST/sigstore.crt"

# Build case_meta.json from the audit-chain head + tail.
head_line=$(head -n1 "$DEST/audit.jsonl")
tail_line=$(tail -n1 "$DEST/audit.jsonl")
cat > "$DEST/case_meta.json" <<EOF
{
  "case_id": "$case_id",
  "source_auto_run": "$(basename "$best")",
  "audit_line_count": $best_lines,
  "first_event_ts": $(echo "$head_line" | python -c 'import json,sys; print(json.dumps(json.loads(sys.stdin.read()).get("ts","")))'),
  "last_event_ts": $(echo "$tail_line" | python -c 'import json,sys; print(json.dumps(json.loads(sys.stdin.read()).get("ts","")))'),
  "curated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "curated_by": "scripts/curate-judge-case.sh"
}
EOF

cat > "$DEST/README.md" <<EOF
# goldens/judge-case/ — curated case bundle

Populated by \`scripts/curate-judge-case.sh\` from
\`tmp/auto-runs/$(basename "$best")\` ($best_lines audit lines).

This bundle is served by the Judge Mode \`/api/judge/case\` route and
read by \`/judge/replay\`, \`/judge/tamper\`, and \`/judge/affidavit\`.

Re-curate by running the script again; commit the resulting tree.
EOF

echo "[curate-judge-case] done. Inspect goldens/judge-case/ and commit."
```

- [ ] **Step 2: Make executable + run**

```bash
chmod +x scripts/curate-judge-case.sh
bash scripts/curate-judge-case.sh
```

Expected output: lines like `[curate-judge-case] source: …`, `dest: …`, `done. Inspect…`. The script exits 0.

- [ ] **Step 3: Inspect outputs**

Run:
```bash
ls goldens/judge-case/
wc -l goldens/judge-case/audit.jsonl
cat goldens/judge-case/case_meta.json
```

Expected: 6 files (audit.jsonl, run.manifest.json, manifest.ots, sigstore.crt, case_meta.json, README.md). audit.jsonl has ≥10 lines. case_meta.json parses as valid JSON with case_id, audit_line_count, first/last_event_ts.

- [ ] **Step 4: Commit script + curated bundle**

```bash
git add scripts/curate-judge-case.sh goldens/judge-case/
git commit -m "feat(judge): curate-judge-case.sh + initial goldens/judge-case/ bundle"
```

---

## Task 3: Define types in `apps/web/lib/judge.ts`

**Files:**
- Create: `apps/web/lib/judge.ts`
- Test: `apps/web/__tests__/judge/judge-types.test.ts`

- [ ] **Step 1: Write the failing test**

Create `apps/web/__tests__/judge/judge-types.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  applyFilters,
  ANNOTATION_KINDS,
  defaultFilterSet,
  isAnnotationLine,
  type AuditLine,
  type FilterSet,
} from "@/lib/judge";

describe("judge types", () => {
  it("ANNOTATION_KINDS contains all four", () => {
    expect(ANNOTATION_KINDS).toEqual([
      "annotation_escalation",
      "annotation_verifier_challenge",
      "annotation_judge_merge",
      "annotation_correlator_veto",
    ]);
  });

  it("isAnnotationLine identifies annotation kinds", () => {
    const ann: AuditLine = {
      seq: 1,
      ts: "2026-04-27T00:00:00Z",
      kind: "annotation_escalation",
      payload: { body: "hello", citedSeqs: [] },
      prev_hash: "0",
      line_hash: "1",
    };
    const tool: AuditLine = { ...ann, kind: "tool_call_start" };
    expect(isAnnotationLine(ann)).toBe(true);
    expect(isAnnotationLine(tool)).toBe(false);
  });

  it("defaultFilterSet hides bookkeeping + HYPOTHESIS", () => {
    const fs = defaultFilterSet();
    expect(fs.hideBookkeeping).toBe(true);
    expect(fs.hideHypothesis).toBe(true);
    expect(fs.poolFilter).toBe(null);
  });

  it("applyFilters drops bookkeeping events when hideBookkeeping", () => {
    const lines: AuditLine[] = [
      { seq: 1, ts: "t", kind: "tool_call_start", payload: {}, prev_hash: "0", line_hash: "1" },
      { seq: 2, ts: "t", kind: "audit_append", payload: {}, prev_hash: "1", line_hash: "2" },
    ];
    const fs: FilterSet = { ...defaultFilterSet(), hideHypothesis: false };
    const out = applyFilters(lines, fs);
    expect(out.map((l) => l.seq)).toEqual([1]);
  });
});
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `pnpm --filter @findevil/web test __tests__/judge/judge-types.test.ts`
Expected: FAIL — module `@/lib/judge` not found.

- [ ] **Step 3: Implement `apps/web/lib/judge.ts`**

```ts
// Judge Mode shared types + helpers.  Plan A foundation; consumed by
// the components in apps/web/components/judge/ and the API route at
// apps/web/app/api/judge/case/route.ts.

export interface AuditLine {
  seq: number;
  ts: string;
  kind: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  line_hash: string;
}

export const ANNOTATION_KINDS = [
  "annotation_escalation",
  "annotation_verifier_challenge",
  "annotation_judge_merge",
  "annotation_correlator_veto",
] as const;

export type AnnotationKind = (typeof ANNOTATION_KINDS)[number];

export const BOOKKEEPING_KINDS = [
  "audit_append",
  "chain_update",
  "manifest_finalize",
  "ots_stamp",
] as const;

export type Pool = "A" | "B" | "merged";

export interface FilterSet {
  hideBookkeeping: boolean;
  hideHypothesis: boolean;
  poolFilter: Pool | null;
  toolNameFilter: string | null;
  mitreFilter: string | null;
}

export function defaultFilterSet(): FilterSet {
  return {
    hideBookkeeping: true,
    hideHypothesis: true,
    poolFilter: null,
    toolNameFilter: null,
    mitreFilter: null,
  };
}

export function isAnnotationLine(line: AuditLine): boolean {
  return (ANNOTATION_KINDS as readonly string[]).includes(line.kind);
}

export function isBookkeepingLine(line: AuditLine): boolean {
  return (BOOKKEEPING_KINDS as readonly string[]).includes(line.kind);
}

export function applyFilters(lines: AuditLine[], fs: FilterSet): AuditLine[] {
  return lines.filter((l) => {
    if (fs.hideBookkeeping && isBookkeepingLine(l)) return false;
    if (fs.hideHypothesis && (l.payload as { confidence?: string })?.confidence === "HYPOTHESIS") return false;
    if (fs.poolFilter && (l.payload as { pool?: string; pool_origin?: string })?.pool !== fs.poolFilter && (l.payload as { pool_origin?: string })?.pool_origin !== fs.poolFilter) return false;
    if (fs.toolNameFilter && (l.payload as { tool?: string })?.tool !== fs.toolNameFilter) return false;
    return true;
  });
}

export interface CaseBundle {
  events: AuditLine[];
  manifest: Record<string, unknown> | null;
  sigstoreCert: string | null;
  otsReceiptBase64: string | null;
  caseMeta: {
    case_id: string;
    audit_line_count: number;
    first_event_ts: string;
    last_event_ts: string;
    curated_at: string;
  };
}
```

- [ ] **Step 4: Run test, expect PASS**

Run: `pnpm --filter @findevil/web test __tests__/judge/judge-types.test.ts`
Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/judge.ts apps/web/__tests__/judge/judge-types.test.ts
git commit -m "feat(judge): types + filter helpers in lib/judge.ts"
```

---

## Task 4: `/api/judge/case` route

**Files:**
- Create: `apps/web/app/api/judge/case/route.ts`
- Test: `apps/web/__tests__/api/judge-case.test.ts`

- [ ] **Step 1: Write the failing test**

Create `apps/web/__tests__/api/judge-case.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { GET } from "@/app/api/judge/case/route";

describe("GET /api/judge/case", () => {
  it("returns 200 with bundle when goldens/judge-case exists", async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.events).toBeInstanceOf(Array);
    expect(body.events.length).toBeGreaterThanOrEqual(10);
    expect(body.caseMeta.case_id).toBeTypeOf("string");
  });

  it("each event matches AuditLine shape", async () => {
    const res = await GET();
    const body = await res.json();
    const ev = body.events[0];
    expect(ev).toMatchObject({
      seq: expect.any(Number),
      ts: expect.any(String),
      kind: expect.any(String),
      prev_hash: expect.any(String),
      line_hash: expect.any(String),
    });
  });
});
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `pnpm --filter @findevil/web test __tests__/api/judge-case.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the route**

Create `apps/web/app/api/judge/case/route.ts`:

```ts
import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";
import type { AuditLine, CaseBundle } from "@/lib/judge";

// Hard-coded path: this route always serves the curated case dir.
// No parameterization (security: no arbitrary-path file read).
const CASE_DIR = path.resolve(process.cwd(), "..", "..", "goldens", "judge-case");

async function readJsonl(p: string): Promise<AuditLine[]> {
  const raw = await fs.readFile(p, "utf-8");
  return raw
    .split("\n")
    .filter((l) => l.length > 0)
    .map((l) => JSON.parse(l) as AuditLine);
}

async function readMaybe(p: string): Promise<string | null> {
  try {
    const raw = await fs.readFile(p, "utf-8");
    return raw.trim().length > 0 ? raw : null;
  } catch {
    return null;
  }
}

export async function GET(): Promise<Response> {
  try {
    const events = await readJsonl(path.join(CASE_DIR, "audit.jsonl"));
    const manifestRaw = await readMaybe(path.join(CASE_DIR, "run.manifest.json"));
    const sigstoreCert = await readMaybe(path.join(CASE_DIR, "sigstore.crt"));
    const otsRaw = await fs.readFile(path.join(CASE_DIR, "manifest.ots")).catch(() => null);
    const caseMetaRaw = await readMaybe(path.join(CASE_DIR, "case_meta.json"));

    if (!caseMetaRaw) {
      return NextResponse.json(
        { error: "no judge case configured; run scripts/curate-judge-case.sh" },
        { status: 503 },
      );
    }

    const bundle: CaseBundle = {
      events,
      manifest: manifestRaw ? JSON.parse(manifestRaw) : null,
      sigstoreCert,
      otsReceiptBase64: otsRaw ? otsRaw.toString("base64") : null,
      caseMeta: JSON.parse(caseMetaRaw),
    };
    return NextResponse.json(bundle);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: `judge case bundle read failed: ${msg}` },
      { status: 503 },
    );
  }
}

export const runtime = "nodejs";
```

- [ ] **Step 4: Run test, expect PASS**

Run: `pnpm --filter @findevil/web test __tests__/api/judge-case.test.ts`
Expected: 2/2 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/api/judge/case/route.ts apps/web/__tests__/api/judge-case.test.ts
git commit -m "feat(judge): /api/judge/case route serves curated bundle"
```

---

## Task 5: `/judge` route shell — layout + landing page

**Files:**
- Create: `apps/web/app/judge/layout.tsx`
- Create: `apps/web/app/judge/page.tsx`
- Test: `apps/web/__tests__/judge/landing.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/web/__tests__/judge/landing.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import JudgePage from "@/app/judge/page";

describe("Judge landing page", () => {
  it("renders three sub-route cards", () => {
    render(<JudgePage />);
    expect(screen.getByText(/Watch a curated investigation/i)).toBeDefined();
    expect(screen.getByText(/Try to break the cryptographic chain/i)).toBeDefined();
    expect(screen.getByText(/Read the affidavit/i)).toBeDefined();
  });

  it("each card links to its sub-route", () => {
    render(<JudgePage />);
    const links = screen.getAllByRole("link");
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/judge/replay");
    expect(hrefs).toContain("/judge/tamper");
    expect(hrefs).toContain("/judge/affidavit");
  });
});
```

- [ ] **Step 2: Run test, expect FAIL**

Run: `pnpm --filter @findevil/web test __tests__/judge/landing.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement layout (forensic aesthetic)**

Create `apps/web/app/judge/layout.tsx`:

```tsx
import type { ReactNode } from "react";

// Forensic-tool aesthetic per spec §0.1: light theme + monospace
// data + minimal chrome.  Distinct from / which uses NES.css.
export default function JudgeLayout({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "#fafafa",
        color: "#1a1a1a",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <header
        style={{
          borderBottom: "1px solid #e5e5e5",
          padding: "12px 24px",
          display: "flex",
          alignItems: "center",
          gap: "12px",
        }}
      >
        <strong>Find Evil! — Judge Mode</strong>
        <span style={{ fontSize: 12, color: "#666" }}>
          forensic-evidence walkthrough
        </span>
      </header>
      <main style={{ padding: "24px" }}>{children}</main>
    </div>
  );
}
```

- [ ] **Step 4: Implement landing page**

Create `apps/web/app/judge/page.tsx`:

```tsx
import Link from "next/link";

interface CardProps {
  title: string;
  description: string;
  href: string;
  rubric: string;
}

function Card({ title, description, href, rubric }: CardProps) {
  return (
    <Link
      href={href}
      style={{
        display: "block",
        padding: "20px",
        border: "1px solid #d1d5db",
        borderRadius: "6px",
        backgroundColor: "white",
        textDecoration: "none",
        color: "inherit",
      }}
    >
      <h2 style={{ marginTop: 0, marginBottom: 8 }}>{title}</h2>
      <p style={{ margin: 0, fontSize: 14, color: "#444" }}>{description}</p>
      <p style={{ marginTop: 12, marginBottom: 0, fontSize: 12, color: "#666", fontFamily: "monospace" }}>
        {rubric}
      </p>
    </Link>
  );
}

export default function JudgePage() {
  return (
    <div style={{ maxWidth: 920, margin: "0 auto", display: "grid", gap: "16px" }}>
      <Card
        title="Watch a curated investigation"
        description="Walk the audit chain at controlled speed.  Filter by role; view per-event annotations dropped by the agent during the run."
        href="/judge/replay"
        rubric="rubric criteria 1, 2, 3"
      />
      <Card
        title="Try to break the cryptographic chain"
        description="Flip a byte in a sandbox copy of the audit log; watch the verifier catch it within 500ms with the precise diagnostic."
        href="/judge/tamper"
        rubric="rubric criteria 4, 5"
      />
      <Card
        title="Read the affidavit"
        description="Self-authenticating verification report with FRE 902(14) + ISO 27037 + NIST SP 800-86 citations and a step-by-step verify-it-yourself guide."
        href="/judge/affidavit"
        rubric="rubric criterion 5"
      />
    </div>
  );
}
```

- [ ] **Step 5: Run test, expect PASS**

Run: `pnpm --filter @findevil/web test __tests__/judge/landing.test.tsx`
Expected: 2/2 PASS.

- [ ] **Step 6: Manual smoke**

Run `pnpm --filter @findevil/web dev`, navigate to `http://localhost:3000/judge`. Expected: three cards visible, light-theme layout, click each → navigates (404s are OK; routes land in subsequent tasks).

- [ ] **Step 7: Commit**

```bash
git add apps/web/app/judge/ apps/web/__tests__/judge/landing.test.tsx
git commit -m "feat(judge): /judge route shell + landing page"
```

---

## Task 6: `Scrubber` component

**Files:**
- Create: `apps/web/components/judge/Scrubber.tsx`
- Test: `apps/web/__tests__/judge/scrubber.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/web/__tests__/judge/scrubber.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Scrubber } from "@/components/judge/Scrubber";

describe("Scrubber", () => {
  const events = Array.from({ length: 5 }, (_, i) => ({
    seq: i + 1,
    ts: "t",
    kind: "tool_call_start",
    payload: {},
    prev_hash: "p",
    line_hash: "l",
  }));

  it("renders current seq label", () => {
    render(
      <Scrubber
        events={events}
        currentSeq={3}
        speed={1}
        onSeqChange={() => {}}
        onPlayPauseToggle={() => {}}
      />,
    );
    expect(screen.getByLabelText(/seq/i)).toHaveValue("3");
  });

  it("emits onSeqChange when slider moves", () => {
    const cb = vi.fn();
    render(
      <Scrubber
        events={events}
        currentSeq={1}
        speed={1}
        onSeqChange={cb}
        onPlayPauseToggle={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText(/seq/i), { target: { value: "4" } });
    expect(cb).toHaveBeenCalledWith(4);
  });

  it("emits onPlayPauseToggle on Play click", () => {
    const cb = vi.fn();
    render(
      <Scrubber
        events={events}
        currentSeq={1}
        speed={1}
        onSeqChange={() => {}}
        onPlayPauseToggle={cb}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /play|pause/i }));
    expect(cb).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

Run: `pnpm --filter @findevil/web test __tests__/judge/scrubber.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement Scrubber**

Create `apps/web/components/judge/Scrubber.tsx`:

```tsx
"use client";

import type { AuditLine } from "@/lib/judge";

export type ScrubberSpeed = 1 | 2 | 8 | "instant";

export interface ScrubberProps {
  events: AuditLine[];
  currentSeq: number;
  speed: ScrubberSpeed;
  focus?: { from: number; to: number };
  pinnedAnnotationId?: string;
  onSeqChange: (seq: number) => void;
  onPlayPauseToggle: () => void;
  onFocusChange?: (focus: { from: number; to: number } | undefined) => void;
  onPinClick?: (annotationId: string) => void;
  isPlaying?: boolean;
}

export function Scrubber(props: ScrubberProps) {
  const min = props.events[0]?.seq ?? 0;
  const max = props.events[props.events.length - 1]?.seq ?? 0;

  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        alignItems: "center",
        padding: "8px 12px",
        borderBottom: "1px solid #e5e5e5",
        backgroundColor: "white",
        fontFamily: "ui-monospace, monospace",
        fontSize: 13,
      }}
    >
      <button
        type="button"
        onClick={props.onPlayPauseToggle}
        aria-label={props.isPlaying ? "pause" : "play"}
        style={{ padding: "4px 12px", border: "1px solid #d1d5db", borderRadius: 4, cursor: "pointer", backgroundColor: "#f9fafb" }}
      >
        {props.isPlaying ? "Pause" : "Play"}
      </button>
      <label htmlFor="scrubber-seq" style={{ color: "#666" }}>seq</label>
      <input
        id="scrubber-seq"
        type="range"
        min={min}
        max={max}
        value={props.currentSeq}
        onChange={(e) => props.onSeqChange(Number(e.target.value))}
        aria-label="seq scrubber"
        style={{ flex: 1 }}
      />
      <span>
        {props.currentSeq} / {max}
      </span>
    </div>
  );
}
```

- [ ] **Step 4: Run test, expect PASS**

Run: `pnpm --filter @findevil/web test __tests__/judge/scrubber.test.tsx`
Expected: 3/3 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/judge/Scrubber.tsx apps/web/__tests__/judge/scrubber.test.tsx
git commit -m "feat(judge): Scrubber component (top-of-notebook navigation)"
```

---

## Task 7: `SourcePillFilter` component

**Files:**
- Create: `apps/web/components/judge/SourcePillFilter.tsx`
- Test: `apps/web/__tests__/judge/source-pill-filter.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SourcePillFilter } from "@/components/judge/SourcePillFilter";

describe("SourcePillFilter", () => {
  it("renders 5 pills (all roles)", () => {
    render(<SourcePillFilter active={[]} onChange={() => {}} />);
    ["pool_a", "pool_b", "verifier", "judge", "correlator"].forEach((r) =>
      expect(screen.getByRole("button", { name: new RegExp(r, "i") })).toBeDefined(),
    );
  });

  it("toggles a role on click", () => {
    const cb = vi.fn();
    render(<SourcePillFilter active={[]} onChange={cb} />);
    fireEvent.click(screen.getByRole("button", { name: /pool a/i }));
    expect(cb).toHaveBeenCalledWith(["pool_a"]);
  });

  it("removes an active role on second click", () => {
    const cb = vi.fn();
    render(<SourcePillFilter active={["pool_a"]} onChange={cb} />);
    fireEvent.click(screen.getByRole("button", { name: /pool a/i }));
    expect(cb).toHaveBeenCalledWith([]);
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

`pnpm --filter @findevil/web test __tests__/judge/source-pill-filter.test.tsx` → FAIL.

- [ ] **Step 3: Implement**

```tsx
"use client";

export type Role = "pool_a" | "pool_b" | "verifier" | "judge" | "correlator";

export const ROLES: readonly Role[] = ["pool_a", "pool_b", "verifier", "judge", "correlator"] as const;

const ROLE_LABEL: Record<Role, string> = {
  pool_a: "Pool A",
  pool_b: "Pool B",
  verifier: "Verifier",
  judge: "Judge",
  correlator: "Correlator",
};

const ROLE_COLOR: Record<Role, string> = {
  pool_a: "#a16207",
  pool_b: "#1d4ed8",
  verifier: "#7c3aed",
  judge: "#b45309",
  correlator: "#b91c1c",
};

export interface SourcePillFilterProps {
  active: Role[];
  onChange: (next: Role[]) => void;
}

export function SourcePillFilter({ active, onChange }: SourcePillFilterProps) {
  const toggle = (r: Role) => {
    if (active.includes(r)) onChange(active.filter((x) => x !== r));
    else onChange([...active, r]);
  };
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", padding: "6px 0" }}>
      {ROLES.map((r) => {
        const on = active.includes(r);
        return (
          <button
            key={r}
            type="button"
            onClick={() => toggle(r)}
            style={{
              padding: "4px 10px",
              borderRadius: 999,
              border: `1px solid ${ROLE_COLOR[r]}`,
              backgroundColor: on ? ROLE_COLOR[r] : "transparent",
              color: on ? "white" : ROLE_COLOR[r],
              cursor: "pointer",
              fontSize: 12,
              fontFamily: "ui-monospace, monospace",
            }}
          >
            {ROLE_LABEL[r]}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Run, expect PASS**

`pnpm --filter @findevil/web test __tests__/judge/source-pill-filter.test.tsx` → 3/3 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/judge/SourcePillFilter.tsx apps/web/__tests__/judge/source-pill-filter.test.tsx
git commit -m "feat(judge): SourcePillFilter (5 role pills, multi-select)"
```

---

## Task 8: `RubricAnnotation` inline tag-chip component

**Files:**
- Create: `apps/web/components/judge/RubricAnnotation.tsx`
- Test: `apps/web/__tests__/judge/rubric-annotation.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RubricAnnotation } from "@/components/judge/RubricAnnotation";

describe("RubricAnnotation", () => {
  it("renders criterion number badge", () => {
    render(<RubricAnnotation criterion={5} explanation="audit-trail traceability" />);
    expect(screen.getByText(/criterion 5/i)).toBeDefined();
    expect(screen.getByText(/audit-trail traceability/i)).toBeDefined();
  });

  it("uses different colors for different criteria", () => {
    const { container: c1 } = render(<RubricAnnotation criterion={1} explanation="a" />);
    const { container: c5 } = render(<RubricAnnotation criterion={5} explanation="a" />);
    const c1Color = (c1.firstChild as HTMLElement).style.backgroundColor;
    const c5Color = (c5.firstChild as HTMLElement).style.backgroundColor;
    expect(c1Color).not.toEqual(c5Color);
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```tsx
"use client";

export type RubricCriterion = 1 | 2 | 3 | 4 | 5 | 6;

const COLORS: Record<RubricCriterion, string> = {
  1: "#1e40af",
  2: "#7c2d12",
  3: "#166534",
  4: "#6b21a8",
  5: "#b45309",
  6: "#0e7490",
};

const LABELS: Record<RubricCriterion, string> = {
  1: "Autonomy",
  2: "Accuracy",
  3: "Breadth/Depth",
  4: "Constraints",
  5: "Audit Trail",
  6: "Usability",
};

export interface RubricAnnotationProps {
  criterion: RubricCriterion;
  explanation: string;
}

export function RubricAnnotation({ criterion, explanation }: RubricAnnotationProps) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "2px 8px",
        borderRadius: 4,
        backgroundColor: COLORS[criterion],
        color: "white",
        fontSize: 11,
        fontFamily: "ui-monospace, monospace",
      }}
    >
      <strong>criterion {criterion}</strong>
      <span style={{ opacity: 0.85 }}>({LABELS[criterion]}) — {explanation}</span>
    </span>
  );
}
```

- [ ] **Step 4: Run test, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/judge/RubricAnnotation.tsx apps/web/__tests__/judge/rubric-annotation.test.tsx
git commit -m "feat(judge): RubricAnnotation inline tag-chip"
```

---

## Task 9: `AnnotationPin` component

**Files:**
- Create: `apps/web/components/judge/AnnotationPin.tsx`
- Test: `apps/web/__tests__/judge/annotation-pin.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnnotationPin, type AnnotationPinModel } from "@/components/judge/AnnotationPin";

const pin: AnnotationPinModel = {
  id: "ann_1",
  seq: 5,
  kind: "annotation_escalation",
  body: "Escalated to INFERRED because pslist=0 + psscan=124.",
  citedSeqs: [3, 4],
};

describe("AnnotationPin", () => {
  it("collapsed: shows only the kind icon", () => {
    render(<AnnotationPin pin={pin} isOpen={false} onToggle={() => {}} />);
    expect(screen.getByLabelText(/escalation/i)).toBeDefined();
    expect(screen.queryByText(/Escalated to INFERRED/)).toBeNull();
  });

  it("open: shows body markdown", () => {
    render(<AnnotationPin pin={pin} isOpen={true} onToggle={() => {}} />);
    expect(screen.getByText(/Escalated to INFERRED because pslist=0/)).toBeDefined();
  });

  it("emits onToggle when clicked", () => {
    const cb = vi.fn();
    render(<AnnotationPin pin={pin} isOpen={false} onToggle={cb} />);
    fireEvent.click(screen.getByLabelText(/escalation/i));
    expect(cb).toHaveBeenCalledWith("ann_1");
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```tsx
"use client";

import type { AnnotationKind } from "@/lib/judge";

export interface AnnotationPinModel {
  id: string;
  seq: number;
  kind: AnnotationKind;
  body: string;
  citedSeqs: number[];
}

const KIND_ICON: Record<AnnotationKind, string> = {
  annotation_escalation: "⬆",
  annotation_verifier_challenge: "?",
  annotation_judge_merge: "⚖",
  annotation_correlator_veto: "✕",
};

const KIND_LABEL: Record<AnnotationKind, string> = {
  annotation_escalation: "escalation",
  annotation_verifier_challenge: "verifier challenge",
  annotation_judge_merge: "judge merge",
  annotation_correlator_veto: "correlator veto",
};

export interface AnnotationPinProps {
  pin: AnnotationPinModel;
  isOpen: boolean;
  onToggle: (id: string) => void;
}

export function AnnotationPin({ pin, isOpen, onToggle }: AnnotationPinProps) {
  return (
    <span>
      <button
        type="button"
        onClick={() => onToggle(pin.id)}
        aria-label={`${KIND_LABEL[pin.kind]} pin at seq ${pin.seq}`}
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 18,
          height: 18,
          borderRadius: 9,
          border: "1px solid #6b7280",
          backgroundColor: isOpen ? "#fbbf24" : "white",
          cursor: "pointer",
          fontSize: 10,
          fontFamily: "ui-monospace, monospace",
        }}
      >
        {KIND_ICON[pin.kind]}
      </button>
      {isOpen ? (
        <div
          style={{
            marginTop: 6,
            padding: "8px 12px",
            border: "1px solid #d1d5db",
            backgroundColor: "#fffbeb",
            borderRadius: 4,
            fontSize: 13,
          }}
        >
          <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>
            {KIND_LABEL[pin.kind]} · seq {pin.seq} · cites {pin.citedSeqs.join(", ")}
          </div>
          <div>{pin.body}</div>
        </div>
      ) : null}
    </span>
  );
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/judge/AnnotationPin.tsx apps/web/__tests__/judge/annotation-pin.test.tsx
git commit -m "feat(judge): AnnotationPin (agent-emitted inline annotations)"
```

---

## Task 10: `TimeGapMarker` component

**Files:**
- Create: `apps/web/components/judge/TimeGapMarker.tsx`
- Test: `apps/web/__tests__/judge/time-gap-marker.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TimeGapMarker } from "@/components/judge/TimeGapMarker";

describe("TimeGapMarker", () => {
  it("renders seconds when gap < 60s", () => {
    render(<TimeGapMarker gapSeconds={42} />);
    expect(screen.getByText(/42 seconds/i)).toBeDefined();
  });
  it("renders minutes when 60s <= gap < 3600s", () => {
    render(<TimeGapMarker gapSeconds={1380} />);
    expect(screen.getByText(/23 minutes/i)).toBeDefined();
  });
  it("renders days for very large gaps", () => {
    render(<TimeGapMarker gapSeconds={172800} />);
    expect(screen.getByText(/2 days/i)).toBeDefined();
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```tsx
export interface TimeGapMarkerProps {
  gapSeconds: number;
}

function formatGap(secs: number): string {
  if (secs < 60) return `${Math.round(secs)} seconds`;
  if (secs < 3600) return `${Math.round(secs / 60)} minutes`;
  if (secs < 86400) return `${Math.round(secs / 3600)} hours`;
  return `${Math.round(secs / 86400)} days`;
}

export function TimeGapMarker({ gapSeconds }: TimeGapMarkerProps) {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "8px 0",
        margin: "8px 0",
        color: "#666",
        fontSize: 12,
        fontStyle: "italic",
        borderTop: "1px dashed #d1d5db",
        borderBottom: "1px dashed #d1d5db",
      }}
    >
      … gap of {formatGap(gapSeconds)} …
    </div>
  );
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/judge/TimeGapMarker.tsx apps/web/__tests__/judge/time-gap-marker.test.tsx
git commit -m "feat(judge): TimeGapMarker (visible-pause divider)"
```

---

## Task 11: `FilterSidebar` component

**Files:**
- Create: `apps/web/components/judge/FilterSidebar.tsx`
- Test: `apps/web/__tests__/judge/filter-sidebar.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FilterSidebar } from "@/components/judge/FilterSidebar";
import { defaultFilterSet } from "@/lib/judge";

describe("FilterSidebar", () => {
  it("default state: hideBookkeeping checked, hideHypothesis checked", () => {
    render(<FilterSidebar value={defaultFilterSet()} onChange={() => {}} />);
    expect((screen.getByLabelText(/hide bookkeeping/i) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/hide hypothesis/i) as HTMLInputElement).checked).toBe(true);
  });

  it("toggling hideBookkeeping fires onChange", () => {
    const cb = vi.fn();
    render(<FilterSidebar value={defaultFilterSet()} onChange={cb} />);
    fireEvent.click(screen.getByLabelText(/hide bookkeeping/i));
    expect(cb).toHaveBeenCalledWith(expect.objectContaining({ hideBookkeeping: false }));
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```tsx
"use client";

import type { FilterSet } from "@/lib/judge";

export interface FilterSidebarProps {
  value: FilterSet;
  onChange: (next: FilterSet) => void;
}

export function FilterSidebar({ value, onChange }: FilterSidebarProps) {
  const set = (patch: Partial<FilterSet>) => onChange({ ...value, ...patch });
  const row: React.CSSProperties = { display: "flex", gap: 8, alignItems: "center", padding: "4px 0" };
  return (
    <aside
      style={{
        padding: "12px 16px",
        borderRight: "1px solid #e5e5e5",
        backgroundColor: "white",
        minWidth: 200,
        fontSize: 13,
        fontFamily: "ui-monospace, monospace",
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 8 }}>Filters</div>
      <label style={row}>
        <input
          type="checkbox"
          checked={value.hideBookkeeping}
          onChange={(e) => set({ hideBookkeeping: e.target.checked })}
        />
        hide bookkeeping
      </label>
      <label style={row}>
        <input
          type="checkbox"
          checked={value.hideHypothesis}
          onChange={(e) => set({ hideHypothesis: e.target.checked })}
        />
        hide hypothesis
      </label>
    </aside>
  );
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/judge/FilterSidebar.tsx apps/web/__tests__/judge/filter-sidebar.test.tsx
git commit -m "feat(judge): FilterSidebar (Autopsy-style left-rail filters)"
```

---

## Task 12: `SummaryModeToggle` component

**Files:**
- Create: `apps/web/components/judge/SummaryModeToggle.tsx`
- Test: `apps/web/__tests__/judge/summary-mode-toggle.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SummaryModeToggle } from "@/components/judge/SummaryModeToggle";

describe("SummaryModeToggle", () => {
  it("highlights the active mode", () => {
    render(<SummaryModeToggle mode="summary" onChange={() => {}} />);
    expect(screen.getByRole("button", { name: /summary/i }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: /detail/i }).getAttribute("aria-pressed")).toBe("false");
  });

  it("emits onChange on click", () => {
    const cb = vi.fn();
    render(<SummaryModeToggle mode="summary" onChange={cb} />);
    fireEvent.click(screen.getByRole("button", { name: /detail/i }));
    expect(cb).toHaveBeenCalledWith("detail");
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```tsx
"use client";

export type SummaryMode = "summary" | "detail";

export interface SummaryModeToggleProps {
  mode: SummaryMode;
  onChange: (next: SummaryMode) => void;
}

const Btn = ({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) => (
  <button
    type="button"
    onClick={onClick}
    aria-pressed={active}
    style={{
      padding: "4px 12px",
      border: "1px solid #d1d5db",
      backgroundColor: active ? "#1f2937" : "white",
      color: active ? "white" : "#1f2937",
      cursor: "pointer",
      fontSize: 12,
      fontFamily: "ui-monospace, monospace",
    }}
  >
    {children}
  </button>
);

export function SummaryModeToggle({ mode, onChange }: SummaryModeToggleProps) {
  return (
    <div style={{ display: "inline-flex", borderRadius: 4, overflow: "hidden" }}>
      <Btn active={mode === "summary"} onClick={() => onChange("summary")}>Summary</Btn>
      <Btn active={mode === "detail"} onClick={() => onChange("detail")}>Detail</Btn>
    </div>
  );
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/judge/SummaryModeToggle.tsx apps/web/__tests__/judge/summary-mode-toggle.test.tsx
git commit -m "feat(judge): SummaryModeToggle (summary | detail segmented control)"
```

---

## Task 13: `NotebookView` (per-row body)

**Files:**
- Create: `apps/web/components/judge/NotebookView.tsx`
- Test: `apps/web/__tests__/judge/notebook-view.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NotebookView } from "@/components/judge/NotebookView";
import type { AuditLine } from "@/lib/judge";

const events: AuditLine[] = [
  { seq: 1, ts: "2026-04-27T00:00:00Z", kind: "tool_call_start", payload: { tool: "vol_pslist", pool: "A" }, prev_hash: "0", line_hash: "1" },
  { seq: 2, ts: "2026-04-27T00:00:01Z", kind: "finding_approved", payload: { confidence: "INFERRED", mitre: "T1014", summary: "DKOM" }, prev_hash: "1", line_hash: "2" },
];

describe("NotebookView", () => {
  it("renders one row per event", () => {
    render(<NotebookView events={events} />);
    expect(screen.getByText(/vol_pslist/i)).toBeDefined();
    expect(screen.getByText(/T1014/i)).toBeDefined();
  });

  it("highlights the current seq", () => {
    const { container } = render(<NotebookView events={events} currentSeq={2} />);
    const rows = container.querySelectorAll("[data-seq]");
    const current = Array.from(rows).find((r) => r.getAttribute("data-seq") === "2");
    expect((current as HTMLElement).dataset.current).toBe("true");
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```tsx
"use client";

import type { AuditLine } from "@/lib/judge";

export interface NotebookViewProps {
  events: AuditLine[];
  currentSeq?: number;
}

function rowSummary(line: AuditLine): string {
  const p = line.payload as Record<string, unknown>;
  if (line.kind === "tool_call_start") return `${p.tool ?? "(tool)"} starting`;
  if (line.kind === "tool_call_end") return `${p.tool ?? "(tool)"} done`;
  if (line.kind === "finding_approved" || line.kind === "finding_draft") {
    const mitre = p.mitre ? `[${p.mitre}] ` : "";
    return `${mitre}${p.summary ?? "(finding)"}`;
  }
  if (line.kind === "acp_handoff") return `handoff ${p.from_role} → ${p.to_role}`;
  if (line.kind === "judge_selfscore") return `selfscore criterion ${p.criterion}`;
  return line.kind;
}

export function NotebookView({ events, currentSeq }: NotebookViewProps) {
  return (
    <div style={{ fontFamily: "ui-monospace, monospace", fontSize: 13 }}>
      {events.map((line) => {
        const isCurrent = line.seq === currentSeq;
        return (
          <div
            key={line.seq}
            data-seq={line.seq}
            data-current={isCurrent}
            style={{
              display: "grid",
              gridTemplateColumns: "60px 140px 1fr",
              gap: 12,
              padding: "6px 12px",
              borderBottom: "1px solid #f3f4f6",
              backgroundColor: isCurrent ? "#fef3c7" : "transparent",
            }}
          >
            <span style={{ color: "#6b7280" }}>seq {line.seq}</span>
            <span style={{ color: "#374151" }}>{line.kind}</span>
            <span>{rowSummary(line)}</span>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/judge/NotebookView.tsx apps/web/__tests__/judge/notebook-view.test.tsx
git commit -m "feat(judge): NotebookView (forensic-notebook per-row body)"
```

---

## Task 14: Wire components into `/judge/replay/page.tsx`

**Files:**
- Create: `apps/web/app/judge/replay/page.tsx`
- Test: `apps/web/__tests__/judge/replay-page.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ReplayPage from "@/app/judge/replay/page";

global.fetch = vi.fn(async () =>
  new Response(
    JSON.stringify({
      events: [
        { seq: 1, ts: "t", kind: "tool_call_start", payload: { tool: "vol_pslist" }, prev_hash: "0", line_hash: "1" },
      ],
      manifest: null,
      sigstoreCert: null,
      otsReceiptBase64: null,
      caseMeta: { case_id: "c1", audit_line_count: 1, first_event_ts: "t", last_event_ts: "t", curated_at: "t" },
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  ),
);

describe("ReplayPage", () => {
  it("fetches the case bundle and renders events", async () => {
    render(<ReplayPage />);
    await waitFor(() => expect(screen.getByText(/vol_pslist/i)).toBeDefined());
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { FilterSidebar } from "@/components/judge/FilterSidebar";
import { NotebookView } from "@/components/judge/NotebookView";
import { Scrubber } from "@/components/judge/Scrubber";
import { SourcePillFilter, type Role } from "@/components/judge/SourcePillFilter";
import { SummaryModeToggle, type SummaryMode } from "@/components/judge/SummaryModeToggle";
import { applyFilters, defaultFilterSet, type CaseBundle, type FilterSet } from "@/lib/judge";

export default function ReplayPage() {
  const [bundle, setBundle] = useState<CaseBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seq, setSeq] = useState(1);
  const [mode, setMode] = useState<SummaryMode>("summary");
  const [filters, setFilters] = useState<FilterSet>(defaultFilterSet());
  const [activeRoles, setActiveRoles] = useState<Role[]>([]);

  useEffect(() => {
    fetch("/api/judge/case")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((b: CaseBundle) => setBundle(b))
      .catch((e) => setError(String(e)));
  }, []);

  const filtered = useMemo(() => {
    if (!bundle) return [];
    let evs = applyFilters(bundle.events, filters);
    if (activeRoles.length > 0) {
      evs = evs.filter((e) => {
        const p = e.payload as { pool?: string; pool_origin?: string; from_role?: string };
        const role = p.pool ?? p.pool_origin ?? p.from_role;
        return activeRoles.includes(role as Role);
      });
    }
    return evs;
  }, [bundle, filters, activeRoles]);

  if (error) return <div>error: {error}</div>;
  if (!bundle) return <div>loading…</div>;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 0 }}>
      <FilterSidebar value={filters} onChange={setFilters} />
      <div>
        <div style={{ display: "flex", gap: 12, alignItems: "center", padding: "8px 12px", borderBottom: "1px solid #e5e5e5", backgroundColor: "white" }}>
          <SummaryModeToggle mode={mode} onChange={setMode} />
          <div style={{ flex: 1 }} />
          <SourcePillFilter active={activeRoles} onChange={setActiveRoles} />
        </div>
        <Scrubber events={bundle.events} currentSeq={seq} speed={1} onSeqChange={setSeq} onPlayPauseToggle={() => {}} />
        {mode === "detail" ? (
          <NotebookView events={filtered} currentSeq={seq} />
        ) : (
          <div style={{ padding: 24, fontFamily: "ui-monospace, monospace", color: "#6b7280" }}>
            Summary mode (stacked-bar histogram lands in a Plan A follow-up if the v1 demo needs it; default landing today is detail mode at seq=1).
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test, expect PASS**

- [ ] **Step 5: Manual smoke**

`pnpm --filter @findevil/web dev`, navigate to `http://localhost:3000/judge/replay`. Expected: filter sidebar on left, mode toggle + role pills on top, scrubber, notebook view below with curated case events.

- [ ] **Step 6: Commit**

```bash
git add apps/web/app/judge/replay/page.tsx apps/web/__tests__/judge/replay-page.test.tsx
git commit -m "feat(judge): /judge/replay wires sidebar + scrubber + notebook + filters"
```

---

## Task 15: Add Playwright E2E for the replay flow

**Files:**
- Modify: `apps/web/package.json` (add `@playwright/test`)
- Create: `apps/web/playwright.config.ts`
- Create: `apps/web/e2e/judge-replay.spec.ts`

- [ ] **Step 1: Install Playwright**

```bash
cd apps/web
pnpm add -D @playwright/test@^1.48.0
pnpm exec playwright install chromium
```

- [ ] **Step 2: Write `playwright.config.ts`**

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
  },
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
```

- [ ] **Step 3: Write E2E test**

Create `apps/web/e2e/judge-replay.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

test("replay route loads curated case + renders events", async ({ page }) => {
  await page.goto("/judge/replay");
  await expect(page.getByText(/seq 1/i)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByLabel(/seq scrubber/i)).toBeVisible();
});
```

- [ ] **Step 4: Run E2E**

```bash
cd apps/web
pnpm exec playwright test
```

Expected: 1/1 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/package.json apps/web/pnpm-lock.yaml apps/web/playwright.config.ts apps/web/e2e/
git commit -m "test(judge): Playwright E2E for /judge/replay"
```

---

## Task 16: Wire into L1 CI

**Files:**
- Modify: `docker/l1-compose.yml` (extend the apps/web step)

- [ ] **Step 1: Inspect current L1 step**

```bash
grep -n "@findevil/web" docker/l1-compose.yml
```

- [ ] **Step 2: Add Vitest + Playwright invocations**

Edit `docker/l1-compose.yml` to extend the apps/web command. Find the existing `pnpm --filter @findevil/web test` line and add `pnpm --filter @findevil/web exec playwright test` after it. (Exact diff depends on current file; the engineer adds the line in the same `command:` block.)

- [ ] **Step 3: Run smokes locally**

```bash
SKIP_SLOW_RUST=1 bash scripts/run-all-smokes.sh
```

Expected: 13/13 still pass (Vitest tests are added; Playwright is gated to apps/web's test step).

- [ ] **Step 4: Commit**

```bash
git add docker/l1-compose.yml
git commit -m "ci(judge): wire Plan A Vitest + Playwright into L1"
```

---

## Task 17: Update README + CHANGELOG

**Files:**
- Modify: `apps/web/README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update apps/web/README.md status block**

Find the Status block; change "5 sprite components — pending Claude Design pass (Phase 5)" line — leave it. Add new line: `Judge Mode (Plan A) — /judge/replay shipped`.

- [ ] **Step 2: Update CHANGELOG.md**

Append under [Unreleased] → Added — feature surface:

```
- **Judge Mode Plan A — /judge route shell + /judge/replay**: forensic-
  notebook walking tour against a curated case dir.  New components:
  Scrubber, NotebookView, SourcePillFilter, AnnotationPin,
  RubricAnnotation, TimeGapMarker, FilterSidebar, SummaryModeToggle.
  New API route /api/judge/case.  New script
  scripts/curate-judge-case.sh + initial goldens/judge-case/ bundle.
  Vitest + RTL + happy-dom test infrastructure added; Playwright E2E
  smoke wired into L1 CI.  Plans B (tamper) and C (affidavit) compose
  on this foundation.  Spec:
  docs/superpowers/specs/2026-04-27-surprise-design-judge-mode.md.
```

- [ ] **Step 3: Run final smokes**

```bash
SKIP_SLOW_RUST=1 bash scripts/run-all-smokes.sh
```

Expected: 13/13 PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/web/README.md CHANGELOG.md
git commit -m "docs(judge): Plan A status + CHANGELOG entry"
```

---

## Verification (end of Plan A)

After Task 17, the following must all hold:

- `pnpm --filter @findevil/web test` — all Vitest tests pass (existing 8 + new ~12 = 20+)
- `pnpm --filter @findevil/web exec playwright test` — 1/1 E2E pass
- `pnpm --filter @findevil/web build` — Next.js build succeeds
- `pnpm --filter @findevil/web typecheck` — clean
- `SKIP_SLOW_RUST=1 bash scripts/run-all-smokes.sh` — 13/13 pass
- Visit `http://localhost:3000/judge` → three-card landing page
- Click "Watch a curated investigation" → filter sidebar + scrubber + notebook with events from `goldens/judge-case/`
- The other two cards 404 (Plans B + C land them)

If any of those fails, don't proceed to Plan B until resolved.
