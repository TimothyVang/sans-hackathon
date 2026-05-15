"""Deterministic replay artifacts and drift classification.

Track 3a keeps replay as a first-class, structured object while preserving
the legacy verifier ``replay_*`` fields used by existing scripts/reports.
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from findevil_agent.mcp_client import McpClient, McpRpcError, ToolCallResult

DriftClass = Literal[
    "exact_match",
    "material_drift",
    "replay_error",
    "missing_citation",
    "missing_audit_record",
]


class ReplayArtifact(BaseModel):
    """Typed replay evidence attached to verifier output and reports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "findevil.replay.v1"
    tool_call_id: str | None = None
    tool_name: str | None = None
    arguments_sha256: str | None = None
    expected_sha256: str | None = None
    actual_sha256: str | None = None
    matched: bool | None = None
    drift_class: DriftClass
    drift_reason: str
    error: str | None = None
    replay_tool_call_id: str | None = None
    wall_clock_ms: int | None = None


def canonical_sha256(value: Any) -> str:
    """SHA-256 of deterministic JSON for structured replay metadata."""

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_drift(
    *, expected_sha256: str | None, actual_sha256: str | None, error: str | None = None
) -> tuple[DriftClass, str]:
    """Classify replay outcome without severity escalation.

    Track 3b's policy changes intentionally do not live here; this only labels
    determinism state for the existing approve/downgrade/reject behavior.
    """

    if error:
        return "replay_error", error
    if expected_sha256 and actual_sha256 and expected_sha256 == actual_sha256:
        return "exact_match", "replay output_sha256 matches audit log"
    return "material_drift", "replay output_sha256 differs from audit log"


def missing_replay_artifact(
    *, tool_call_id: str | None, drift_class: DriftClass, reason: str
) -> ReplayArtifact:
    return ReplayArtifact(
        tool_call_id=tool_call_id,
        drift_class=drift_class,
        drift_reason=reason,
        error=reason,
        matched=False,
    )


def build_replay_artifact(
    *,
    tool_call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    expected_sha256: str,
    result: ToolCallResult | None,
    error: str | None = None,
) -> ReplayArtifact:
    actual = result.output_sha256 if result else None
    drift_class, drift_reason = classify_drift(
        expected_sha256=expected_sha256, actual_sha256=actual, error=error
    )
    return ReplayArtifact(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        arguments_sha256=canonical_sha256(arguments),
        expected_sha256=expected_sha256,
        actual_sha256=actual,
        matched=(actual == expected_sha256) if actual is not None else False,
        drift_class=drift_class,
        drift_reason=drift_reason,
        error=error,
        replay_tool_call_id=result.tool_call_id if result else None,
        wall_clock_ms=result.wall_clock_ms if result else None,
    )


@dataclass
class ReplayPool:
    """Small cache/concurrency helper for replaying cited tool calls.

    The pool is opt-in. Existing verifier paths remain serial unless callers
    supply a pool or use ``verify_findings(..., max_workers=N)``.
    """

    mcp: McpClient
    max_workers: int = 4
    _cache: dict[str, ToolCallResult] = field(default_factory=dict)
    _executor: ThreadPoolExecutor | None = None

    def cache_key(self, tool_name: str, arguments: dict[str, Any]) -> str:
        return canonical_sha256({"tool_name": tool_name, "arguments": arguments})

    def replay(
        self, tool_name: str, arguments: dict[str, Any], *, force_fresh: bool = False
    ) -> ToolCallResult:
        key = self.cache_key(tool_name, arguments)
        if not force_fresh and key in self._cache:
            return self._cache[key]
        result = self.mcp.call_tool(tool_name, arguments)
        self._cache[key] = result
        return result

    def submit(
        self, tool_name: str, arguments: dict[str, Any], *, force_fresh: bool = False
    ) -> Future[ToolCallResult]:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=max(1, self.max_workers))
        return self._executor.submit(self.replay, tool_name, arguments, force_fresh=force_fresh)

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None


def replay_tool_call(
    *,
    tool_call_id: str,
    record: dict[str, Any],
    mcp: McpClient,
    replay_pool: ReplayPool | None = None,
    force_fresh: bool = False,
) -> ReplayArtifact:
    """Replay one audit tool-call record and return a structured artifact."""

    tool_name = str(record.get("tool_name", ""))
    arguments = dict(record.get("arguments") or {})
    expected = str(record.get("output_sha256", ""))
    try:
        result = (
            replay_pool.replay(tool_name, arguments, force_fresh=force_fresh)
            if replay_pool is not None
            else mcp.call_tool(tool_name, arguments)
        )
    except McpRpcError as exc:
        return build_replay_artifact(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
            expected_sha256=expected,
            result=None,
            error=f"mcp rpc error code={exc.code}: {exc}",
        )
    except Exception as exc:
        return build_replay_artifact(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
            expected_sha256=expected,
            result=None,
            error=f"mcp replay error: {exc}",
        )
    return build_replay_artifact(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        arguments=arguments,
        expected_sha256=expected,
        result=result,
    )


__all__ = [
    "DriftClass",
    "ReplayArtifact",
    "ReplayPool",
    "build_replay_artifact",
    "canonical_sha256",
    "classify_drift",
    "missing_replay_artifact",
    "replay_tool_call",
]
