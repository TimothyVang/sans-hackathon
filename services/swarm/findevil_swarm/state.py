"""Build swarm shared state types.

Defines the canonical ``SwarmState`` ``TypedDict`` that ``PostgresSaver``
checkpoints between supervisor nodes, plus the three Pydantic models the
swarm's pipeline produces.

Reference: Spec #1 §4 (State schema) and Amendment A1 (Option B — no USD
budget fields; rate-limit handling is session-based).
"""

from __future__ import annotations

import operator
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypedDict

# ---------------------------------------------------------------------------
# PRSpec — the atomic unit of work the supervisor dispatches.
# Parsed from BUILD_PLAN_v2.md week sections by plan_parser.py.
# ---------------------------------------------------------------------------


class PRSpec(BaseModel):
    """One self-contained unit of work a single worker ships as a draft PR.

    Week 2 example from BUILD_PLAN_v2.md §7:
        PRSpec(
            pr_id="week2-rust-case-open-tool",
            week=2,
            language="rust",
            title="Add case_open MCP tool with SHA-256 image verify",
            description=...,  # full task description from the week section
            files_expected=[
                "services/mcp/src/tools/case_open.rs",
                "services/mcp/tests/tool_smoke.rs",
            ],
            l1_command="cargo test -p findevil-mcp --test tool_smoke",
            token_ceiling=500_000,
            max_turns=40,
            depends_on=[],
        )
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pr_id: str = Field(..., min_length=1)
    week: int = Field(..., ge=1, le=8)
    language: str = Field(..., pattern=r"^(rust|python|typescript)$")
    title: str = Field(..., min_length=1, max_length=72)
    description: str = Field(..., min_length=1)
    files_expected: list[str] = Field(default_factory=list)
    l1_command: str = Field(..., min_length=1)
    token_ceiling: int = Field(default=500_000, ge=10_000)
    max_turns: int = Field(default=40, ge=1, le=100)
    depends_on: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# CriticVerdict — what the critic subagent returns after reviewing a
# worker's diff + L1 output.
# ---------------------------------------------------------------------------


class CriticVerdict(BaseModel):
    """Critic output. Must be structured JSON; unstructured → treat as REJECT."""

    model_config = ConfigDict(extra="forbid")

    pr_id: str
    decision: str = Field(..., pattern=r"^(APPROVE|REJECT)$")
    reason: str = Field(..., min_length=1, max_length=2000)
    token_count_input: int = Field(..., ge=0)
    token_count_output: int = Field(..., ge=0)
    l1_exit_code: int
    diff_line_count: int = Field(..., ge=0)


# ---------------------------------------------------------------------------
# NightlyReport — emitted once per supervisor run by collect_node.
# Persisted to logs/swarm/{date}-{run_id}.jsonl for morning triage.
# Amendment A1: no USD fields; session-based throughput only.
# ---------------------------------------------------------------------------


class NightlyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str  # ISO-8601 date (YYYY-MM-DD); UTC by convention
    week: int = Field(..., ge=1, le=8)
    run_id: str
    prs_opened: list[str] = Field(default_factory=list)
    prs_rejected: list[str] = Field(default_factory=list)
    wall_clock_seconds: int = Field(..., ge=0)
    session_halt_reason: str | None = None  # set when session_guard halted us
    workers_dispatched: int = Field(..., ge=0)
    critic_verdicts: int = Field(..., ge=0)


# ---------------------------------------------------------------------------
# SwarmState — the DAG state object persisted by PostgresSaver.
#
# Reducer rules (non-negotiable; parallel dispatch_node writes depend on them):
#   - *_pr_ids / critic_verdicts use operator.add: append-only, no overwrite.
#   - Singleton fields (nightly_report, session_halted, wall_clock_start_ts)
#     use last-write; only supervisor nodes write them, never workers.
#   - pr_specs and week are set once in plan_node and treated as immutable.
# ---------------------------------------------------------------------------


class SwarmState(TypedDict, total=False):
    # Set once in plan_node.
    week: int
    run_id: str
    pr_specs: list[PRSpec]

    # Append-only across parallel workers.
    dispatched_pr_ids: Annotated[list[str], operator.add]
    completed_pr_ids: Annotated[list[str], operator.add]
    rejected_pr_ids: Annotated[list[str], operator.add]
    critic_verdicts: Annotated[list[CriticVerdict], operator.add]

    # Session-based halt signal (Amendment A1; replaces USD budget_exhausted).
    # Supervisor-only write.
    session_halted: bool
    session_halt_reason: str | None

    # Dry-run gate outcome — supervisor-only write.
    dry_run_gate_passed: bool
    dry_run_gate_pr_id: str | None

    # Watchdog anchor.
    wall_clock_start_ts: int  # Unix epoch seconds, UTC

    # Final night report (collect_node-only write).
    nightly_report: NightlyReport | None
