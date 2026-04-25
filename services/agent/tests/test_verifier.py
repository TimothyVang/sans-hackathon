"""Tests for findevil_agent.verifier."""

from __future__ import annotations

from typing import Any

from findevil_agent.events import Finding
from findevil_agent.mcp_client import MockMcpClient
from findevil_agent.verifier import (
    downgrade_confidence,
    reverify_finding,
    verify_findings,
)


def _make_finding(
    tool_call_id: str = "tc-1",
    confidence: str = "CONFIRMED",
    finding_id: str = "f-1",
) -> Finding:
    return Finding(
        case_id="c-1",
        finding_id=finding_id,
        tool_call_id=tool_call_id,
        artifact_path="Security.evtx",
        confidence=confidence,
        description="logon from 192.168.1.5",
    )


def _make_index(
    *,
    tool_name: str = "evtx_query",
    arguments: dict[str, Any] | None = None,
    output_sha256: str = "a" * 64,
) -> dict[str, dict[str, Any]]:
    return {
        "tc-1": {
            "tool_name": tool_name,
            "arguments": arguments or {"case_id": "c-1", "evtx_path": "x"},
            "output_sha256": output_sha256,
        }
    }


class TestRequiredCitation:
    def test_missing_tool_call_id_rejects(self) -> None:
        # Build a Finding with empty tool_call_id by directly creating
        # one (bypassing Pydantic's "required" since the runtime path
        # has agents that may emit empty strings).
        f = _make_finding(tool_call_id="")
        action, replay = reverify_finding(f, mcp=MockMcpClient(), tool_call_index={})
        assert action.action == "rejected"
        assert "tool_call_id" in action.reason
        assert replay is None

    def test_missing_audit_record_rejects(self) -> None:
        f = _make_finding(tool_call_id="tc-not-in-index")
        action, replay = reverify_finding(f, mcp=MockMcpClient(), tool_call_index={})
        assert action.action == "rejected"
        assert "not found" in action.reason
        assert replay is None


class TestSuccessPath:
    def test_matching_sha_approves(self) -> None:
        f = _make_finding()
        same_payload = {"row_count": 7}
        # MockMcpClient computes SHA on the canonical JSON of dict;
        # we precompute the same SHA into the index.
        import hashlib
        import json

        canonical = json.dumps(same_payload, sort_keys=True, separators=(",", ":"))
        expected_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        mcp = MockMcpClient()
        mcp.register("evtx_query", same_payload)
        index = _make_index(output_sha256=expected_sha)
        action, replay = reverify_finding(f, mcp=mcp, tool_call_index=index)
        assert action.action == "approved"
        assert replay is not None
        assert replay.matched is True
        assert replay.actual_sha256 == expected_sha


class TestDriftPath:
    def test_mismatched_sha_downgrades(self) -> None:
        f = _make_finding()
        mcp = MockMcpClient()
        mcp.register("evtx_query", {"row_count": 99})
        # Index says expected SHA is 'a'*64 but the mock returns
        # something else.
        index = _make_index(output_sha256="a" * 64)
        action, replay = reverify_finding(f, mcp=mcp, tool_call_index=index)
        assert action.action == "downgraded"
        assert "drift" in action.reason
        assert replay is not None
        assert replay.matched is False
        assert replay.expected_sha256 == "a" * 64


class TestRpcErrorPath:
    def test_mcp_error_rejects(self) -> None:
        f = _make_finding()
        mcp = MockMcpClient()  # no handler registered for evtx_query
        index = _make_index()
        action, replay = reverify_finding(f, mcp=mcp, tool_call_index=index)
        assert action.action == "rejected"
        assert replay is not None
        assert replay.matched is False
        assert replay.error is not None
        assert "rpc error" in replay.error


class TestBatchVerify:
    def test_batch_returns_aligned_tuples(self) -> None:
        mcp = MockMcpClient()
        mcp.register("evtx_query", {"x": 1})
        # Build expected SHA matching what the mock will produce.
        import hashlib
        import json

        canonical = json.dumps({"x": 1}, sort_keys=True, separators=(",", ":"))
        expected_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        index = {
            "tc-1": {"tool_name": "evtx_query", "arguments": {}, "output_sha256": expected_sha},
            "tc-2": {"tool_name": "evtx_query", "arguments": {}, "output_sha256": expected_sha},
        }
        findings = [
            Finding(
                case_id="c",
                finding_id="f-1",
                tool_call_id="tc-1",
                artifact_path="x",
                confidence="CONFIRMED",
                description="a",
            ),
            Finding(
                case_id="c",
                finding_id="f-2",
                tool_call_id="tc-2",
                artifact_path="y",
                confidence="INFERRED",
                description="b",
            ),
        ]
        results = verify_findings(findings, mcp=mcp, tool_call_index=index)
        assert len(results) == 2
        for _original, action, replay in results:
            assert action.action == "approved"
            assert replay is not None and replay.matched


class TestDowngradeConfidence:
    def test_confirmed_to_inferred(self) -> None:
        f = _make_finding(confidence="CONFIRMED")
        downgraded = downgrade_confidence(f)
        assert downgraded.confidence == "INFERRED"

    def test_inferred_to_hypothesis(self) -> None:
        f = _make_finding(confidence="INFERRED")
        assert downgrade_confidence(f).confidence == "HYPOTHESIS"

    def test_hypothesis_stays_hypothesis(self) -> None:
        f = _make_finding(confidence="HYPOTHESIS")
        assert downgrade_confidence(f).confidence == "HYPOTHESIS"
