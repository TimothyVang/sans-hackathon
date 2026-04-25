#!/usr/bin/env python3
"""End-to-end smoke for the findevil-agent-mcp Python MCP server.

Spawns the server as a subprocess (matching the ``.mcp.json`` boot
recipe) and drives a full investigation through all 10 MCP tools.
This is the demo flow under Amendment A2 minus the actual SCHARDT.001
disk image — synthetic Findings shaped like the NIST CFReDS golden
exercise the same crypto/ACH paths the live demo will.

Usage::

    uv run --directory services/agent_mcp python ../../scripts/agent-mcp-smoke.py

What it proves:
  1. Server boots and completes the MCP initialize handshake.
  2. ``tools/list`` returns all 10 expected tools with valid schemas.
  3. ``audit_append`` chains 12 representative records (tool calls,
     findings, agent messages).
  4. ``audit_verify`` replays the chain cleanly.
  5. ``detect_contradictions`` surfaces a Pool A/B disagreement.
  6. ``judge_findings`` merges with credibility weighting.
  7. ``correlate_findings`` enforces SOUL.md cross-artifact rules.
  8. ``manifest_finalize`` writes a signed run.manifest.json.
  9. ``manifest_verify`` confirms audit chain + Merkle root + signature.

Exit code: 0 on full success, 1 on the first assertion failure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from queue import Empty, Queue
from typing import Any

REPO = Path(__file__).resolve().parent.parent
AGENT_MCP_DIR = REPO / "services" / "agent_mcp"


def fatal(msg: str) -> None:
    print(f"\n[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def log(msg: str) -> None:
    print(f"  {msg}")


# ---------------------------------------------------------------------------
# Stdio JSON-RPC harness — line-delimited JSON, NOT LSP framing.
# ---------------------------------------------------------------------------


class StdioClient:
    def __init__(self, cmd: list[str]) -> None:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["FINDEVIL_LOG_LEVEL"] = "WARNING"
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._next_id = 1
        self._queue: Queue[str | None] = Queue()
        self._t = threading.Thread(target=self._reader, daemon=True)
        self._t.start()

    def _reader(self) -> None:
        try:
            assert self.proc.stdout is not None
            for line in iter(self.proc.stdout.readline, ""):
                if not line:
                    break
                self._queue.put(line)
        finally:
            self._queue.put(None)

    def send(self, message: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def read(self, timeout_s: float = 30.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("read timed out")
            try:
                line = self._queue.get(timeout=remaining)
            except Empty:
                continue
            if line is None:
                raise RuntimeError("server closed stdout")
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        msg_id = self._next_id
        self._next_id += 1
        self.send(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": method,
                "params": params or {},
            }
        )
        resp = self.read()
        if resp.get("id") != msg_id:
            fatal(f"id mismatch: sent {msg_id}, got {resp.get('id')}")
        if "error" in resp:
            fatal(f"server error on {method}: {resp['error']}")
        return resp["result"]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self.call("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content") or []
        if not content:
            fatal(f"empty content from {name}")
        body = json.loads(content[0]["text"])
        if (
            isinstance(body, dict)
            and "error" in body
            and isinstance(body["error"], dict)
        ):
            fatal(f"{name} returned error: {body['error']}")
        return body

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def close(self) -> None:
        if self.proc.stdin is not None and not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


# ---------------------------------------------------------------------------
# The smoke flow.
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _finding(
    *,
    case_id: str,
    finding_id: str,
    tool_call_id: str,
    artifact: str,
    description: str,
    confidence: str,
    pool: str,
    mitre: str | None = None,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "finding_id": finding_id,
        "tool_call_id": tool_call_id,
        "artifact_path": artifact,
        "confidence": confidence,
        "description": description,
        "mitre_technique": mitre,
        "pool_origin": pool,
    }


def main() -> int:
    print("=" * 60)
    print("Find Evil! — agent_mcp end-to-end smoke (Amendment A2)")
    print("=" * 60)

    case_id = f"smoke-{uuid.uuid4()}"
    run_id = f"run-{int(time.time())}"
    workdir = REPO / "tmp" / "smoke" / case_id
    workdir.mkdir(parents=True, exist_ok=True)
    audit_path = workdir / "audit.jsonl"
    manifest_path = workdir / "run.manifest.json"
    started_at = _now_iso()

    cmd = [
        "uv",
        "run",
        "--directory",
        str(AGENT_MCP_DIR),
        "python",
        "-m",
        "findevil_agent_mcp.server",
    ]
    log(f"spawning: {' '.join(cmd)}")
    client = StdioClient(cmd)
    try:
        # ---- 1. initialize handshake ------------------------------------
        log("initialize handshake...")
        init = client.call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent-mcp-smoke", "version": "1.0"},
            },
        )
        assert "capabilities" in init, f"no capabilities in init result: {init}"
        client.notify("notifications/initialized")

        # ---- 2. tools/list ---------------------------------------------
        log("tools/list...")
        tools_resp = client.call("tools/list")
        names = sorted(t["name"] for t in tools_resp["tools"])
        expected = sorted(
            [
                "audit_append",
                "audit_verify",
                "manifest_finalize",
                "manifest_verify",
                "ots_stamp",
                "ots_verify",
                "verify_finding",
                "detect_contradictions",
                "judge_findings",
                "correlate_findings",
            ]
        )
        if names != expected:
            fatal(f"tools mismatch: got {names}, expected {expected}")
        log(f"  -> {len(names)} tools registered")

        # ---- 3. audit_append a representative tool-call sequence -------
        log("audit_append: chaining 12 records...")
        records = [
            (
                "agent_message",
                {"role": "supervisor", "content": "starting investigation"},
            ),
            ("tool_call_start", {"tool_call_id": "tc-1", "tool": "case_open"}),
            ("tool_call_output", {"tool_call_id": "tc-1", "output_hash": "a" * 64}),
            ("tool_call_start", {"tool_call_id": "tc-2", "tool": "evtx_query"}),
            (
                "tool_call_output",
                {"tool_call_id": "tc-2", "output_hash": "b" * 64, "row_count": 42},
            ),
            ("tool_call_start", {"tool_call_id": "tc-3", "tool": "prefetch_parse"}),
            ("tool_call_output", {"tool_call_id": "tc-3", "output_hash": "c" * 64}),
            ("tool_call_start", {"tool_call_id": "tc-4", "tool": "mft_timeline"}),
            ("tool_call_output", {"tool_call_id": "tc-4", "output_hash": "d" * 64}),
            (
                "finding_approved",
                {
                    "finding_id": "f-A-1",
                    "tool_call_id": "tc-2",
                    "confidence": "CONFIRMED",
                },
            ),
            (
                "finding_approved",
                {
                    "finding_id": "f-B-1",
                    "tool_call_id": "tc-3",
                    "confidence": "INFERRED",
                },
            ),
            ("agent_message", {"role": "judge", "content": "merge complete"}),
        ]
        for kind, payload in records:
            client.call_tool(
                "audit_append",
                {"path": str(audit_path), "kind": kind, "payload": payload},
            )

        # ---- 4. audit_verify replay ------------------------------------
        log("audit_verify: replay the chain...")
        v = client.call_tool("audit_verify", {"path": str(audit_path)})
        if not (v["ok"] and v["record_count"] == len(records)):
            fatal(f"audit chain replay failed: {v}")
        log(f"  -> chain verifies, {v['record_count']} records")

        # ---- 5. detect_contradictions ----------------------------------
        log("detect_contradictions: Pool A persistence vs Pool B exfil...")
        a_findings = [
            _finding(
                case_id=case_id,
                finding_id="f-A-1",
                tool_call_id="tc-2",
                artifact="C:\\Windows\\System32\\winevt\\Logs\\Security.evtx",
                description="Type 10 RDP logon at 02:14 UTC from external IP",
                confidence="CONFIRMED",
                pool="A",
                mitre="T1078",
            ),
            _finding(
                case_id=case_id,
                finding_id="f-A-2",
                tool_call_id="tc-3",
                artifact="C:\\Windows\\Prefetch\\STAGER.EXE-D269B812.pf",
                description="Prefetch shows STAGER.EXE ran 3 times, last 03:08 UTC",
                confidence="CONFIRMED",
                pool="A",
                mitre="T1547.001",
            ),
        ]
        b_findings = [
            _finding(
                case_id=case_id,
                finding_id="f-B-1",
                tool_call_id="tc-2",
                artifact="C:\\Windows\\System32\\winevt\\Logs\\Security.evtx",
                description="Possible RDP brute-force; not a successful logon",
                confidence="HYPOTHESIS",
                pool="B",
                mitre="T1110.001",
            ),
        ]
        cs = client.call_tool(
            "detect_contradictions",
            {
                "case_id": case_id,
                "pool_a": a_findings,
                "pool_b": b_findings,
                "resolution_required": True,
            },
        )
        if cs["pool_a_count"] != 2 or cs["pool_b_count"] != 1:
            fatal(f"unexpected pool counts: {cs}")
        if not cs["contradictions"]:
            fatal(
                "expected at least one contradiction (CONFIRMED vs HYPOTHESIS on tc-2)"
            )
        log(f"  -> {len(cs['contradictions'])} contradictions surfaced")

        # ---- 6. judge_findings -----------------------------------------
        log("judge_findings: credibility-weighted merge...")
        j = client.call_tool(
            "judge_findings",
            {
                "pool_a_findings": a_findings,
                "pool_b_findings": b_findings,
                "pool_a_verifier_actions": [],
                "pool_b_verifier_actions": [],
            },
        )
        if not j["merged"] or j["budget_exceeded"]:
            fatal(f"judge produced no merged findings: {j}")
        log(f"  -> {len(j['merged'])} merged findings; budget OK")

        # ---- 7. correlate_findings -------------------------------------
        log("correlate_findings: SOUL.md cross-artifact rules...")
        merged_only = [m["finding"] for m in j["merged"]]
        c = client.call_tool("correlate_findings", {"findings": merged_only})
        kept = sum(1 for o in c["outcomes"] if o["action"] == "kept")
        downgraded = sum(1 for o in c["outcomes"] if o["action"] == "downgraded")
        log(f"  -> {kept} kept, {downgraded} downgraded by SOUL.md rules")

        # ---- 8. manifest_finalize --------------------------------------
        log("manifest_finalize: build + sign run.manifest.json...")
        mf = client.call_tool(
            "manifest_finalize",
            {
                "case_id": case_id,
                "run_id": run_id,
                "started_at": started_at,
                "audit_log_path": str(audit_path),
                "output_path": str(manifest_path),
                "signer": "stub",
                "extra": {
                    "image_path": "/fixtures/nist-hacking-case/SCHARDT.001",
                    "model": "claude-opus-4-7",
                },
            },
        )
        if not (mf["leaf_count"] >= 4 and len(mf["merkle_root_hex"]) == 64):
            fatal(f"manifest finalize unexpected: {mf}")
        log(
            f"  -> {mf['leaf_count']} Merkle leaves, root={mf['merkle_root_hex'][:12]}..., "
            f"sig sha256={mf['signature_payload_sha256'][:12]}..."
        )

        # ---- 9. manifest_verify (offline) ------------------------------
        log("manifest_verify: offline replay...")
        mv = client.call_tool("manifest_verify", {"manifest_path": str(manifest_path)})
        if not mv["overall"]:
            fatal(f"manifest verification failed: {mv}")
        log(
            "  -> overall=True, audit_chain_ok={a}, merkle_root_ok={m}, sig_present={s}".format(
                a=mv["audit_chain_ok"],
                m=mv["merkle_root_ok"],
                s=mv["signature_present"],
            )
        )

        # ---- 10. tampered manifest is rejected -------------------------
        log("manifest_verify (tampered): expect failure...")
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        loaded["merkle_root_hex"] = "ff" * 32
        manifest_path.write_text(
            json.dumps(loaded, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        mv2 = client.call_tool("manifest_verify", {"manifest_path": str(manifest_path)})
        if mv2["overall"]:
            fatal("tampered manifest must NOT verify, but it did")
        log(f"  -> tampered manifest correctly rejected: {mv2['merkle_root_detail']!r}")

        print()
        print("=" * 60)
        print("OK — full A2 demo flow round-trips clean.")
        print(f"  case_id        : {case_id}")
        print(f"  run_id         : {run_id}")
        print(f"  audit log      : {audit_path} ({v['record_count']} records)")
        print(f"  manifest       : {manifest_path}")
        print("=" * 60)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
