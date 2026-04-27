// Integration test: audit-tail.ts against a real on-disk audit.jsonl
// that gets appended to mid-test. Per A3 plan Task 4.2.

import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { tailAuditLog, type AuditLine } from "@/lib/audit-tail";

let tmpDir: string;

beforeEach(async () => {
  tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "audit-tail-"));
});

afterEach(async () => {
  await fs.rm(tmpDir, { recursive: true, force: true });
});

function lineFor(seq: number, kind: string, payload: object): string {
  return JSON.stringify({
    seq,
    kind,
    ts: "2026-04-27T01:00:00Z",
    payload,
    line_hash:
      "deadbeef".padEnd(64, "0").slice(0, 64),
    prev_hash:
      "00000000".padEnd(64, "0").slice(0, 64),
  });
}

describe("tailAuditLog", () => {
  it("yields existing lines on initial drain", async () => {
    const auditPath = path.join(tmpDir, "audit.jsonl");
    await fs.writeFile(
      auditPath,
      [
        lineFor(0, "agent_message", { role: "supervisor", content: "go" }),
        lineFor(1, "tool_call_start", { tool_call_id: "tc-1" }),
      ].join("\n") + "\n",
      "utf-8",
    );

    const ac = new AbortController();
    const collected: AuditLine[] = [];
    const iter = tailAuditLog(auditPath, ac.signal);

    for (let i = 0; i < 2; i++) {
      const next = await iter.next();
      if (next.done) break;
      collected.push(next.value);
    }
    ac.abort();
    // Drain the generator so the watcher cleanly closes.
    await iter.next();

    expect(collected).toHaveLength(2);
    expect(collected[0].seq).toBe(0);
    expect(collected[0].kind).toBe("agent_message");
    expect(collected[1].seq).toBe(1);
    expect(collected[1].kind).toBe("tool_call_start");
  });

  it("yields a line appended after the consumer is already listening", async () => {
    const auditPath = path.join(tmpDir, "audit.jsonl");
    // Pre-create empty so chokidar starts watching immediately.
    await fs.writeFile(auditPath, "", "utf-8");

    const ac = new AbortController();
    const iter = tailAuditLog(auditPath, ac.signal);

    // Kick the consumer first; it'll await the next line.
    const nextPromise = iter.next();

    // Give chokidar a tick to attach to the file before we append.
    await new Promise((r) => setTimeout(r, 100));

    await fs.appendFile(
      auditPath,
      lineFor(0, "finding_approved", { finding_id: "f-A-1" }) + "\n",
      "utf-8",
    );

    // Race the result against a 1500ms timeout — chokidar fires fast
    // but Windows fs.watch can lag on the first event.
    type RaceResult = { value: AuditLine | undefined; timed_out: boolean };
    const winner: RaceResult = await Promise.race<RaceResult>([
      nextPromise.then(
        (r): RaceResult => ({
          // r.value is AuditLine | void (void when r.done === true);
          // narrow to AuditLine | undefined for the assertion below.
          value: r.done ? undefined : r.value,
          timed_out: false,
        }),
      ),
      new Promise<RaceResult>((r) =>
        setTimeout(() => r({ value: undefined, timed_out: true }), 1500),
      ),
    ]);

    ac.abort();
    await iter.next();

    expect(winner.timed_out).toBe(false);
    expect(winner.value).toBeDefined();
    expect(winner.value?.seq).toBe(0);
    expect(winner.value?.kind).toBe("finding_approved");
  });

  it("skips malformed JSON lines without aborting the stream", async () => {
    const auditPath = path.join(tmpDir, "audit.jsonl");
    await fs.writeFile(
      auditPath,
      [
        lineFor(0, "agent_message", { content: "first" }),
        "this is not json",
        lineFor(1, "agent_message", { content: "second" }),
      ].join("\n") + "\n",
      "utf-8",
    );

    const ac = new AbortController();
    const iter = tailAuditLog(auditPath, ac.signal);
    const collected: AuditLine[] = [];
    for (let i = 0; i < 2; i++) {
      const next = await iter.next();
      if (next.done) break;
      collected.push(next.value);
    }
    ac.abort();
    await iter.next().catch(() => undefined);

    expect(collected).toHaveLength(2);
    expect(collected[0].payload).toEqual({ content: "first" });
    expect(collected[1].payload).toEqual({ content: "second" });
  });
});
