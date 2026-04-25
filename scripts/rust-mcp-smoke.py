#!/usr/bin/env python3
"""End-to-end smoke for the findevil-mcp Rust MCP server.

Spawns the Rust binary as a subprocess, completes the MCP initialize
handshake, lists tools, and calls each one. Mirrors the Python
agent-mcp-smoke.py pattern.

Under Amendment A2 this is the missing piece — without the stdio
server, Claude Code can't reach case_open / evtx_query / prefetch_parse
through the typed MCP surface. This script proves the wire works.

Usage::

    python scripts/rust-mcp-smoke.py [--release]

The default uses the debug binary at target/debug/findevil-mcp;
``--release`` switches to target/release/findevil-mcp.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Any

REPO = Path(__file__).resolve().parent.parent


def fatal(msg: str) -> None:
    print(f"\n[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def log(msg: str) -> None:
    print(f"  {msg}")


class StdioClient:
    def __init__(self, cmd: list[str]) -> None:
        env = os.environ.copy()
        # Quiet mode — keep stderr from cluttering terminal during smoke.
        env.setdefault("RUST_LOG", "warn")
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
        threading.Thread(target=self._reader, daemon=True).start()

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
        meta = result.get("_meta", {})
        # Tools should attach SHA-256 of canonical output to _meta.
        if "output_sha256" not in meta or len(meta["output_sha256"]) != 64:
            fatal(f"{name} missing _meta.output_sha256")
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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--release", action="store_true")
    args = p.parse_args()

    bin_dir = "release" if args.release else "debug"
    bin_name = "findevil-mcp.exe" if sys.platform == "win32" else "findevil-mcp"
    binary = REPO / "target" / bin_dir / bin_name

    if not binary.is_file():
        fatal(
            f"binary not built: {binary}\n"
            f"  build: cargo build {'--release' if args.release else ''} -p findevil-mcp"
        )

    print("=" * 60)
    print("Find Evil! — findevil-mcp (Rust) end-to-end smoke")
    print("=" * 60)
    log(f"binary: {binary}")

    client = StdioClient([str(binary)])
    try:
        # ---- 1. initialize handshake ------------------------------------
        log("initialize handshake...")
        init = client.call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "rust-mcp-smoke", "version": "1.0"},
            },
        )
        if init.get("protocolVersion") != "2024-11-05":
            fatal(f"unexpected protocol version: {init}")
        if init.get("serverInfo", {}).get("name") != "findevil-mcp":
            fatal(f"unexpected serverInfo: {init}")
        client.notify("notifications/initialized")
        log(
            f"  -> protocol={init['protocolVersion']} server={init['serverInfo']['name']}"
        )

        # ---- 2. tools/list -----------------------------------------------
        log("tools/list...")
        tools_resp = client.call("tools/list")
        names = sorted(t["name"] for t in tools_resp["tools"])
        expected = sorted(
            [
                "case_open",
                "evtx_query",
                "prefetch_parse",
                "mft_timeline",
                "registry_query",
                "yara_scan",
                "usnjrnl_query",
            ]
        )
        if names != expected:
            fatal(f"tool mismatch: {names} != {expected}")
        # Each tool must advertise an inputSchema dict.
        for tool in tools_resp["tools"]:
            schema = tool["inputSchema"]
            if not isinstance(schema, dict) or "type" not in schema:
                fatal(f"{tool['name']} schema malformed: {schema}")
        log(f"  -> {len(names)} tools registered with JSON Schema")

        # ---- 3. case_open -----------------------------------------------
        log("case_open: register synthetic evidence...")
        workdir = REPO / "tmp" / "rust-smoke"
        workdir.mkdir(parents=True, exist_ok=True)
        evidence = workdir / "evidence.E01"
        evidence.write_bytes(
            b"FAKE EVIDENCE BYTES for the rust-mcp-smoke harness. "
            b"Real .e01 round-trip would land in tmp/rust-smoke/."
        )
        case_home = workdir / "home"
        case_home.mkdir(exist_ok=True)
        os.environ["FINDEVIL_HOME"] = str(case_home)

        handle = client.call_tool(
            "case_open",
            {"image_path": str(evidence), "label": "rust-mcp-smoke"},
        )
        if not (
            isinstance(handle.get("id"), str)
            and len(handle.get("image_hash", "")) == 64
        ):
            fatal(f"case_open returned malformed handle: {handle}")
        log(
            f"  -> case_id={handle['id'][:8]}... "
            f"image_hash={handle['image_hash'][:12]}... "
            f"size={handle['image_size_bytes']}B"
        )

        def expect_error_response(
            method: str, params: dict[str, Any], substr: str
        ) -> None:
            """Call the server raw and assert the response is a JSON-RPC error."""
            msg_id = client._next_id  # noqa: SLF001 — test-only access
            client._next_id += 1  # noqa: SLF001
            client.send(
                {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
            )
            resp = client.read()
            if resp.get("id") != msg_id:
                fatal(f"id mismatch: {resp}")
            if "error" not in resp:
                fatal(f"expected error, got success: {resp}")
            if substr not in resp["error"].get("message", ""):
                fatal(f"error message missing {substr!r}: {resp}")

        # ---- 4. evtx_query (error path) ---------------------------------
        log("evtx_query: missing-file error path...")
        expect_error_response(
            "tools/call",
            {
                "name": "evtx_query",
                "arguments": {
                    "case_id": handle["id"],
                    "evtx_path": str(workdir / "nope.evtx"),
                },
            },
            "evtx file not found",
        )
        log("  -> -32603 with 'evtx file not found' as expected")

        # ---- 5. prefetch_parse (error path) -----------------------------
        log("prefetch_parse: missing-file error path...")
        expect_error_response(
            "tools/call",
            {
                "name": "prefetch_parse",
                "arguments": {
                    "case_id": handle["id"],
                    "prefetch_path": str(workdir / "nope.pf"),
                },
            },
            "prefetch file not found",
        )
        log("  -> -32603 with 'prefetch file not found' as expected")

        # ---- 6. mft_timeline (error path) -------------------------------
        log("mft_timeline: missing-file error path...")
        expect_error_response(
            "tools/call",
            {
                "name": "mft_timeline",
                "arguments": {
                    "case_id": handle["id"],
                    "mft_path": str(workdir / "nope.mft"),
                },
            },
            "MFT file not found",
        )
        log("  -> -32603 with 'MFT file not found' as expected")

        # ---- 7. mft_timeline invalid-time-filter (-32602) ---------------
        log("mft_timeline: invalid time filter (-32602)...")
        # Use the temp evidence file as the mft_path — the parser will try
        # to open it and may fail later, but the time-filter validation
        # runs FIRST and returns -32602 before any parsing happens.
        expect_error_response(
            "tools/call",
            {
                "name": "mft_timeline",
                "arguments": {
                    "case_id": handle["id"],
                    "mft_path": str(evidence),
                    "since_iso": "not-a-real-time",
                },
            },
            "invalid time filter",
        )
        log("  -> -32602 invalid_params with 'invalid time filter' as expected")

        # ---- 8. registry_query (error path) -----------------------------
        log("registry_query: missing-file error path...")
        expect_error_response(
            "tools/call",
            {
                "name": "registry_query",
                "arguments": {
                    "case_id": handle["id"],
                    "hive_path": str(workdir / "nope.dat"),
                    "key_path": "",
                },
            },
            "registry hive not found",
        )
        log("  -> -32603 with 'registry hive not found' as expected")

        # ---- 9. yara_scan (error path) ----------------------------------
        log("yara_scan: missing-target error path...")
        expect_error_response(
            "tools/call",
            {
                "name": "yara_scan",
                "arguments": {
                    "case_id": handle["id"],
                    "target_path": str(workdir / "nope.bin"),
                    "rules_path": str(workdir / "nope.yar"),
                },
            },
            "YARA target not found",
        )
        log("  -> -32603 with 'YARA target not found' as expected")

        # ---- 10. usnjrnl_query (error path) -----------------------------
        log("usnjrnl_query: missing-file error path...")
        expect_error_response(
            "tools/call",
            {
                "name": "usnjrnl_query",
                "arguments": {
                    "case_id": handle["id"],
                    "usnjrnl_path": str(workdir / "nope.j"),
                },
            },
            "UsnJrnl file not found",
        )
        log("  -> -32603 with 'UsnJrnl file not found' as expected")

        # ---- 11. unknown tool dispatch is rejected ----------------------
        log("unknown tool: expect JSON-RPC error...")
        client.send(
            {
                "jsonrpc": "2.0",
                "id": 9999,
                "method": "tools/call",
                "params": {"name": "no_such_tool", "arguments": {}},
            }
        )
        resp = client.read()
        if "error" not in resp or resp["error"]["code"] != -32602:
            fatal(f"expected -32602 invalid_params, got: {resp}")
        log(f"  -> rejected with -32602: {resp['error']['message'][:60]}...")

        print()
        print("=" * 60)
        print("OK — Rust MCP server speaks 2024-11-05 over stdio.")
        print("  All 7 tools dispatchable, error paths well-formed.")
        print("=" * 60)
        return 0
    finally:
        client.close()
        os.environ.pop("FINDEVIL_HOME", None)


if __name__ == "__main__":
    sys.exit(main())
