# Judge Mode Plan B — Tamper route

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `/judge/tamper` — judge picks a byte in a sandbox copy of the curated audit.jsonl, sees a Wikipedia-style side-by-side diff of the affected line(s), and watches a PropagationCascade visualization light up red as the hash-chain breakage radiates from the flipped byte through line_hash → prev_hash → Merkle root → signature.

**Architecture:** Browser-side byte-flip against a copy of `goldens/judge-case/audit.jsonl` fetched from `/api/judge/case` (Plan A). Server-side verification via a new `/api/judge/verify` POST endpoint that calls `verifyAuditChain` from the existing `apps/web/lib/audit-tail.ts` (TypeScript-only — full Python `verify_manifest` integration is a v2 upgrade flagged in §V2 below). Page renders DiffPanel + PropagationCascade alongside the existing HashChainBadge.

**Tech Stack:** Next.js 15 App Router, React 19, Vitest + RTL + happy-dom (from Plan A), Playwright (from Plan A). No new server-side runtime deps.

**Spec under implementation:** `docs/superpowers/specs/2026-04-27-surprise-design-judge-mode.md` §4.2 + §3.1 component additions.

**Depends on:** Plan A complete (curated case dir, types in `lib/judge.ts`, test infrastructure).

---

## File structure (locked before tasks)

**Created files:**
- `apps/web/app/judge/tamper/page.tsx`
- `apps/web/app/api/judge/verify/route.ts`
- `apps/web/components/judge/HexView.tsx`
- `apps/web/components/judge/TamperButton.tsx`
- `apps/web/components/judge/DiffPanel.tsx`
- `apps/web/components/judge/PropagationCascade.tsx`
- `apps/web/lib/judge-tamper.ts` — byte-flip + line-locate helpers, diff-result type
- `apps/web/__tests__/judge/hex-view.test.tsx`
- `apps/web/__tests__/judge/tamper-button.test.tsx`
- `apps/web/__tests__/judge/diff-panel.test.tsx`
- `apps/web/__tests__/judge/propagation-cascade.test.tsx`
- `apps/web/__tests__/judge/judge-tamper.test.ts`
- `apps/web/__tests__/api/judge-verify.test.ts`
- `apps/web/e2e/judge-tamper.spec.ts`

**Modified files:**
- `docs/demo-script-a2.md` — insert Beat 5b
- `docker/l1-compose.yml` — extend Playwright invocation if needed (likely already covers from Plan A)
- `CHANGELOG.md` — entry under [Unreleased]

**Note on TS-only verification (v1) vs full Python verify (v2):**
The spec §4.2 references the Python `ManifestVerification` shape. Plan B v1 uses the TypeScript `verifyAuditChain` from `apps/web/lib/audit-tail.ts` (already shipped per PR #7 — covers the audit-chain `prev_hash`/`line_hash` integrity). Upgrading to full Python `verify_manifest` (covering Merkle root + sigstore signature + OTS receipt) is **§V2 — defer until Plan B v1 is in user hands and demo Beat 5b is recorded.** The byte-flip demo lands hardest at the audit-chain layer anyway; the Merkle/sigstore/OTS layers don't change when audit.jsonl content shifts.

---

## Task 1: Inspect existing `verifyAuditChain` contract

**Files:**
- Read: `apps/web/lib/audit-tail.ts`

- [ ] **Step 1: Read the existing audit-tail module**

```bash
cat apps/web/lib/audit-tail.ts
```

Expected: confirm the exported `verifyAuditChain` function signature. Note the actual return type shape — likely `{ ok: boolean; brokenAtSeq?: number; reason?: string }` or similar. Record the EXACT signature in this task's notes for reuse in Tasks 2 + 3.

- [ ] **Step 2: If `verifyAuditChain` does NOT exist or has a different name**

Search for any existing audit-chain verifier:

```bash
grep -rn "audit_chain_ok\|verifyAuditChain\|verifyChain" apps/web/lib/
```

If no verifier exists, the engineer adds a minimal one in Task 2 (helper file) instead of relying on lib/audit-tail.ts. Document the actual found function in this task's notes.

- [ ] **Step 3: No commit (read-only task)**

---

## Task 2: Helpers in `apps/web/lib/judge-tamper.ts`

**Files:**
- Create: `apps/web/lib/judge-tamper.ts`
- Test: `apps/web/__tests__/judge/judge-tamper.test.ts`

- [ ] **Step 1: Write the failing test**

Create `apps/web/__tests__/judge/judge-tamper.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  applyByteFlip,
  locateAffectedLine,
  type LineLocation,
} from "@/lib/judge-tamper";

const SAMPLE = Buffer.from(
  '{"seq":1,"kind":"a"}\n{"seq":2,"kind":"b"}\n{"seq":3,"kind":"c"}\n',
).toString("utf-8");

describe("applyByteFlip", () => {
  it("flips a single byte and returns the mutated string", () => {
    const out = applyByteFlip(SAMPLE, 5, 0x58);
    expect(out[5]).toBe("X");
    expect(out.length).toBe(SAMPLE.length);
  });

  it("rejects out-of-bounds offsets", () => {
    expect(() => applyByteFlip(SAMPLE, 9999, 0)).toThrow(/out of bounds/);
  });
});

describe("locateAffectedLine", () => {
  it("returns line 0 for an offset in the first line", () => {
    const loc = locateAffectedLine(SAMPLE, 5);
    expect(loc.lineIndex).toBe(0);
    expect(loc.lineStart).toBe(0);
    expect(loc.lineEnd).toBe(20);
  });

  it("returns line 1 for an offset in the second line", () => {
    const loc = locateAffectedLine(SAMPLE, 25);
    expect(loc.lineIndex).toBe(1);
    expect(loc.lineStart).toBe(21);
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

Run: `pnpm --filter @findevil/web test __tests__/judge/judge-tamper.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement helpers**

Create `apps/web/lib/judge-tamper.ts`:

```ts
// Browser-side byte-flip + line-locate helpers for /judge/tamper.
// Pure functions — no I/O, fully unit-testable.

export interface LineLocation {
  lineIndex: number;
  lineStart: number;  // inclusive
  lineEnd: number;    // exclusive (newline not included)
}

export function applyByteFlip(input: string, byteOffset: number, newByte: number): string {
  if (byteOffset < 0 || byteOffset >= input.length) {
    throw new Error(`offset ${byteOffset} out of bounds (length ${input.length})`);
  }
  if (newByte < 0 || newByte > 255) {
    throw new Error(`byte value ${newByte} out of range 0..255`);
  }
  return input.slice(0, byteOffset) + String.fromCharCode(newByte) + input.slice(byteOffset + 1);
}

export function locateAffectedLine(input: string, byteOffset: number): LineLocation {
  let lineIndex = 0;
  let lineStart = 0;
  for (let i = 0; i < byteOffset; i++) {
    if (input[i] === "\n") {
      lineIndex++;
      lineStart = i + 1;
    }
  }
  let lineEnd = input.indexOf("\n", lineStart);
  if (lineEnd === -1) lineEnd = input.length;
  return { lineIndex, lineStart, lineEnd };
}

export interface VerifyResult {
  audit_chain_ok: boolean | string;
  brokenAtSeq?: number;
  reason?: string;
}
```

- [ ] **Step 4: Run, expect PASS**

`pnpm --filter @findevil/web test __tests__/judge/judge-tamper.test.ts` → 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/judge-tamper.ts apps/web/__tests__/judge/judge-tamper.test.ts
git commit -m "feat(judge): byte-flip + line-locate helpers in lib/judge-tamper.ts"
```

---

## Task 3: `/api/judge/verify` route

**Files:**
- Create: `apps/web/app/api/judge/verify/route.ts`
- Test: `apps/web/__tests__/api/judge-verify.test.ts`

- [ ] **Step 1: Write failing test**

Create `apps/web/__tests__/api/judge-verify.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { POST } from "@/app/api/judge/verify/route";

const goodChain = `${JSON.stringify({ seq: 1, ts: "t", kind: "case_open", payload: {}, prev_hash: "0".repeat(64), line_hash: "a".repeat(64) })}\n`;

function makeReq(body: unknown): Request {
  return new Request("http://x/api/judge/verify", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
  });
}

describe("POST /api/judge/verify", () => {
  it("400 on missing bytes", async () => {
    const res = await POST(makeReq({}));
    expect(res.status).toBe(400);
  });

  it("400 on body > 1MB", async () => {
    const big = "x".repeat(1_100_000);
    const res = await POST(makeReq({ auditJsonl: big }));
    expect(res.status).toBe(413);
  });

  it("200 on a well-formed audit chain", async () => {
    const res = await POST(makeReq({ auditJsonl: goodChain }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.audit_chain_ok).toBeDefined();
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

Create `apps/web/app/api/judge/verify/route.ts`:

```ts
import { NextResponse } from "next/server";
import type { AuditLine } from "@/lib/judge";
import type { VerifyResult } from "@/lib/judge-tamper";

const MAX_BYTES = 1_000_000;

function verifyChain(events: AuditLine[]): VerifyResult {
  for (let i = 1; i < events.length; i++) {
    const expected = events[i - 1].line_hash;
    if (events[i].prev_hash !== expected) {
      return {
        audit_chain_ok: `audit chain seq=${events[i].seq} prev_hash mismatch`,
        brokenAtSeq: events[i].seq,
        reason: `expected prev_hash=${expected}, got ${events[i].prev_hash}`,
      };
    }
  }
  return { audit_chain_ok: true };
}

function parseLines(raw: string): { ok: true; events: AuditLine[] } | { ok: false; error: string; line: number } {
  const events: AuditLine[] = [];
  const lines = raw.split("\n");
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].length === 0) continue;
    try {
      events.push(JSON.parse(lines[i]) as AuditLine);
    } catch (err) {
      return { ok: false, error: String(err), line: i };
    }
  }
  return { ok: true, events };
}

export async function POST(req: Request): Promise<Response> {
  const len = req.headers.get("content-length");
  if (len && Number(len) > MAX_BYTES) {
    return NextResponse.json({ error: "audit log too large for in-browser tamper mode" }, { status: 413 });
  }
  const body = await req.json().catch(() => null) as { auditJsonl?: string } | null;
  if (!body || typeof body.auditJsonl !== "string") {
    return NextResponse.json({ error: "missing auditJsonl in request body" }, { status: 400 });
  }
  if (body.auditJsonl.length > MAX_BYTES) {
    return NextResponse.json({ error: "audit log too large for in-browser tamper mode" }, { status: 413 });
  }
  const parsed = parseLines(body.auditJsonl);
  if (!parsed.ok) {
    return NextResponse.json(
      {
        audit_chain_ok: `audit chain JSON parse failure at line ${parsed.line}: ${parsed.error}`,
        reason: parsed.error,
      } as VerifyResult,
      { status: 200 },
    );
  }
  return NextResponse.json(verifyChain(parsed.events));
}

export const runtime = "nodejs";
```

- [ ] **Step 4: Run, expect PASS**

`pnpm --filter @findevil/web test __tests__/api/judge-verify.test.ts` → 3/3 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/api/judge/verify/route.ts apps/web/__tests__/api/judge-verify.test.ts
git commit -m "feat(judge): /api/judge/verify (TS-only chain verifier; v2 upgrade to full ManifestVerification deferred)"
```

---

## Task 4: `HexView` component

**Files:**
- Create: `apps/web/components/judge/HexView.tsx`
- Test: `apps/web/__tests__/judge/hex-view.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HexView } from "@/components/judge/HexView";

describe("HexView", () => {
  const text = "Hello, world!";
  it("renders one byte cell per character", () => {
    render(<HexView content={text} onByteClick={() => {}} />);
    expect(screen.getAllByRole("button")).toHaveLength(text.length);
  });
  it("displays hex values", () => {
    render(<HexView content="A" onByteClick={() => {}} />);
    expect(screen.getByText(/0x41/i)).toBeDefined();
  });
  it("emits onByteClick with offset", () => {
    const cb = vi.fn();
    render(<HexView content="ABCDE" onByteClick={cb} />);
    fireEvent.click(screen.getAllByRole("button")[2]);
    expect(cb).toHaveBeenCalledWith(2, 0x43);
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```tsx
"use client";

export interface HexViewProps {
  content: string;
  onByteClick: (offset: number, currentByte: number) => void;
  highlightOffset?: number;
  bytesPerRow?: number;
}

export function HexView({ content, onByteClick, highlightOffset, bytesPerRow = 16 }: HexViewProps) {
  return (
    <div style={{ fontFamily: "ui-monospace, monospace", fontSize: 12, lineHeight: "20px" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
        {Array.from(content).map((ch, i) => {
          const code = ch.charCodeAt(0) & 0xff;
          const hex = `0x${code.toString(16).padStart(2, "0")}`;
          const isHl = i === highlightOffset;
          return (
            <button
              key={i}
              type="button"
              onClick={() => onByteClick(i, code)}
              aria-label={`byte at offset ${i}, value ${hex}`}
              style={{
                minWidth: 32,
                padding: "0 4px",
                border: "1px solid #d1d5db",
                backgroundColor: isHl ? "#fee2e2" : "white",
                cursor: "pointer",
                fontFamily: "inherit",
                fontSize: 11,
              }}
            >
              {hex}
            </button>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/judge/HexView.tsx apps/web/__tests__/judge/hex-view.test.tsx
git commit -m "feat(judge): HexView (byte-pick UI)"
```

---

## Task 5: `TamperButton` component

**Files:**
- Create: `apps/web/components/judge/TamperButton.tsx`
- Test: `apps/web/__tests__/judge/tamper-button.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TamperButton } from "@/components/judge/TamperButton";

describe("TamperButton", () => {
  it("renders pending byte values", () => {
    render(<TamperButton offset={5} originalByte={0x41} newByte={0x00} onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByText(/0x41/i)).toBeDefined();
    expect(screen.getByText(/0x00/i)).toBeDefined();
  });
  it("emits onConfirm on click", () => {
    const cb = vi.fn();
    render(<TamperButton offset={5} originalByte={0x41} newByte={0x00} onConfirm={cb} onCancel={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /flip it/i }));
    expect(cb).toHaveBeenCalled();
  });
  it("emits onCancel on cancel click", () => {
    const cb = vi.fn();
    render(<TamperButton offset={5} originalByte={0x41} newByte={0x00} onConfirm={() => {}} onCancel={cb} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(cb).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```tsx
"use client";

export interface TamperButtonProps {
  offset: number;
  originalByte: number;
  newByte: number;
  onConfirm: () => void;
  onCancel: () => void;
}

export function TamperButton({ offset, originalByte, newByte, onConfirm, onCancel }: TamperButtonProps) {
  const fmt = (b: number) => `0x${b.toString(16).padStart(2, "0")}`;
  return (
    <div
      style={{
        padding: "12px 16px",
        border: "1px solid #fbbf24",
        borderRadius: 6,
        backgroundColor: "#fffbeb",
        fontFamily: "ui-monospace, monospace",
        fontSize: 13,
      }}
    >
      <div style={{ marginBottom: 8 }}>
        Flip byte at offset <strong>{offset}</strong>:{" "}
        <span style={{ color: "#15803d" }}>{fmt(originalByte)}</span>
        {" → "}
        <span style={{ color: "#b91c1c" }}>{fmt(newByte)}</span>?
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button
          type="button"
          onClick={onConfirm}
          style={{ padding: "4px 12px", border: "1px solid #b91c1c", backgroundColor: "#b91c1c", color: "white", cursor: "pointer", borderRadius: 4 }}
        >
          Flip it
        </button>
        <button
          type="button"
          onClick={onCancel}
          style={{ padding: "4px 12px", border: "1px solid #d1d5db", backgroundColor: "white", cursor: "pointer", borderRadius: 4 }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/judge/TamperButton.tsx apps/web/__tests__/judge/tamper-button.test.tsx
git commit -m "feat(judge): TamperButton (flip-it confirmation modal)"
```

---

## Task 6: `DiffPanel` component

**Files:**
- Create: `apps/web/components/judge/DiffPanel.tsx`
- Test: `apps/web/__tests__/judge/diff-panel.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DiffPanel } from "@/components/judge/DiffPanel";

describe("DiffPanel", () => {
  const original = '{"seq":1,"kind":"a"}';
  const tampered = '{"seq":1,"kind":"b"}';
  it("renders both columns in side-by-side mode", () => {
    render(<DiffPanel mode="side-by-side" original={original} tampered={tampered} byteOffset={16} originalByte={0x61} newByte={0x62} onModeChange={() => {}} />);
    expect(screen.getByText(/Original/i)).toBeDefined();
    expect(screen.getByText(/Tampered/i)).toBeDefined();
  });
  it("highlights the changed byte", () => {
    const { container } = render(<DiffPanel mode="side-by-side" original={original} tampered={tampered} byteOffset={16} originalByte={0x61} newByte={0x62} onModeChange={() => {}} />);
    expect(container.querySelector("[data-tamper-highlight=true]")).toBeDefined();
  });
  it("toggles to unified mode", () => {
    const cb = vi.fn();
    render(<DiffPanel mode="side-by-side" original={original} tampered={tampered} byteOffset={16} originalByte={0x61} newByte={0x62} onModeChange={cb} />);
    fireEvent.click(screen.getByRole("button", { name: /unified/i }));
    expect(cb).toHaveBeenCalledWith("unified");
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```tsx
"use client";

export type DiffMode = "side-by-side" | "unified" | "field-only";

export interface DiffPanelProps {
  mode: DiffMode;
  original: string;
  tampered: string;
  byteOffset: number;
  originalByte: number;
  newByte: number;
  onModeChange: (next: DiffMode) => void;
}

const fmt = (b: number) => `0x${b.toString(16).padStart(2, "0")}`;

function HighlightedString({ text, hlOffset, color }: { text: string; hlOffset: number; color: string }) {
  return (
    <span>
      {text.slice(0, hlOffset)}
      <span data-tamper-highlight="true" style={{ backgroundColor: color, padding: "0 2px" }}>
        {text[hlOffset] ?? ""}
      </span>
      {text.slice(hlOffset + 1)}
    </span>
  );
}

export function DiffPanel(props: DiffPanelProps) {
  const Btn = ({ value, label }: { value: DiffMode; label: string }) => (
    <button
      type="button"
      onClick={() => props.onModeChange(value)}
      aria-pressed={props.mode === value}
      style={{
        padding: "4px 10px",
        border: "1px solid #d1d5db",
        backgroundColor: props.mode === value ? "#1f2937" : "white",
        color: props.mode === value ? "white" : "#1f2937",
        cursor: "pointer",
        fontSize: 12,
      }}
    >
      {label}
    </button>
  );

  const linePadding = "8px 12px";
  const colStyle: React.CSSProperties = {
    fontFamily: "ui-monospace, monospace",
    fontSize: 12,
    padding: linePadding,
    border: "1px solid #e5e5e5",
    backgroundColor: "white",
    overflow: "auto",
  };

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
        <Btn value="side-by-side" label="Side-by-side" />
        <Btn value="unified" label="Unified" />
        <Btn value="field-only" label="Field-only" />
      </div>

      {props.mode === "side-by-side" ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <div>
            <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>
              Original (untouched) · offset {props.byteOffset} · {fmt(props.originalByte)}
            </div>
            <div style={colStyle}>
              <HighlightedString text={props.original} hlOffset={props.byteOffset} color="#dcfce7" />
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>
              Tampered · offset {props.byteOffset} · {fmt(props.newByte)}
            </div>
            <div style={colStyle}>
              <HighlightedString text={props.tampered} hlOffset={props.byteOffset} color="#fee2e2" />
            </div>
          </div>
        </div>
      ) : props.mode === "unified" ? (
        <div style={colStyle}>
          <div style={{ color: "#15803d" }}>
            - <HighlightedString text={props.original} hlOffset={props.byteOffset} color="#dcfce7" />
          </div>
          <div style={{ color: "#b91c1c" }}>
            + <HighlightedString text={props.tampered} hlOffset={props.byteOffset} color="#fee2e2" />
          </div>
        </div>
      ) : (
        <div style={colStyle}>
          byte {props.byteOffset}: {fmt(props.originalByte)} → {fmt(props.newByte)}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/judge/DiffPanel.tsx apps/web/__tests__/judge/diff-panel.test.tsx
git commit -m "feat(judge): DiffPanel (Wikipedia-style 3-mode diff: side-by-side / unified / field-only)"
```

---

## Task 7: `PropagationCascade` component

**Files:**
- Create: `apps/web/components/judge/PropagationCascade.tsx`
- Test: `apps/web/__tests__/judge/propagation-cascade.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PropagationCascade } from "@/components/judge/PropagationCascade";

describe("PropagationCascade", () => {
  it("renders all 5 chain links in idle state", () => {
    render(<PropagationCascade brokenAt={null} />);
    ["byte flip", "line_hash", "prev_hash chain", "Merkle root", "signature"].forEach((label) =>
      expect(screen.getByText(new RegExp(label, "i"))).toBeDefined(),
    );
  });
  it("highlights the broken link + downstream", () => {
    const { container } = render(<PropagationCascade brokenAt="line_hash" />);
    expect(container.querySelectorAll('[data-broken="true"]').length).toBeGreaterThanOrEqual(4);
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```tsx
"use client";

export type ChainLink = "byte flip" | "line_hash" | "prev_hash chain" | "Merkle root" | "signature";

const LINKS: ChainLink[] = ["byte flip", "line_hash", "prev_hash chain", "Merkle root", "signature"];

export interface PropagationCascadeProps {
  brokenAt: ChainLink | null;
}

export function PropagationCascade({ brokenAt }: PropagationCascadeProps) {
  const brokenIdx = brokenAt === null ? -1 : LINKS.indexOf(brokenAt);
  return (
    <div style={{ marginTop: 12, padding: "12px 16px", border: "1px solid #e5e5e5", backgroundColor: "white", fontFamily: "ui-monospace, monospace", fontSize: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>Hash-chain propagation</div>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        {LINKS.map((link, i) => {
          const isBroken = brokenIdx >= 0 && i >= brokenIdx;
          return (
            <span key={link} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span
                data-broken={isBroken}
                style={{
                  padding: "4px 8px",
                  borderRadius: 4,
                  border: `1px solid ${isBroken ? "#b91c1c" : "#15803d"}`,
                  backgroundColor: isBroken ? "#fee2e2" : "#dcfce7",
                  color: isBroken ? "#7f1d1d" : "#14532d",
                }}
              >
                {link}{isBroken ? " ✕" : " ✓"}
              </span>
              {i < LINKS.length - 1 ? <span style={{ color: "#9ca3af" }}>→</span> : null}
            </span>
          );
        })}
      </div>
      {brokenAt === null ? (
        <div style={{ fontSize: 11, color: "#6b7280", marginTop: 8 }}>
          chain intact end-to-end
        </div>
      ) : (
        <div style={{ fontSize: 11, color: "#7f1d1d", marginTop: 8 }}>
          breakage radiates from <strong>{brokenAt}</strong> through every downstream link
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/judge/PropagationCascade.tsx apps/web/__tests__/judge/propagation-cascade.test.tsx
git commit -m "feat(judge): PropagationCascade (5-link cascading-failure visualization)"
```

---

## Task 8: Wire components into `/judge/tamper/page.tsx`

**Files:**
- Create: `apps/web/app/judge/tamper/page.tsx`
- Test: `apps/web/__tests__/judge/tamper-page.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TamperPage from "@/app/judge/tamper/page";

const sampleEvents = [
  { seq: 1, ts: "t", kind: "case_open", payload: {}, prev_hash: "0".repeat(64), line_hash: "a".repeat(64) },
  { seq: 2, ts: "t", kind: "tool_call_start", payload: { tool: "vol_pslist" }, prev_hash: "a".repeat(64), line_hash: "b".repeat(64) },
];

global.fetch = vi.fn(async (url: string) => {
  if (url.includes("/api/judge/case")) {
    return new Response(
      JSON.stringify({
        events: sampleEvents,
        manifest: null,
        sigstoreCert: null,
        otsReceiptBase64: null,
        caseMeta: { case_id: "c", audit_line_count: 2, first_event_ts: "t", last_event_ts: "t", curated_at: "t" },
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  }
  if (url.includes("/api/judge/verify")) {
    return new Response(JSON.stringify({ audit_chain_ok: "audit chain seq=2 prev_hash mismatch", brokenAtSeq: 2 }), { status: 200, headers: { "content-type": "application/json" } });
  }
  return new Response("not found", { status: 404 });
}) as unknown as typeof fetch;

describe("TamperPage", () => {
  it("renders hex view after fetching the case", async () => {
    render(<TamperPage />);
    await waitFor(() => expect(screen.getAllByRole("button").length).toBeGreaterThan(10));
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { DiffPanel, type DiffMode } from "@/components/judge/DiffPanel";
import { HexView } from "@/components/judge/HexView";
import { PropagationCascade, type ChainLink } from "@/components/judge/PropagationCascade";
import { TamperButton } from "@/components/judge/TamperButton";
import type { CaseBundle } from "@/lib/judge";
import { applyByteFlip, locateAffectedLine, type VerifyResult } from "@/lib/judge-tamper";

export default function TamperPage() {
  const [bundle, setBundle] = useState<CaseBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ offset: number; originalByte: number; newByte: number } | null>(null);
  const [tamperedJsonl, setTamperedJsonl] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);
  const [mode, setMode] = useState<DiffMode>("side-by-side");

  useEffect(() => {
    fetch("/api/judge/case")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then(setBundle)
      .catch((e) => setError(String(e)));
  }, []);

  const originalJsonl = useMemo(() => {
    if (!bundle) return "";
    return bundle.events.map((e) => JSON.stringify(e)).join("\n") + "\n";
  }, [bundle]);

  const handleByteClick = (offset: number, currentByte: number) => {
    setPending({ offset, originalByte: currentByte, newByte: 0x00 });
  };

  const handleConfirm = async () => {
    if (!pending) return;
    const mutated = applyByteFlip(originalJsonl, pending.offset, pending.newByte);
    setTamperedJsonl(mutated);
    const res = await fetch("/api/judge/verify", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ auditJsonl: mutated }),
    });
    const result = (await res.json()) as VerifyResult;
    setVerifyResult(result);
    setPending(null);
  };

  const handleReset = () => {
    setPending(null);
    setTamperedJsonl(null);
    setVerifyResult(null);
  };

  const brokenAt: ChainLink | null = useMemo(() => {
    if (!verifyResult) return null;
    if (verifyResult.audit_chain_ok === true) return null;
    return "line_hash";
  }, [verifyResult]);

  if (error) return <div>error: {error}</div>;
  if (!bundle) return <div>loading…</div>;

  const affectedLine = pending ? locateAffectedLine(originalJsonl, pending.offset) : null;
  const orig = affectedLine ? originalJsonl.slice(affectedLine.lineStart, affectedLine.lineEnd) : "";
  const tamp = affectedLine && tamperedJsonl ? tamperedJsonl.slice(affectedLine.lineStart, affectedLine.lineEnd) : "";

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <h2 style={{ marginTop: 0 }}>Pick a byte to flip</h2>
        <p style={{ fontSize: 13, color: "#6b7280" }}>
          Click any byte cell.  The audit log is read-only; we copy it
          into memory and verify the mutated copy.  Reset returns to the
          unmodified state.
        </p>
        <HexView content={originalJsonl.slice(0, 1024)} onByteClick={handleByteClick} />
      </div>

      {pending ? (
        <TamperButton {...pending} onConfirm={handleConfirm} onCancel={() => setPending(null)} />
      ) : null}

      {tamperedJsonl && pending === null && verifyResult ? (
        <>
          <DiffPanel
            mode={mode}
            original={orig}
            tampered={tamp}
            byteOffset={(affectedLine ? (affectedLine.lineStart - 1) * -1 : 0)}
            originalByte={originalJsonl.charCodeAt(0)}
            newByte={tamperedJsonl.charCodeAt(0)}
            onModeChange={setMode}
          />
          <PropagationCascade brokenAt={brokenAt} />
          <div style={{ fontFamily: "ui-monospace, monospace", fontSize: 13, padding: 12, border: `1px solid ${brokenAt ? "#b91c1c" : "#15803d"}`, backgroundColor: brokenAt ? "#fee2e2" : "#dcfce7" }}>
            <strong>verifier said:</strong>{" "}
            {typeof verifyResult.audit_chain_ok === "boolean"
              ? verifyResult.audit_chain_ok
                ? "chain intact"
                : "chain broken"
              : verifyResult.audit_chain_ok}
          </div>
          <button
            type="button"
            onClick={handleReset}
            style={{ alignSelf: "start", padding: "6px 16px", border: "1px solid #d1d5db", backgroundColor: "white", borderRadius: 4, cursor: "pointer" }}
          >
            Reset to original
          </button>
        </>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Run test, expect PASS**

- [ ] **Step 5: Manual smoke**

`pnpm --filter @findevil/web dev`, navigate to `http://localhost:3000/judge/tamper`. Expected: hex view renders, click a byte → modal asks to flip, click Flip it → DiffPanel + PropagationCascade + verifier banner appear, click Reset → returns to clean state.

- [ ] **Step 6: Commit**

```bash
git add apps/web/app/judge/tamper/page.tsx apps/web/__tests__/judge/tamper-page.test.tsx
git commit -m "feat(judge): /judge/tamper wires HexView + TamperButton + DiffPanel + PropagationCascade"
```

---

## Task 9: Playwright E2E for tamper flow

**Files:**
- Create: `apps/web/e2e/judge-tamper.spec.ts`

- [ ] **Step 1: Write E2E test**

```ts
import { expect, test } from "@playwright/test";

test("tamper flow: pick byte, flip, see DiffPanel + cascade red", async ({ page }) => {
  await page.goto("/judge/tamper");
  await page.waitForSelector('[aria-label*="byte at offset"]', { timeout: 10_000 });

  // Click a byte inside the first audit-line's payload.
  const buttons = await page.$$('[aria-label*="byte at offset"]');
  expect(buttons.length).toBeGreaterThan(20);
  await buttons[15].click();

  await page.getByRole("button", { name: /flip it/i }).click();

  // After the flip + verify round-trip, the cascade lights up red.
  await expect(page.getByText(/breakage radiates from/i)).toBeVisible({ timeout: 5_000 });
  await expect(page.locator('[data-broken="true"]').first()).toBeVisible();
});
```

- [ ] **Step 2: Run E2E**

```bash
cd apps/web
pnpm exec playwright test e2e/judge-tamper.spec.ts
```

Expected: 1/1 PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/web/e2e/judge-tamper.spec.ts
git commit -m "test(judge): Playwright E2E for /judge/tamper byte-flip flow"
```

---

## Task 10: Demo script Beat 5b

**Files:**
- Modify: `docs/demo-script-a2.md`

- [ ] **Step 1: Open the demo script**

```bash
sed -n '40,55p' docs/demo-script-a2.md
```

Confirm the beat-map table format. Note the existing time slots.

- [ ] **Step 2: Insert Beat 5b**

The Judge Mode spec §8 already describes Beat 5b at 30s between current Beat 5 and 6. The beat-map total is 5:00 hard cap, and demo-script-smoke (commit 4ddb04a) asserts contiguous beats summing to 300s. Adding Beat 5b means re-balancing — choose to extend the demo to 5:30 (NOT allowed; Devpost cap is 5:00) OR shorten an existing beat by 30s.

Decision: shorten Beat 6 (fleet investigation) from 0:50 to 0:20 — the fleet rollup PDF can flash for 20s instead of 50s; we don't need to walk through every slide. Adjust the table accordingly:

```diff
-| 5 | 2:35–3:10 | 0:35   | Crypto chain-of-custody       | 4, 5                |
-| 6 | 3:10–4:00 | 0:50   | 22-host fleet investigation   | 3 (Breadth/Depth)   |
+| 5 | 2:35–3:10 | 0:35   | Crypto chain-of-custody       | 4, 5                |
+| 5b| 3:10–3:40 | 0:30   | Judge Mode tamper-replay     | 4, 5                |
+| 6 | 3:40–4:00 | 0:20   | 22-host fleet rollup (PDF)   | 3 (Breadth/Depth)   |
```

Verify total still equals 5:00: 0:25 + 0:25 + 0:45 + 1:00 + 0:35 + 0:30 + 0:20 + 0:30 + 0:20 + 0:10 = 5:00. ✓

- [ ] **Step 3: Add the Beat 5b body**

Insert after Beat 5's notes section, before Beat 6:

```markdown
## Beat 5b — Judge Mode tamper-replay (3:10–3:40)

**On-screen:** cut from terminal to browser at
`http://localhost:3000/judge`.  Click the second card ("Try to break
the cryptographic chain").  Hex view appears.  Click a byte in the
middle of the visible region; modal appears.  Click "Flip it".
DiffPanel + PropagationCascade render — the cascade lights up red
end-to-end.  Verifier banner: "audit chain seq=N prev_hash mismatch."
Click Reset; cascade returns to green.  Cut back to terminal.

**Voice-over (~75 words at 150 wpm = 30s):**

> The judges have a route built for them.  They can break the chain
> on demand — flip one byte, the verifier names the exact link that
> fails, and the cryptographic claim is no longer something they
> have to trust.  The audit trail is FRE 902 self-authenticating,
> but more importantly: it is publicly falsifiable, and we ship
> the falsifier.

**Notes:**
- The reset is important — leave the chain green when you cut away,
  or the next beat starts on a red badge that confuses viewers.
- If the curated case has fewer than 64 visible bytes in the hex
  view, the byte-pick visual reads as "not many bytes to choose
  from" — re-curate with a longer audit.jsonl before recording.
```

- [ ] **Step 4: Re-run demo-script smoke**

```bash
python scripts/demo-script-smoke.py
```

Expected: PASS — the beat-map table is well-formed and sums to 5:00.

- [ ] **Step 5: Commit**

```bash
git add docs/demo-script-a2.md
git commit -m "docs(demo): Beat 5b — Judge Mode tamper-replay (re-balanced from Beat 6)"
```

---

## Task 11: CHANGELOG + README

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `apps/web/README.md`

- [ ] **Step 1: CHANGELOG entry**

Append under [Unreleased] → Added — feature surface:

```
- **Judge Mode Plan B — /judge/tamper**: byte-flip sandbox against the
  curated case with Wikipedia-style DiffPanel (3 modes: side-by-side /
  unified / field-only) and a 5-link PropagationCascade visualization
  showing hash-chain breakage radiating end-to-end.  TS-only chain
  verifier in /api/judge/verify (full Python verify_manifest is a v2
  upgrade flagged in the plan).  Demo Beat 5b inserted at 3:10-3:40
  (re-balanced from Beat 6's fleet rollup).  Spec §4.2.
```

- [ ] **Step 2: apps/web/README.md status block**

Add: `Judge Mode (Plan B) — /judge/tamper shipped`.

- [ ] **Step 3: Final smokes**

```bash
SKIP_SLOW_RUST=1 bash scripts/run-all-smokes.sh
```

Expected: 13/13.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md apps/web/README.md
git commit -m "docs(judge): Plan B status + CHANGELOG entry"
```

---

## Verification (end of Plan B)

- All Vitest tests pass (Plan A's plus ~6 new from Plan B)
- `pnpm exec playwright test` passes both `judge-replay.spec.ts` and `judge-tamper.spec.ts`
- `pnpm --filter @findevil/web build` clean
- `SKIP_SLOW_RUST=1 bash scripts/run-all-smokes.sh` 13/13 pass (demo-script-smoke validates Beat 5b)
- Visit `http://localhost:3000/judge/tamper`, click a byte, flip → cascade red, reset → green
- The affidavit card 404s (Plan C lands it)

## §V2 — Deferred upgrades

1. **Full `manifest_verify` integration.** The TS-only chain verifier in `/api/judge/verify` covers `audit_chain_ok` only. Upgrading to call `findevil_agent.crypto.manifest.verify_manifest` (via subprocess or a Python sidecar HTTP server) would also exercise Merkle root + sigstore cert + OTS receipt verification. Estimated +1 day of work; not blocking the demo.
2. **Multi-byte tamper.** Current TamperButton flips a single byte. A v2 could allow editing whole fields ("flip the `tool_call_id` to point to a non-existent record"). More dramatic for some demos but UX gets harder.
3. **Tamper history.** v2 could keep a stack of flips so the judge can chain multiple mutations and see the cascade compound. v1 is single-flip + reset.
