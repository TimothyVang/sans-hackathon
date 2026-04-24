"""Verifier node — vetoes uncited Findings + re-runs tool calls.

Spec #2 §8.1 (Verify stage) + ``CLAUDE.md`` invariant
"Every Finding cites a ``tool_call_id``."

The verifier sits between the contradiction-resolution node and
the correlator in the LangGraph state machine. For every candidate
Finding it:

1. **Required-citation check.** Reject if ``tool_call_id`` is
   missing or empty. The agent system prompts already enforce
   this, but the verifier is the architectural guard.
2. **Re-execution check.** Re-runs the tool call and confirms the
   output_sha256 matches what the audit log declared. If the
   digests diverge, downgrade the Finding's confidence (a tool
   that produced different output on replay is, at best, racy
   evidence).
3. **Confidence floor.** If the re-execution fails entirely, the
   Finding is rejected — the underlying evidence is no longer
   reproducible.

The verifier uses ``McpClient`` (production: ``StdioMcpClient``;
tests: ``MockMcpClient``) so we never need a live Rust binary in
unit tests.

This module is pure orchestration over the existing ``mcp_client``
+ ``events`` types. No LLM calls — confidence decisions are
deterministic given the same inputs, which is what the M2 chain
requires for replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from findevil_agent.events import Finding, VerifierAction
from findevil_agent.mcp_client import McpClient, McpRpcError, ToolCallResult


@dataclass(frozen=True)
class CallReplay:
    """Outcome of one tool re-run during verification."""

    tool_name: str
    arguments: dict[str, Any]
    expected_sha256: str
    actual_sha256: str | None
    matched: bool
    error: str | None = None


def reverify_finding(
    finding: Finding,
    *,
    mcp: McpClient,
    tool_call_index: dict[str, dict[str, Any]],
) -> tuple[VerifierAction, CallReplay | None]:
    """Re-run the single tool call cited by ``finding`` and decide
    approve / reject / downgrade.

    ``tool_call_index`` maps ``tool_call_id`` → the original
    ``{"tool_name", "arguments", "output_sha256"}`` triple recorded
    in the audit log. The supervisor builds this index before
    invoking the verifier.
    """
    if not finding.tool_call_id:
        return (
            VerifierAction(
                case_id=finding.case_id,
                action="rejected",
                finding_id=finding.finding_id,
                reason="missing tool_call_id (Spec #2 invariant)",
            ),
            None,
        )

    record = tool_call_index.get(finding.tool_call_id)
    if record is None:
        return (
            VerifierAction(
                case_id=finding.case_id,
                action="rejected",
                finding_id=finding.finding_id,
                reason=f"tool_call_id {finding.tool_call_id!r} not found in audit log",
            ),
            None,
        )

    tool_name = str(record.get("tool_name", ""))
    arguments = dict(record.get("arguments") or {})
    expected = str(record.get("output_sha256", ""))

    replay: CallReplay
    try:
        result: ToolCallResult = mcp.call_tool(tool_name, arguments)
    except McpRpcError as exc:
        replay = CallReplay(
            tool_name=tool_name,
            arguments=arguments,
            expected_sha256=expected,
            actual_sha256=None,
            matched=False,
            error=f"mcp rpc error code={exc.code}: {exc}",
        )
        return (
            VerifierAction(
                case_id=finding.case_id,
                action="rejected",
                finding_id=finding.finding_id,
                reason=replay.error or "tool re-run failed",
            ),
            replay,
        )

    matched = result.output_sha256 == expected
    replay = CallReplay(
        tool_name=tool_name,
        arguments=arguments,
        expected_sha256=expected,
        actual_sha256=result.output_sha256,
        matched=matched,
    )
    if matched:
        return (
            VerifierAction(
                case_id=finding.case_id,
                action="approved",
                finding_id=finding.finding_id,
                reason="tool re-run output_sha256 matches audit log",
            ),
            replay,
        )
    # Drift: re-run produced different output. Downgrade rather
    # than reject — the underlying evidence path is still real, but
    # confidence drops a tier.
    return (
        VerifierAction(
            case_id=finding.case_id,
            action="downgraded",
            finding_id=finding.finding_id,
            reason=(
                f"tool re-run output_sha256 drift "
                f"(expected={expected[:12]}…, got={result.output_sha256[:12]}…)"
            ),
        ),
        replay,
    )


def verify_findings(
    findings: list[Finding],
    *,
    mcp: McpClient,
    tool_call_index: dict[str, dict[str, Any]],
) -> list[tuple[Finding, VerifierAction, CallReplay | None]]:
    """Verify a batch of findings. Returns aligned (finding, action, replay) tuples.

    Uses the same ``mcp`` client for every re-run, serializing the
    calls. Spec #2 §8.1 budgets this stage at ~30s per finding;
    parallel re-runs are a future optimization.
    """
    out: list[tuple[Finding, VerifierAction, CallReplay | None]] = []
    for finding in findings:
        action, replay = reverify_finding(
            finding, mcp=mcp, tool_call_index=tool_call_index
        )
        out.append((finding, action, replay))
    return out


def downgrade_confidence(finding: Finding) -> Finding:
    """Drop confidence one tier per the verifier's downgrade ladder.

    CONFIRMED → INFERRED → HYPOTHESIS. HYPOTHESIS stays HYPOTHESIS
    (further drift is handled by rejecting the Finding outright at
    the verifier level).
    """
    ladder = {
        "CONFIRMED": "INFERRED",
        "INFERRED": "HYPOTHESIS",
        "HYPOTHESIS": "HYPOTHESIS",
    }
    new_confidence = ladder.get(finding.confidence, finding.confidence)
    if new_confidence == finding.confidence:
        return finding
    # Pydantic v2 frozen models: ``model_copy`` for safe mutation.
    return finding.model_copy(update={"confidence": new_confidence})


__all__ = [
    "CallReplay",
    "downgrade_confidence",
    "reverify_finding",
    "verify_findings",
]
