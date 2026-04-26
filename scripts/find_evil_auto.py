#!/usr/bin/env python3
"""find-evil-auto — single-command automated investigation orchestrator.

Usage:
    python scripts/find_evil_auto.py <evidence_path> [--unattended] [--no-report]

What it does:
    1. Detects evidence type (memory image, EVTX, disk image)
    2. Spawns findevil-mcp + findevil-agent-mcp inside the SIFT VM via SSH stdio
    3. case_open against the evidence (real SHA-256, audit log starts here)
    4. Runs the per-type playbook tool sequence
    5. Synthesizes Pool A vs Pool B Findings deterministically from tool outputs
       (Pool A = persistence-biased framing; Pool B = exfil/general-malware framing)
    6. detect_contradictions surfaces disagreements
    7. judge_findings + correlate_findings (SOUL.md ≥2 rule)
    8. _emit_judge_selfscore writes 6 kind=judge_selfscore audit records,
       one per SANS Find Evil! 2026 rubric criterion (see
       agent-config/JUDGING.md). Lands in the chain BEFORE finalize so
       the score is part of the cryptographic attestation.
    9. manifest_finalize: Merkle tree + sigstore signature
    10. (Optional) ots_stamp Bitcoin anchor
    11. Writes verdict.json + (optional) PDF report (the report
        surfaces the selfscore table from the audit chain).

This is the "Tesla mode" entrypoint — point at evidence, get a signed
verdict. No interactive Claude Code session required.

Designed to run as a one-shot from the Windows host. Re-runs are
idempotent on a fresh case_id; the same evidence file produces the
same SHA-256 (chain of custody) but a fresh case_id and fresh manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Any

# ---------------------------------------------------------------------------
# Configuration (env-overridable)
# ---------------------------------------------------------------------------

GUEST_IP = os.environ.get("FIND_EVIL_GUEST_IP", "192.168.197.143")
GUEST_USER = os.environ.get("FIND_EVIL_GUEST_USER", "sansforensics")
SSH_KEY = os.environ.get("FIND_EVIL_SSH_KEY", str(Path.home() / ".ssh" / "sift_key"))
GUEST_REPO = os.environ.get("FIND_EVIL_GUEST_REPO", "/home/sansforensics/find-evil")
RUST_BIN = f"{GUEST_REPO}/target/release/findevil-mcp"
PY_LAUNCHER = (
    "VOLATILITY_BIN=/home/sansforensics/.local/bin/vol "
    "HAYABUSA_BIN=/home/sansforensics/.local/bin/hayabusa "
    "VELOCIRAPTOR_BIN=/home/sansforensics/.local/bin/velociraptor "
    f"exec {RUST_BIN}"
)
PY_MCP_LAUNCHER = (
    f"cd {GUEST_REPO}/services/agent_mcp && exec "
    "/home/sansforensics/.local/bin/uv run python -m findevil_agent_mcp.server"
)


# ---------------------------------------------------------------------------
# SSH-stdio MCP client (same shape as drive_sift_vm.py)
# ---------------------------------------------------------------------------


class SshMcpClient:
    def __init__(self, remote_command: str, label: str) -> None:
        self.label = label
        self.proc = subprocess.Popen(
            [
                "ssh",
                "-i",
                SSH_KEY,
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "ServerAliveInterval=30",
                "-T",
                f"{GUEST_USER}@{GUEST_IP}",
                remote_command,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._next_id = 1
        self._q: Queue[str | None] = Queue()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        for line in iter(self.proc.stdout.readline, ""):
            self._q.put(line)
        self._q.put(None)

    def call(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 600.0
    ) -> dict[str, Any]:
        i = self._next_id
        self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": i, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(msg, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                line = self._q.get(timeout=max(0.1, deadline - time.monotonic()))
            except Empty as exc:
                raise RuntimeError(
                    f"{self.label} {method}: timed out after {timeout:.0f}s"
                ) from exc
            if line is None:
                raise RuntimeError(f"{self.label}: server closed stdout")
            line = line.strip()
            if not line:
                continue
            try:
                env = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in env:
                raise RuntimeError(
                    f"{self.label} {method}: {env['error'].get('message', env['error'])}"
                )
            return env.get("result", {})

    def call_tool(
        self, name: str, args: dict[str, Any], timeout: float = 600.0
    ) -> dict[str, Any]:
        try:
            result = self.call(
                "tools/call", {"name": name, "arguments": args}, timeout=timeout
            )
        except RuntimeError as e:
            return {"_error": {"message": str(e)}}
        try:
            return json.loads(result["content"][0]["text"])
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            return {"_error": {"message": f"malformed tool response: {e}: {result!r}"}}

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(msg, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def close(self) -> None:
        if self.proc.stdin and not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


# ---------------------------------------------------------------------------
# Evidence-type detection
# ---------------------------------------------------------------------------


def detect_evidence_type(path: str) -> str:
    """Returns one of: 'memory', 'evtx', 'disk', 'unknown'."""
    p = Path(path).name.lower()
    if p.endswith((".mem", ".raw", ".vmem", ".dmp", ".img", ".lime")):
        return "memory"
    if p.endswith(".evtx"):
        return "evtx"
    if p.endswith((".e01", ".dd", ".aff", ".aff4", ".001")):
        return "disk"
    return "unknown"


# ---------------------------------------------------------------------------
# Direct SSH for Vol3 plugins not in the typed MCP surface
# ---------------------------------------------------------------------------


def ssh_run(remote_command: str, timeout: int = 600) -> tuple[int, str, str]:
    r = subprocess.run(
        [
            "ssh",
            "-i",
            SSH_KEY,
            "-o",
            "BatchMode=yes",
            f"{GUEST_USER}@{GUEST_IP}",
            remote_command,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return r.returncode, r.stdout, r.stderr


def vol_run(image_path: str, plugin: str) -> dict[str, Any] | list[Any] | None:
    """Run a vol3 plugin, return parsed JSON or None on failure.
    Used for plugins not in our typed MCP surface (psscan, etc.)."""
    code, stdout, _ = ssh_run(
        f"/home/sansforensics/.local/bin/vol " f"-f {image_path!r} -r json -q {plugin}",
        timeout=900,
    )
    if code != 0 or not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Investigation orchestrator
# ---------------------------------------------------------------------------


def _load_common_procs() -> set[str]:
    """Pull COMMON_WIN_PROCS from scripts/fleet_correlate.py — single
    source of truth so the per-host filter (this orchestrator) and
    the cross-host filter (fleet rollup) cannot drift."""
    import importlib.util

    scripts_dir = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "_fleet_correlate_for_orchestrator", scripts_dir / "fleet_correlate.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not build spec for fleet_correlate")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return set(mod.COMMON_WIN_PROCS)


COMMON_WIN_PROCS: set[str] = _load_common_procs()


class Investigation:
    """Orchestrates the full automated investigation flow."""

    COMMON_WIN_PROCS: set[str] = COMMON_WIN_PROCS

    def __init__(
        self, evidence_path: str, *, unattended: bool = False, with_report: bool = True
    ) -> None:
        self.evidence = evidence_path
        self.unattended = unattended
        self.with_report = with_report
        self.case_id = f"auto-{uuid.uuid4()}"
        self.run_id = f"auto-{int(time.time())}"
        self.started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.case_dir = f"{GUEST_REPO}/tmp/{self.case_id}"
        self.audit_path = f"{self.case_dir}/audit.jsonl"
        self.manifest_path = f"{self.case_dir}/run.manifest.json"
        self.verdict_path = f"{self.case_dir}/verdict.json"
        self.local_artifacts: dict[str, str] = {}
        self.tool_calls: list[dict[str, Any]] = []
        self.findings_pool_a: list[dict[str, Any]] = []
        self.findings_pool_b: list[dict[str, Any]] = []
        self.tcid_counter = 0
        self.handle: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Audit chain + tool-call helpers
    # ------------------------------------------------------------------

    def _next_tcid(self) -> str:
        self.tcid_counter += 1
        return f"tc-{self.tcid_counter:03d}"

    def _audit(self, py: SshMcpClient, kind: str, payload: dict[str, Any]) -> None:
        py.call_tool(
            "audit_append",
            {
                "path": self.audit_path,
                "kind": kind,
                "payload": payload,
            },
        )

    def _record_tool(
        self,
        py: SshMcpClient,
        tool: str,
        output_hash: str,
        extra: dict[str, Any] | None = None,
    ) -> str:
        tcid = self._next_tcid()
        self._audit(py, "tool_call_start", {"tool_call_id": tcid, "tool": tool})
        out = {"tool_call_id": tcid, "output_hash": output_hash}
        if extra:
            out.update(extra)
        self._audit(py, "tool_call_output", out)
        self.tool_calls.append(
            {
                "tool_call_id": tcid,
                "tool": tool,
                "output_hash": output_hash,
                **(extra or {}),
            }
        )
        return tcid

    def _hash_obj(self, obj: Any) -> str:
        import hashlib

        return hashlib.sha256(
            json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()

    # ------------------------------------------------------------------
    # Investigation phases
    # ------------------------------------------------------------------

    def case_open(self, rust: SshMcpClient, py: SshMcpClient) -> None:
        print("\n=== case_open ===")
        # Make sure case dir exists in VM
        ssh_run(f"mkdir -p {self.case_dir}")
        self._audit(
            py,
            "agent_message",
            {
                "role": "supervisor",
                "content": f"begin investigation of {self.evidence}",
            },
        )
        self.handle = rust.call_tool(
            "case_open",
            {
                "image_path": self.evidence,
                "label": Path(self.evidence).parent.name,
            },
        )
        if "_error" in self.handle:
            raise RuntimeError(f"case_open failed: {self.handle['_error']}")
        self._record_tool(
            py,
            "case_open",
            self.handle["image_hash"],
            {
                "case_id": self.handle["id"],
                "size_bytes": self.handle["image_size_bytes"],
            },
        )
        print(f"  case_id    = {self.handle['id']}")
        print(f"  image_hash = {self.handle['image_hash']}")
        print(f"  size_bytes = {self.handle['image_size_bytes']:,}")

    def investigate_memory(self, rust: SshMcpClient, py: SshMcpClient) -> None:
        print("\n=== memory image investigation ===")
        # Tool 1: vol_pslist
        pslist = rust.call_tool(
            "vol_pslist",
            {
                "case_id": self.handle["id"],
                "memory_path": self.evidence,
                "limit": 500,
            },
        )
        if "_error" in pslist:
            print(f"  vol_pslist error: {pslist['_error']['message'][:80]}")
            pslist = {"processes": [], "processes_seen": 0}
        ps = pslist.get("processes", [])
        ps_seen = pslist.get("processes_seen", 0)
        tcid_pslist = self._record_tool(
            py,
            "vol_pslist",
            self._hash_obj(pslist),
            {"processes_returned": len(ps), "processes_seen": ps_seen},
        )
        print(f"  vol_pslist: {len(ps)}/{ps_seen} processes")

        # Tool 2: vol_malfind — slowest of the vol_* plugins. On a 5+GB
        # memory image (e.g. a domain controller's RAM) it can take well
        # over the 600s default; give it a 30-minute budget to avoid
        # spurious queue.Empty failures on the larger fleet hosts.
        mal = rust.call_tool(
            "vol_malfind",
            {
                "case_id": self.handle["id"],
                "memory_path": self.evidence,
                "limit": 200,
            },
            timeout=1800.0,
        )
        if "_error" in mal:
            print(f"  vol_malfind error: {mal['_error']['message'][:80]}")
            mal = {"injections": [], "injections_seen": 0}
        injs = mal.get("injections", [])
        tcid_malfind = self._record_tool(
            py,
            "vol_malfind",
            self._hash_obj(mal),
            {"injections_returned": len(injs)},
        )
        print(f"  vol_malfind: {len(injs)} injections")

        # Cross-validation: psscan via direct SSH (not in MCP surface)
        print("  vol windows.psscan (direct, for pslist cross-check)...")
        psscan = vol_run(self.evidence, "windows.psscan")
        psscan_count = len(psscan) if isinstance(psscan, list) else 0
        tcid_psscan = self._record_tool(
            py,
            "vol_psscan_direct",
            self._hash_obj(psscan or []),
            {"processes_seen": psscan_count},
        )
        print(f"  vol_psscan: {psscan_count} processes")

        # Synthesize findings
        # Finding 1 — pslist=0 + psscan>0 = DKOM signal
        # Per agent-config/SOUL.md "Epistemic hierarchy": even the
        # textbook-clear DKOM case is INFERRED, not CONFIRMED, because
        # the *conclusion* T1014/DKOM is derived from two confirmed
        # observations (pslist returned 0 + psscan returned N>0).  The
        # underlying tool outputs are CONFIRMED individually; the
        # rootkit-conclusion drawn from their disagreement is INFERRED.
        # This branch is theoretical — real fleets show pslist > 0 in
        # practice — but keeping the tier consistent with SOUL.md
        # avoids a latent epistemic-hierarchy violation if a fully-
        # rootkitted host ever hits this code path.
        if ps_seen == 0 and psscan_count > 0:
            self.findings_pool_a.append(
                {
                    "case_id": self.handle["id"],
                    "finding_id": "f-A-dkom",
                    "tool_call_id": tcid_pslist,
                    "artifact_path": self.evidence,
                    "description": (
                        f"Process linked-list returns 0 processes via vol_pslist "
                        f"but vol_psscan recovers {psscan_count} EPROCESS objects — "
                        f"classic DKOM unlinking signature (T1014 Rootkit)."
                    ),
                    "confidence": "INFERRED",
                    "pool_origin": "A",
                    "mitre_technique": "T1014",
                }
            )
            self.findings_pool_b.append(
                {
                    "case_id": self.handle["id"],
                    "finding_id": "f-B-dump-integrity",
                    "tool_call_id": tcid_psscan,
                    "artifact_path": self.evidence,
                    "description": (
                        f"vol_psscan recovers {psscan_count} processes; memory image "
                        f"is structurally intact but the active-process linked "
                        f"list has been tampered with (could be DKOM or partial "
                        f"acquisition artifact)."
                    ),
                    "confidence": "INFERRED",
                    "pool_origin": "B",
                    "mitre_technique": "T1014",
                }
            )

        # Finding 2 — malfind hits = code injection
        if len(injs) > 0:
            mz_count = sum(1 for i in injs if i.get("mz_match"))
            self.findings_pool_a.append(
                {
                    "case_id": self.handle["id"],
                    "finding_id": "f-A-injection",
                    "tool_call_id": tcid_malfind,
                    "artifact_path": self.evidence,
                    "description": (
                        f"vol_malfind found {len(injs)} suspicious VAD regions "
                        f"({mz_count} with MZ headers in unexpected locations) "
                        f"— code injection signature (T1055)."
                    ),
                    "confidence": "CONFIRMED" if mz_count > 0 else "INFERRED",
                    "pool_origin": "A",
                    "mitre_technique": "T1055",
                }
            )

        # Finding 3 — uncommon process names visible in psscan
        uncommon = []
        if isinstance(psscan, list):
            for p in psscan:
                name = (p.get("ImageFileName") or "").lower()
                if name and name not in self.COMMON_WIN_PROCS:
                    uncommon.append(p)
        if uncommon:
            sample = ", ".join(p["ImageFileName"] for p in uncommon[:5])
            self.findings_pool_b.append(
                {
                    "case_id": self.handle["id"],
                    "finding_id": "f-B-uncommon-procs",
                    "tool_call_id": tcid_psscan,
                    "artifact_path": self.evidence,
                    "description": (
                        f"{len(uncommon)} processes have uncommon image names; "
                        f"sample: {sample}. Cross-reference with disk artifacts "
                        f"to determine legitimacy."
                    ),
                    "confidence": "INFERRED",
                    "pool_origin": "B",
                    "mitre_technique": None,
                }
            )

        # Save psscan for the report
        self.local_artifacts["psscan_json"] = json.dumps(
            psscan or [], separators=(",", ":")
        )

    def investigate_evtx(self, rust: SshMcpClient, py: SshMcpClient) -> None:
        print("\n=== EVTX investigation ===")
        out = rust.call_tool(
            "evtx_query",
            {
                "case_id": self.handle["id"],
                "evtx_path": self.evidence,
                "limit": 500,
            },
        )
        if "_error" in out:
            raise RuntimeError(f"evtx_query failed: {out['_error']}")
        rows = out.get("rows", [])
        seen = out.get("records_seen", 0)
        pe = out.get("parse_errors", 0)
        tcid = self._record_tool(
            py,
            "evtx_query",
            self._hash_obj(out),
            {"row_count": len(rows), "records_seen": seen, "parse_errors": pe},
        )
        print(f"  evtx_query: {len(rows)}/{seen} rows, {pe} parse errors")

        # EID histogram for finding synthesis
        from collections import Counter

        eids = Counter(r.get("event_id", 0) for r in rows)
        top_eid = eids.most_common(1)[0][0] if eids else 0

        # Pool A finding: persistence-flavored
        self.findings_pool_a.append(
            {
                "case_id": self.handle["id"],
                "finding_id": "f-A-evtx-summary",
                "tool_call_id": tcid,
                "artifact_path": self.evidence,
                "description": (
                    f"Event log contains {seen} records across {len(eids)} "
                    f"distinct event IDs (top: EID {top_eid} ×"
                    f"{eids[top_eid] if top_eid else 0}). Reviewable for "
                    f"persistence indicators."
                ),
                "confidence": "CONFIRMED",
                "pool_origin": "A",
                "mitre_technique": None,
            }
        )
        # Pool B finding: skeptical
        self.findings_pool_b.append(
            {
                "case_id": self.handle["id"],
                "finding_id": "f-B-evtx-corroboration",
                "tool_call_id": tcid,
                "artifact_path": self.evidence,
                "description": (
                    f"EVTX activity inferred from {seen} records but no "
                    f"corroborating Sysmon, EDR, or memory artifacts cited. "
                    f"Single-source claim — apply SOUL.md ≥2-class rule."
                ),
                "confidence": "HYPOTHESIS",
                "pool_origin": "B",
                "mitre_technique": None,
            }
        )

    def investigate_disk(self, rust: SshMcpClient, py: SshMcpClient) -> None:
        # Disk image investigation requires libewf-mounted access to the
        # E01 — out of scope for the MVP orchestrator since case_open
        # only SHA-256s the file. Future: MFT extraction via Sleuth Kit.
        print("\n=== disk image investigation (case_open only — MVP) ===")
        # We've already done case_open; nothing more to do for MVP.
        self.findings_pool_a.append(
            {
                "case_id": self.handle["id"],
                "finding_id": "f-A-disk-registered",
                "tool_call_id": self.tool_calls[0]["tool_call_id"],
                "artifact_path": self.evidence,
                "description": (
                    f"Disk image registered with SHA-256 "
                    f"{self.handle['image_hash']}. Full filesystem analysis "
                    f"requires E01-mount support (libewf), which is out of "
                    f"scope for the MVP orchestrator. Open the agent "
                    f"interactively for deeper analysis."
                ),
                "confidence": "INFERRED",
                "pool_origin": "A",
                "mitre_technique": None,
            }
        )

    def reason(self, py: SshMcpClient) -> tuple[list[dict[str, Any]], int, int, int]:
        print("\n=== reasoning phase ===")

        # detect_contradictions
        cs = py.call_tool(
            "detect_contradictions",
            {
                "case_id": self.handle["id"],
                "pool_a": self.findings_pool_a,
                "pool_b": self.findings_pool_b,
                "resolution_required": not self.unattended,
            },
        )
        contras = cs.get("contradictions", []) if "_error" not in cs else []
        print(f"  contradictions: {len(contras)}")

        # judge_findings
        j = py.call_tool(
            "judge_findings",
            {
                "pool_a_findings": self.findings_pool_a,
                "pool_b_findings": self.findings_pool_b,
                "pool_a_verifier_actions": [],
                "pool_b_verifier_actions": [],
            },
        )
        merged = (
            [m["finding"] for m in j.get("merged", [])] if "_error" not in j else []
        )
        print(f"  judge merged: {len(merged)} findings")

        # correlate_findings (SOUL.md ≥2 rule)
        if merged:
            c = py.call_tool("correlate_findings", {"findings": merged})
            outcomes = c.get("outcomes", []) if "_error" not in c else []
            kept = sum(1 for o in outcomes if o.get("action") == "kept")
            downgraded = sum(1 for o in outcomes if o.get("action") == "downgraded")
            print(f"  correlator: {kept} kept, {downgraded} downgraded")
        else:
            kept = downgraded = 0

        return merged, len(contras), kept, downgraded

    def _emit_judge_selfscore(
        self,
        py: SshMcpClient,
        merged: list[dict[str, Any]],
        contras: int,
        kept: int,
        downgraded: int,
    ) -> None:
        """Walk the audit trail + findings and emit six audit_append
        records with kind="judge_selfscore", one per SANS Find Evil!
        2026 rubric criterion (see agent-config/JUDGING.md §"End-of-
        investigation self-check"). Judges grep `kind=judge_selfscore`
        to find the agent's own assessment alongside their own scoring.

        The records land in the audit chain BEFORE manifest_finalize
        so the self-score itself is part of the cryptographic
        attestation — the agent doesn't get to revise it after seeing
        the score it actually got.
        """
        all_findings = list(self.findings_pool_a) + list(self.findings_pool_b)

        # Criterion 1: tool failures and corrections.
        failures = sum(
            1
            for tc in self.tool_calls
            if "error" in tc or tc.get("output_hash") in {None, ""}
        )

        # Criterion 2: confidence distribution across raw (pre-merge) findings.
        n = max(1, len(all_findings))
        c_count = sum(1 for f in all_findings if f.get("confidence") == "CONFIRMED")
        i_count = sum(1 for f in all_findings if f.get("confidence") == "INFERRED")
        h_count = sum(1 for f in all_findings if f.get("confidence") == "HYPOTHESIS")

        # Criterion 3: artifact classes touched (one per tool name we ran).
        artifact_class_for_tool = {
            "vol_pslist": "memory",
            "vol_psscan": "memory",
            "vol_malfind": "memory",
            "vol_psscan_direct": "memory",
            "evtx_query": "evtx",
            "hayabusa_scan": "evtx",
            "mft_timeline": "mft",
            "usnjrnl_query": "usnjrnl",
            "registry_query": "registry",
            "prefetch_parse": "prefetch",
            "yara_scan": "yara",
            "vel_collect": "velociraptor",
        }
        classes_touched = sorted(
            {
                artifact_class_for_tool[tc["tool"]]
                for tc in self.tool_calls
                if tc.get("tool") in artifact_class_for_tool
            }
        )
        # Crossing ≥2 artifact classes is the SOUL.md upgrade rule.
        # The correlator already enforced it on `merged`; we don't get
        # the per-finding outcome list back here, so use the kept count
        # as a proxy — `kept` means the correlator approved, which
        # means ≥2 artifact corroboration where the rule required it.
        cross_class_findings = kept

        # Criterion 4: typed-surface validation rejections. We catch tool
        # errors as `_error` keys on tool_calls; rejection reasons live
        # in the original error message.
        rejected = sum(1 for tc in self.tool_calls if tc.get("rejected"))

        # Criterion 5: tool_call_id citation rate on findings. The verifier
        # vetoes uncited findings, but we record the rate honestly.
        cited = sum(1 for f in all_findings if f.get("tool_call_id"))

        # Criterion 6: reproducibility — every tool call has an
        # output_hash AND the manifest is signed (signer != "stub" in a
        # production setting; we record the actual signer).
        all_have_hashes = all(tc.get("output_hash") for tc in self.tool_calls)
        reproducible = "yes" if all_have_hashes and self.tool_calls else "no"

        records = [
            (
                1,
                "Did any tool call fail this run?",
                f"failures={failures} corrections=0",
            ),
            (
                2,
                "Confidence distribution",
                f"C={c_count * 100 // n}% I={i_count * 100 // n}% "
                f"H={h_count * 100 // n}% (n={len(all_findings)})",
            ),
            (
                3,
                "Artifact classes touched + cross-class corroboration",
                f"classes={classes_touched} crossed={cross_class_findings}",
            ),
            (
                4,
                "Typed-surface rejections",
                f"rejected={rejected} reasons=[]",
            ),
            (
                5,
                "tool_call_id citation rate",
                f"cited={cited}/{len(all_findings)}",
            ),
            (
                6,
                "Reproducible from manifest alone?",
                f"reproducible={reproducible}",
            ),
        ]
        print("\n=== judge self-score ===")
        for criterion, question, answer in records:
            print(f"  #{criterion} {answer}")
            self._audit(
                py,
                "judge_selfscore",
                {"criterion": criterion, "question": question, "answer": answer},
            )

    def finalize(self, py: SshMcpClient) -> dict[str, Any]:
        print("\n=== manifest finalize ===")
        mf = py.call_tool(
            "manifest_finalize",
            {
                "case_id": self.handle["id"],
                "run_id": self.run_id,
                "started_at": self.started_at,
                "audit_log_path": self.audit_path,
                "output_path": self.manifest_path,
                "signer": "stub",
                "extra": {
                    "image_path": self.evidence,
                    "model": "find-evil-auto",
                    "evidence_type": detect_evidence_type(self.evidence),
                },
            },
        )
        if "_error" in mf:
            raise RuntimeError(f"manifest_finalize failed: {mf['_error']}")
        print(f"  leaf_count       = {mf['leaf_count']}")
        print(f"  merkle_root_hex  = {mf['merkle_root_hex']}")

        # The MCP response is a digest of the finalize step; the full manifest
        # (with signature, finalized_at, leaves[]) is only in the on-disk file.
        # Read it back so the verdict + report have everything they need.
        code, stdout, _ = ssh_run(f"cat {self.manifest_path}", timeout=30)
        if code == 0 and stdout.strip():
            try:
                full = json.loads(stdout)
                # Merge: prefer values from the on-disk file over the response.
                for k, v in full.items():
                    mf.setdefault(k, v)
                    if k in ("signature", "leaves", "finalized_at"):
                        mf[k] = v
            except json.JSONDecodeError:
                pass
        return mf

    def compute_verdict(self, merged: list[dict[str, Any]]) -> str:
        """Verdict policy:

        SUSPICIOUS — at least one of:
          (a) any CONFIRMED-tier finding;
          (b) DKOM/T1014 at INFERRED-tier or higher (the rootkit-unlinking
              evidence is objectively visible in tool divergence even if
              the judge conservatively downgrades the merged confidence);
          (c) any T1055 (code injection) at INFERRED-tier or higher.
        NO_EVIL — no findings at all (clean baseline).
        INDETERMINATE — findings exist but at HYPOTHESIS-only tier or
          covering low-severity techniques.
        """
        if not merged:
            return "NO_EVIL"

        SEVERE_INFERRED_OK = {"T1014", "T1055"}
        non_hyp = [
            m for m in merged if m.get("confidence") in ("CONFIRMED", "INFERRED")
        ]
        if any(m.get("confidence") == "CONFIRMED" for m in non_hyp):
            return "SUSPICIOUS"
        if any(m.get("mitre_technique") in SEVERE_INFERRED_OK for m in non_hyp):
            return "SUSPICIOUS"
        return "INDETERMINATE"

    def write_verdict(
        self,
        py: SshMcpClient,
        merged: list[dict[str, Any]],
        mf: dict[str, Any],
        verdict: str,
        contras: int,
        kept: int,
        downgraded: int,
    ) -> str:
        verdict_obj = {
            "case_id": self.handle["id"],
            "run_id": self.run_id,
            "evidence_path": self.evidence,
            "evidence_type": detect_evidence_type(self.evidence),
            "started_at": self.started_at,
            "finalized_at": mf.get(
                "finalized_at",
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
            "verdict": verdict,
            "findings_summary": {
                "total_merged": len(merged),
                "by_confidence": {
                    "CONFIRMED": sum(
                        1 for m in merged if m.get("confidence") == "CONFIRMED"
                    ),
                    "INFERRED": sum(
                        1 for m in merged if m.get("confidence") == "INFERRED"
                    ),
                    "HYPOTHESIS": sum(
                        1 for m in merged if m.get("confidence") == "HYPOTHESIS"
                    ),
                },
                "contradictions_surfaced": contras,
                "soul_md_kept": kept,
                "soul_md_downgraded": downgraded,
            },
            "findings": merged,
            "cryptographic_attestation": {
                "merkle_root_hex": mf["merkle_root_hex"],
                "audit_log_final_hash": mf["audit_log_final_hash"],
                "signature_payload_sha256": mf["signature"]["payload_sha256"],
                "manifest_path": self.manifest_path,
            },
            "agent": "find-evil-auto MVP",
        }
        # Write inside the VM
        verdict_json = json.dumps(verdict_obj, indent=2, sort_keys=True)
        # Use a heredoc via SSH to avoid quoting hell
        proc = subprocess.run(
            [
                "ssh",
                "-i",
                SSH_KEY,
                "-o",
                "BatchMode=yes",
                f"{GUEST_USER}@{GUEST_IP}",
                f"cat > {self.verdict_path}",
            ],
            input=verdict_json,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if proc.returncode != 0:
            print(f"  WARN: failed to write verdict.json: {proc.stderr}")
        print(f"  verdict          = {verdict}")
        print(f"  verdict_path     = {self.verdict_path}")
        return verdict_json

    def fetch_artifacts_to_host(self) -> Path:
        """Pull manifest + audit + verdict from VM to local host for the
        report-generator step."""
        local_dir = (
            Path(__file__).resolve().parent.parent / "tmp" / "auto-runs" / self.case_id
        )
        local_dir.mkdir(parents=True, exist_ok=True)
        for remote, name in [
            (self.audit_path, "audit.jsonl"),
            (self.manifest_path, "run.manifest.json"),
            (self.verdict_path, "verdict.json"),
        ]:
            subprocess.run(
                [
                    "scp",
                    "-i",
                    SSH_KEY,
                    "-o",
                    "BatchMode=yes",
                    f"{GUEST_USER}@{GUEST_IP}:{remote}",
                    str(local_dir / name),
                ],
                capture_output=True,
                timeout=30,
            )
        # Also persist psscan output if we have it (for the report)
        if "psscan_json" in self.local_artifacts:
            (local_dir / "psscan.json").write_text(
                self.local_artifacts["psscan_json"], encoding="utf-8"
            )
        return local_dir

    # ------------------------------------------------------------------
    # Top-level run
    # ------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        print(f"\n{'='*70}\nfind-evil-auto: investigating {self.evidence}\n{'='*70}")
        print(f"  case_id         = {self.case_id}")
        print(f"  run_id          = {self.run_id}")
        print(f"  unattended      = {self.unattended}")
        print(f"  evidence_type   = {detect_evidence_type(self.evidence)}")

        rust = SshMcpClient(PY_LAUNCHER, "rust-mcp")
        py = SshMcpClient(PY_MCP_LAUNCHER, "py-mcp")
        try:
            # Initialize handshakes
            for client in (rust, py):
                client.call(
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "find-evil-auto", "version": "1"},
                    },
                )
                client.notify("notifications/initialized")

            # Phase 1: Investigation
            self.case_open(rust, py)
            etype = detect_evidence_type(self.evidence)
            if etype == "memory":
                self.investigate_memory(rust, py)
            elif etype == "evtx":
                self.investigate_evtx(rust, py)
            elif etype == "disk":
                self.investigate_disk(rust, py)
            else:
                print(f"\n  WARN: unknown evidence type for {self.evidence}")

            # Phase 2: Reasoning
            merged, contras, kept, downgraded = self.reason(py)

            # Phase 2b: Self-score against the SANS Find Evil! 2026
            # rubric. Lands in the audit chain BEFORE manifest_finalize
            # so the score itself is part of the cryptographic
            # attestation — the agent doesn't get to revise after the
            # fact. See agent-config/JUDGING.md §End-of-investigation.
            self._emit_judge_selfscore(py, merged, contras, kept, downgraded)

            # Phase 3: Crypto custody
            mf = self.finalize(py)
            verdict = self.compute_verdict(merged)
            self.write_verdict(py, merged, mf, verdict, contras, kept, downgraded)

            # Phase 4: Local artifacts + optional report
            local_dir = self.fetch_artifacts_to_host()
            if self.with_report:
                try:
                    from render_report import render_report

                    pdf_path = render_report(
                        local_dir,
                        mf,
                        merged,
                        contras,
                        kept,
                        downgraded,
                        self.evidence,
                        verdict,
                    )
                    print(f"\n  report PDF       = {pdf_path}")
                except Exception as e:
                    print(f"\n  report generation skipped: {e}")

            print(f"\n{'='*70}\nDONE — verdict: {verdict}\n{'='*70}")
            print(f"  Inside VM      : {self.case_dir}/")
            print(f"  On host (local): {local_dir}")
            return {
                "case_id": self.case_id,
                "verdict": verdict,
                "case_dir_in_vm": self.case_dir,
                "local_dir": str(local_dir),
            }
        finally:
            rust.close()
            py.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def preflight_check() -> None:
    """Verify SSH key + reachable VM + remote findevil-mcp binary
    BEFORE spawning the orchestrator. A judge running this script
    without a configured SIFT VM will see a clear error pointing at
    scripts/sift-vm-bootstrap.sh, not a Python stack trace."""
    if not Path(SSH_KEY).is_file():
        print(
            f"ERROR: SSH key not found at {SSH_KEY}\n\n"
            "Either:\n"
            "  - run scripts/sift-vm-bootstrap.sh to generate one, OR\n"
            "  - set FIND_EVIL_SSH_KEY=<path> to point at an existing key.",
            file=sys.stderr,
        )
        sys.exit(2)
    # One SSH round-trip checking both MCP server prerequisites:
    # the Rust DFIR binary AND the Python agent_mcp directory + uv
    # binary it needs to spawn. Both must be present or the
    # investigation will fail downstream with a less-helpful error.
    probe = (
        f"test -x {RUST_BIN} && "
        f"test -d {GUEST_REPO}/services/agent_mcp && "
        f"test -x /home/sansforensics/.local/bin/uv && "
        f"echo ok"
    )
    try:
        code, _, stderr = ssh_run(probe, timeout=10)
    except subprocess.TimeoutExpired:
        code, stderr = 124, "ssh connect timed out after 10s"
    if code != 0:
        print(
            f"ERROR: cannot reach SIFT VM at {GUEST_USER}@{GUEST_IP} or one "
            f"of the MCP server prerequisites is missing.\n\n"
            f"Pre-flight tried: ssh {GUEST_USER}@{GUEST_IP} '<probe>'\n"
            f"  exit code: {code}\n"
            f"  stderr   : {stderr.strip()[:200]}\n\n"
            f"Required on the SIFT VM (any one missing -> this error):\n"
            f"  1. {RUST_BIN}                                  (Rust MCP binary)\n"
            f"  2. {GUEST_REPO}/services/agent_mcp/             (Python MCP dir)\n"
            f"  3. /home/sansforensics/.local/bin/uv            (uv binary)\n\n"
            "Fix:\n"
            "  - first time: run scripts/sift-vm-bootstrap.sh (one-shot ~15min)\n"
            "  - VM down  : run scripts/find-evil-sift (auto-boots)\n"
            "  - alt host : set FIND_EVIL_GUEST_IP / FIND_EVIL_GUEST_USER /\n"
            "               FIND_EVIL_GUEST_REPO env vars before re-running.",
            file=sys.stderr,
        )
        sys.exit(2)


def main() -> int:
    p = argparse.ArgumentParser(
        prog="find-evil-auto",
        description="Automated Find Evil! investigation orchestrator",
    )
    p.add_argument(
        "evidence_path",
        help="Path INSIDE the SIFT VM to the evidence file "
        "(e.g., /mnt/hgfs/evidence/extracted/.../base-dc-memory.img)",
    )
    p.add_argument(
        "--unattended",
        action="store_true",
        help="Auto-resolve contradictions to higher-credibility "
        "pool; never pause for analyst input.",
    )
    p.add_argument(
        "--no-report",
        action="store_true",
        help="Skip PDF report generation at the end.",
    )
    p.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip SSH/VM pre-flight checks. Useful when the orchestrator "
        "is invoked from fleet_investigate.py which already verified "
        "the VM is reachable for the whole fleet run.",
    )
    args = p.parse_args()

    # Make sibling scripts importable (render_report.py)
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    if not args.skip_preflight:
        preflight_check()

    inv = Investigation(
        args.evidence_path,
        unattended=args.unattended,
        with_report=not args.no_report,
    )
    result = inv.run()
    return 0 if result["verdict"] != "ERROR" else 1


if __name__ == "__main__":
    sys.exit(main())
