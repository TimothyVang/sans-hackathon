// Phase 5 sprite-state derivation unit tests — Amendment A3 §1.2.
//
// These cover the *logic* of `deriveRoleStates`, not React rendering.
// The sprite components themselves are placeholder visuals about to
// be replaced by the Claude Design pass; locking their JSX into
// component-render tests now would be premature.

import { describe, expect, it } from "vitest";

import type { AuditLine } from "@/lib/audit-tail";
import { deriveRoleStates } from "@/lib/sprite-state";

function line(
  seq: number,
  kind: string,
  payload: Record<string, unknown>,
): AuditLine {
  return {
    seq,
    kind,
    ts: "2026-04-27T01:00:00Z",
    payload,
    line_hash: "deadbeef".padEnd(64, "0").slice(0, 64),
    raw_line: JSON.stringify({ seq, kind, payload }),
  };
}

describe("deriveRoleStates", () => {
  it("returns all-idle for an empty event log", () => {
    const states = deriveRoleStates([]);
    expect(states).toEqual({
      pool_a: "idle",
      pool_b: "idle",
      verifier: "idle",
      judge: "idle",
      correlator: "idle",
    });
  });

  it("flips Pool A to 'working' on a tool_call_start with pool='A'", () => {
    const states = deriveRoleStates([
      line(0, "tool_call_start", {
        tool_name: "evtx_query",
        tool_call_id: "tc-1",
        pool: "A",
      }),
    ]);
    expect(states.pool_a).toBe("working");
    expect(states.pool_b).toBe("idle");
  });

  it("flips both pools to 'working' on a tool_call_start with no pool field (shared probe)", () => {
    const states = deriveRoleStates([
      line(0, "tool_call_start", {
        tool_name: "case_open",
        tool_call_id: "tc-shared",
      }),
    ]);
    expect(states.pool_a).toBe("working");
    expect(states.pool_b).toBe("working");
  });

  it("flips Pool B to 'verdict' on a finding_approved with pool_origin='B'", () => {
    const states = deriveRoleStates([
      line(0, "finding_approved", {
        finding_id: "f-B-1",
        pool_origin: "B",
        confidence: "CONFIRMED",
      }),
    ]);
    expect(states.pool_b).toBe("verdict");
    expect(states.pool_a).toBe("idle");
  });

  it("verifier→judge handoff sets verifier='verdict' and judge='waiting'", () => {
    const states = deriveRoleStates([
      line(0, "acp_handoff", {
        from_role: "verifier",
        to_role: "judge",
        payload: { finding_id: "f-1", action: "approved" },
      }),
    ]);
    expect(states.verifier).toBe("verdict");
    expect(states.judge).toBe("waiting");
    expect(states.correlator).toBe("idle");
  });

  it("judge→correlator handoff sets judge='verdict' and correlator='waiting'", () => {
    const states = deriveRoleStates([
      line(0, "acp_handoff", {
        from_role: "judge",
        to_role: "correlator",
        payload: { finding_count: 3 },
      }),
    ]);
    expect(states.judge).toBe("verdict");
    expect(states.correlator).toBe("waiting");
  });

  it("later events override earlier ones for the same role", () => {
    // Pool A working → then Pool A approved finding → 'verdict' wins.
    const states = deriveRoleStates([
      line(0, "tool_call_start", {
        tool_name: "registry_query",
        tool_call_id: "tc-A1",
        pool: "A",
      }),
      line(1, "finding_approved", {
        finding_id: "f-A-1",
        pool_origin: "A",
        confidence: "CONFIRMED",
      }),
    ]);
    expect(states.pool_a).toBe("verdict");
  });

  it("ignores bookkeeping kinds (judge_selfscore, chain_update, …)", () => {
    const states = deriveRoleStates([
      line(0, "judge_selfscore", { criterion: "audit_trail", score: 5 }),
      line(1, "chain_update", { merkle_root: "abc", leaf_count: 3 }),
    ]);
    // Nothing in this stream drives a transition; everyone stays idle.
    expect(states).toEqual({
      pool_a: "idle",
      pool_b: "idle",
      verifier: "idle",
      judge: "idle",
      correlator: "idle",
    });
  });
});
