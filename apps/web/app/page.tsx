// Placeholder dashboard — Phase 4 Task 4.1 scaffold. Subsequent PRs
// add: WebSocket / SSE audit-log tail (4.2), pydantic-to-typescript
// codegen (4.3), the 5 sprite components (5.1-5.5), and the
// AuditBeadString + HashChainBadge + FindingChip chrome (6.1-6.3).
// See docs/superpowers/plans/2026-04-26-amendment-a3-plan.md.

export default function DashboardPage() {
  return (
    <main className="min-h-screen p-8">
      <div className="nes-container with-title is-centered max-w-3xl mx-auto">
        <p className="title">Find Evil!</p>
        <p>
          Dashboard scaffold — Amendment A3 §1.2 (<code>apps/web/</code>{" "}
          un-deferral).
        </p>
        <p className="mt-4 text-sm">
          The five sprites (Pool A, Pool B, Verifier, Judge, Correlator) and
          the audit-chain bead-string land in subsequent PRs.
        </p>
        <p className="mt-4 text-sm">
          Append <code>?case=&lt;absolute-case-dir&gt;</code> to the URL to
          point this dashboard at a specific case&apos;s{" "}
          <code>audit.jsonl</code> (live tail wires up in 4.2).
        </p>
      </div>

      <div className="nes-container with-title is-rounded max-w-3xl mx-auto mt-8">
        <p className="title">Status</p>
        <ul className="nes-list is-disc">
          <li>Next.js 15 + React 19 ✓</li>
          <li>Tailwind v4 (CSS-first config) ✓</li>
          <li>NES.css component library ✓</li>
          <li>
            SSE audit-log tail —{" "}
            <a href="/debug" className="nes-text is-primary">
              /debug stream viewer
            </a>{" "}
            (raw events, dev/QA only)
          </li>
          <li>Audit event-type codegen — pending PR (Task 4.3)</li>
          <li>5 sprite components — pending Claude Design pass (Phase 5)</li>
          <li>
            AuditBeadString + HashChainBadge + FindingChip — pending Claude
            Design pass (Phase 6)
          </li>
        </ul>
      </div>
    </main>
  );
}
