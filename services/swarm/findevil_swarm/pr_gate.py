"""Dry-run gate — dispatch first PR, observe CI, then release or pause.

Spec #1 §7.3. A misconfigured swarm can open 10 broken PRs in 20
minutes. One wrong PR is recoverable; ten are not. The gate runs the
first ``PRSpec`` from the night, polls GHA CI on the resulting PR,
and only releases the remaining PRs when both the critic APPROVEd
and CI turned green.

This module is intentionally stateless — all state lives in
``SwarmState.dry_run_gate_passed``. ``pr_gate.poll_ci_until_result``
is the only side-effecting function.
"""

from __future__ import annotations

import subprocess
import time

from findevil_swarm.state import SwarmState

_POLL_INTERVAL_SECONDS = 60
_POLL_TIMEOUT_SECONDS = 30 * 60  # 30 minutes


def has_run(state: SwarmState) -> bool:
    """True if the gate has already been evaluated (pass or fail)."""
    return state.get("dry_run_gate_passed") is not None


def should_release_rest(state: SwarmState) -> bool:
    """True if the remaining PRs may be dispatched."""
    return bool(state.get("dry_run_gate_passed", False))


def poll_ci_until_result(
    pr_number: int,
    *,
    poll_interval: int = _POLL_INTERVAL_SECONDS,
    timeout: int = _POLL_TIMEOUT_SECONDS,
    gh_cmd: str = "gh",
) -> str | None:
    """Poll ``gh pr checks <N>`` until all checks are success|failure|timeout.

    Returns:
      * ``"success"`` — every required check passed
      * ``"failure"`` — at least one required check failed
      * ``"timeout"`` — polling exceeded ``timeout``
      * ``None``     — polling raised an unexpected subprocess error

    ``gh_cmd`` is injectable for tests.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = subprocess.run(
                [gh_cmd, "pr", "checks", str(pr_number), "--json", "status,conclusion"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

        if result.returncode != 0:
            # PR checks may take a few seconds to register. Retry.
            time.sleep(poll_interval)
            continue

        outcome = _summarize_checks(result.stdout)
        if outcome in ("success", "failure"):
            return outcome
        time.sleep(poll_interval)
    return "timeout"


def _summarize_checks(stdout: str) -> str | None:
    """Parse ``gh pr checks --json`` output to a single verdict.

    Returns ``"success"`` if every check completed with conclusion
    ``SUCCESS``, ``"failure"`` if any completed with ``FAILURE`` /
    ``CANCELLED`` / ``TIMED_OUT``, or ``None`` if any are still running.
    """
    import json

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None

    all_done = True
    for check in data:
        status = (check.get("status") or "").upper()
        conclusion = (check.get("conclusion") or "").upper()
        if status != "COMPLETED":
            all_done = False
            continue
        if conclusion in ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"):
            return "failure"
        if conclusion not in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            all_done = False
    return "success" if all_done else None


__all__ = ["has_run", "poll_ci_until_result", "should_release_rest"]
