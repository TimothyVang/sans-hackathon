"""Tests for verify_finding wrapper.

Uses ``MockMcpClient`` via monkeypatching ``_make_mcp_client`` so we
don't spawn a real Rust subprocess in unit tests.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from findevil_agent.mcp_client import MockMcpClient

from findevil_agent_mcp.tools import verify_finding as vf
from findevil_agent_mcp.tools.verify_finding import (
    SPEC,
    VerifyFindingInput,
    VerifyFindingOutput,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _finding_dict(**over: Any) -> dict[str, Any]:
    base = {
        "case_id": "case-001",
        "finding_id": "f-1",
        "tool_call_id": "tc-1",
        "artifact_path": "C:\\Windows\\Temp\\x.exe",
        "confidence": "CONFIRMED",
        "mitre_technique": "T1059",
        "description": "scheduled task points at writable temp",
        "pool_origin": "A",
    }
    base.update(over)
    return base


class TestVerifyFinding:
    async def test_replay_match_approves(self, monkeypatch: Any) -> None:
        canned_text = json.dumps(
            {"rows": [{"id": 1, "data": "x"}]}, sort_keys=True, separators=(",", ":")
        )
        expected_sha = _sha(canned_text)

        client = MockMcpClient()
        client.register("evtx_query", lambda args: canned_text)

        monkeypatch.setattr(vf, "_make_mcp_client", lambda _cmd: client)

        result = await SPEC.handler(
            VerifyFindingInput(
                finding=_finding_dict(),
                tool_call_index={
                    "tc-1": {
                        "tool_name": "evtx_query",
                        "arguments": {"case_id": "case-001"},
                        "output_sha256": expected_sha,
                    }
                },
                findevil_mcp_command=["dummy"],
            )
        )
        assert isinstance(result, VerifyFindingOutput)
        assert result.action == "approved"
        assert result.replay_matched is True
        assert result.replay_actual_sha256 == expected_sha

    async def test_replay_drift_downgrades(self, monkeypatch: Any) -> None:
        client = MockMcpClient()
        client.register("evtx_query", lambda args: "DIFFERENT_OUTPUT")
        monkeypatch.setattr(vf, "_make_mcp_client", lambda _cmd: client)

        result = await SPEC.handler(
            VerifyFindingInput(
                finding=_finding_dict(),
                tool_call_index={
                    "tc-1": {
                        "tool_name": "evtx_query",
                        "arguments": {},
                        "output_sha256": "0" * 64,
                    }
                },
                findevil_mcp_command=["dummy"],
            )
        )
        assert isinstance(result, VerifyFindingOutput)
        assert result.action == "downgraded"
        assert result.replay_matched is False

    async def test_missing_tool_call_id_rejected(self, monkeypatch: Any) -> None:
        client = MockMcpClient()
        monkeypatch.setattr(vf, "_make_mcp_client", lambda _cmd: client)

        result = await SPEC.handler(
            VerifyFindingInput(
                finding=_finding_dict(tool_call_id="tc-missing"),
                tool_call_index={},
                findevil_mcp_command=["dummy"],
            )
        )
        assert isinstance(result, VerifyFindingOutput)
        assert result.action == "rejected"
        assert "tc-missing" in result.reason
