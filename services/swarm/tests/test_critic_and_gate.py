"""Tests for critic.py, pr_gate.py, watchdog.py."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from findevil_swarm.critic import _parse_critic_json, pre_check, review
from findevil_swarm.pr_gate import (
    _summarize_checks,
    has_run,
    should_release_rest,
)
from findevil_swarm.state import PRSpec
from findevil_swarm.watchdog import DEFAULT_DEADLINE_SECONDS, Watchdog
from findevil_swarm.workers.base_worker import WorkerResult


@pytest.fixture()
def spec() -> PRSpec:
    return PRSpec(
        pr_id="pr-001",
        week=2,
        language="python",
        title="x",
        description="d",
        files_expected=["a/b.py"],
        l1_command="pytest",
    )


def _result(**kwargs: object) -> WorkerResult:
    defaults = dict(
        pr_id="pr-001",
        branch_name="swarm/week-2-pr-001",
        worktree_path=Path("/tmp/wt"),
        claude_exit_code=0,
        claude_stdout="",
        claude_stderr="",
        l1_exit_code=0,
        l1_stdout="",
        l1_stderr="",
        diff_line_count=100,
        token_count_input=0,
        token_count_output=0,
        no_progress_killed=False,
        wall_clock_seconds=10,
        jsonl_sidecar_path=None,
    )
    defaults.update(kwargs)
    return WorkerResult(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Critic pre-checks.
# ---------------------------------------------------------------------------


class TestPreCheck:
    def test_clean_result_returns_none(self, spec: PRSpec) -> None:
        assert pre_check(spec, _result()) is None

    def test_l1_failure_rejects(self, spec: PRSpec) -> None:
        v = pre_check(spec, _result(l1_exit_code=1, l1_stderr="boom"))
        assert v is not None
        assert v.decision == "REJECT"
        assert "L1" in v.reason

    def test_empty_diff_rejects(self, spec: PRSpec) -> None:
        v = pre_check(spec, _result(diff_line_count=0))
        assert v is not None
        assert v.decision == "REJECT"
        assert "empty diff" in v.reason.lower()

    def test_no_progress_rejects(self, spec: PRSpec) -> None:
        v = pre_check(
            spec,
            _result(no_progress_killed=True, diff_line_count=5),
        )
        assert v is not None
        assert v.decision == "REJECT"
        assert "no_progress" in v.reason.lower()

    def test_claude_exit_nonzero_rejects(self, spec: PRSpec) -> None:
        v = pre_check(spec, _result(claude_exit_code=2))
        assert v is not None
        assert v.decision == "REJECT"


class TestParseCriticJson:
    def test_parses_clean_json(self) -> None:
        r = _parse_critic_json('{"decision": "APPROVE", "reason": "green"}')
        assert r is not None
        assert r["decision"] == "APPROVE"

    def test_parses_json_with_surrounding_text(self) -> None:
        r = _parse_critic_json(
            'Some preamble\n{"decision": "REJECT", "reason": "bad"}\nSome postamble'
        )
        assert r is not None
        assert r["decision"] == "REJECT"

    def test_rejects_invalid_decision_value(self) -> None:
        assert _parse_critic_json('{"decision": "MAYBE", "reason": "unsure"}') is None

    def test_rejects_non_json(self) -> None:
        assert _parse_critic_json("looks like a decision but isn't") is None

    def test_rejects_missing_fields(self) -> None:
        assert _parse_critic_json('{"decision": "APPROVE"}') is not None  # reason defaults to ""


class TestReviewDryRun:
    def test_dry_run_approves_clean_result(self, spec: PRSpec, tmp_path: Path) -> None:
        verdict = review(spec=spec, result=_result(), repo=tmp_path, dry_run=True)
        assert verdict.decision == "APPROVE"
        assert verdict.pr_id == spec.pr_id

    def test_dry_run_rejects_bad_l1(self, spec: PRSpec, tmp_path: Path) -> None:
        verdict = review(
            spec=spec,
            result=_result(l1_exit_code=1, l1_stderr="boom"),
            repo=tmp_path,
            dry_run=True,
        )
        assert verdict.decision == "REJECT"


# ---------------------------------------------------------------------------
# pr_gate.
# ---------------------------------------------------------------------------


class TestGateHelpers:
    def test_has_run_reports_false_when_absent(self) -> None:
        from findevil_swarm.state import SwarmState

        state: SwarmState = {}
        assert has_run(state) is False

    def test_has_run_reports_true_when_set(self) -> None:
        from findevil_swarm.state import SwarmState

        state: SwarmState = {"dry_run_gate_passed": True}
        assert has_run(state) is True

    def test_should_release_requires_explicit_true(self) -> None:
        assert should_release_rest({}) is False
        assert should_release_rest({"dry_run_gate_passed": False}) is False
        assert should_release_rest({"dry_run_gate_passed": True}) is True


class TestSummarizeChecks:
    def test_all_success(self) -> None:
        data = '[{"status":"COMPLETED","conclusion":"SUCCESS"},{"status":"COMPLETED","conclusion":"SUCCESS"}]'
        assert _summarize_checks(data) == "success"

    def test_one_failure(self) -> None:
        data = '[{"status":"COMPLETED","conclusion":"SUCCESS"},{"status":"COMPLETED","conclusion":"FAILURE"}]'
        assert _summarize_checks(data) == "failure"

    def test_in_progress_returns_none(self) -> None:
        data = '[{"status":"IN_PROGRESS","conclusion":null}]'
        assert _summarize_checks(data) is None

    def test_skipped_counts_as_success(self) -> None:
        data = '[{"status":"COMPLETED","conclusion":"SKIPPED"}]'
        assert _summarize_checks(data) == "success"

    def test_cancelled_counts_as_failure(self) -> None:
        data = '[{"status":"COMPLETED","conclusion":"CANCELLED"}]'
        assert _summarize_checks(data) == "failure"

    def test_bad_json_returns_none(self) -> None:
        assert _summarize_checks("not json") is None


# ---------------------------------------------------------------------------
# Watchdog.
# ---------------------------------------------------------------------------


class TestWatchdog:
    def test_default_deadline_is_8_hours(self) -> None:
        assert DEFAULT_DEADLINE_SECONDS == 8 * 60 * 60

    def test_rejects_non_positive_deadline(self) -> None:
        with pytest.raises(ValueError):
            Watchdog(deadline_seconds=0)
        with pytest.raises(ValueError):
            Watchdog(deadline_seconds=-1)

    def test_cancel_before_fire_prevents_callback(self) -> None:
        fired = []
        w = Watchdog(deadline_seconds=1, on_fire=lambda: fired.append(True))
        w.arm()
        time.sleep(0.05)
        w.cancel()
        # Wait longer than deadline; callback should NOT have fired.
        time.sleep(1.2)
        assert w.fired is False
        assert fired == []

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason=(
            "On Windows the watchdog falls through to os._exit(137) "
            "(no process groups) which would terminate pytest itself. "
            "CI runs on Linux."
        ),
    )
    def test_fires_callback_on_deadline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fired = []
        signaled = []
        monkeypatch.setattr(
            "findevil_swarm.watchdog._signal_process_group",
            lambda: signaled.append(True),
        )
        w = Watchdog(deadline_seconds=1, on_fire=lambda: fired.append(True))
        w.arm()
        time.sleep(1.5)
        assert w.fired is True
        assert fired == [True]
        assert signaled == [True]

    def test_seconds_remaining_counts_down(self) -> None:
        w = Watchdog(deadline_seconds=10)
        assert w.seconds_remaining() == 10
        w.arm()
        try:
            time.sleep(0.05)
            remaining = w.seconds_remaining()
            assert remaining < 10 and remaining > 9
        finally:
            w.cancel()
