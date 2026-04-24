"""Tests for services/swarm/findevil_swarm/state.py schema contracts.

Spec #1 §4 + §11 Acceptance Criteria — Pydantic rules enforce the
reducer contract. Parallel dispatch_node writes to *_pr_ids rely on
operator.add semantics at the typing level; the Pydantic constraints
here guard against silent data corruption (e.g. unknown decision
strings, negative token counts, bad language values).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from findevil_swarm.state import CriticVerdict, NightlyReport, PRSpec, SwarmState


class TestPRSpec:
    def test_minimal_valid_spec_builds(self) -> None:
        spec = PRSpec(
            pr_id="week2-rust-case-open-tool",
            week=2,
            language="rust",
            title="Add case_open MCP tool with SHA-256 image verify",
            description="Implement case_open per Spec #2 §6",
            files_expected=[
                "services/mcp/src/tools/case_open.rs",
                "services/mcp/tests/tool_smoke.rs",
            ],
            l1_command="cargo test -p findevil-mcp --test tool_smoke",
        )
        assert spec.token_ceiling == 500_000  # default
        assert spec.max_turns == 40  # default
        assert spec.depends_on == []

    def test_spec_is_frozen(self) -> None:
        spec = PRSpec(
            pr_id="x",
            week=1,
            language="python",
            title="t",
            description="d",
            l1_command="pytest",
        )
        with pytest.raises(ValidationError):
            spec.title = "mutated"  # type: ignore[misc]

    def test_rejects_unknown_language(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PRSpec(
                pr_id="x",
                week=1,
                language="cobol",  # not allowed
                title="t",
                description="d",
                l1_command="cobc t.cob",
            )
        assert "pattern" in str(exc.value).lower()

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            PRSpec(  # type: ignore[call-arg]
                pr_id="x",
                week=1,
                language="rust",
                title="t",
                description="d",
                l1_command="c",
                rogue_field="nope",
            )

    def test_week_bounds(self) -> None:
        for bad_week in (0, 9, -1, 100):
            with pytest.raises(ValidationError):
                PRSpec(
                    pr_id="x",
                    week=bad_week,
                    language="rust",
                    title="t",
                    description="d",
                    l1_command="c",
                )

    def test_title_length_cap(self) -> None:
        # Long titles break gh pr create --title rendering.
        with pytest.raises(ValidationError):
            PRSpec(
                pr_id="x",
                week=1,
                language="rust",
                title="x" * 73,
                description="d",
                l1_command="c",
            )

    def test_token_ceiling_floor(self) -> None:
        with pytest.raises(ValidationError):
            PRSpec(
                pr_id="x",
                week=1,
                language="rust",
                title="t",
                description="d",
                l1_command="c",
                token_ceiling=9_999,  # < 10_000 minimum
            )


class TestCriticVerdict:
    def test_approve_path(self) -> None:
        v = CriticVerdict(
            pr_id="x",
            decision="APPROVE",
            reason="clean diff; tests green",
            token_count_input=1200,
            token_count_output=80,
            l1_exit_code=0,
            diff_line_count=42,
        )
        assert v.decision == "APPROVE"

    def test_reject_path(self) -> None:
        v = CriticVerdict(
            pr_id="x",
            decision="REJECT",
            reason="L1 exit 1",
            token_count_input=2000,
            token_count_output=0,
            l1_exit_code=1,
            diff_line_count=0,
        )
        assert v.decision == "REJECT"

    def test_unknown_decision_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CriticVerdict(
                pr_id="x",
                decision="MAYBE",  # type: ignore[arg-type]
                reason="r",
                token_count_input=0,
                token_count_output=0,
                l1_exit_code=0,
                diff_line_count=0,
            )

    def test_negative_token_counts_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CriticVerdict(
                pr_id="x",
                decision="APPROVE",
                reason="r",
                token_count_input=-1,
                token_count_output=0,
                l1_exit_code=0,
                diff_line_count=0,
            )


class TestNightlyReport:
    def test_basic_report(self) -> None:
        r = NightlyReport(
            date="2026-04-23",
            week=1,
            run_id="swarm-2026-04-23-w1",
            prs_opened=["pr-a", "pr-b"],
            prs_rejected=["pr-c"],
            wall_clock_seconds=3600,
            workers_dispatched=3,
            critic_verdicts=3,
        )
        assert r.session_halt_reason is None

    def test_halt_reason_round_trips(self) -> None:
        r = NightlyReport(
            date="2026-04-23",
            week=1,
            run_id="swarm-2026-04-23-w1",
            prs_opened=[],
            prs_rejected=[],
            wall_clock_seconds=120,
            workers_dispatched=0,
            critic_verdicts=0,
            session_halt_reason="claude CLI returned 429 (usage limit reached)",
        )
        assert r.session_halt_reason is not None
        assert "429" in r.session_halt_reason


class TestSwarmState:
    """SwarmState is a TypedDict, so we validate structural shape, not Pydantic rules."""

    def test_shape_matches_spec(self) -> None:
        required = {
            "week",
            "run_id",
            "pr_specs",
            "dispatched_pr_ids",
            "completed_pr_ids",
            "rejected_pr_ids",
            "critic_verdicts",
            "session_halted",
            "session_halt_reason",
            "dry_run_gate_passed",
            "dry_run_gate_pr_id",
            "wall_clock_start_ts",
            "nightly_report",
        }
        actual = set(SwarmState.__annotations__.keys())
        assert required == actual, f"missing: {required - actual} extra: {actual - required}"

    def test_option_b_has_no_usd_fields(self) -> None:
        """Amendment A1: SwarmState must not carry USD budget fields."""
        banned = {"spend_usd_cumulative", "budget_exhausted"}
        actual = set(SwarmState.__annotations__.keys())
        intersect = banned & actual
        assert intersect == set(), f"Amendment A1 violation: {intersect}"
