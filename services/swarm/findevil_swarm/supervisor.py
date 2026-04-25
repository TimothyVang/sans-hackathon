"""LangGraph supervisor — the top-level swarm orchestrator.

Spec #1 §3.1 Task 14 + §4 + Amendment A1. Compiles a StateGraph with
three nodes (``plan_node`` → ``dispatch_node`` → ``collect_node``)
checkpointed to PostgresSaver. Each nightly run = one thread ID
``swarm-week-{N}-{date}``. Supervisor re-opens the thread on
``--resume`` so laptop-sleep interruptions pick up where they left off.

Heavy lifting lives in the existing modules:
  * ``plan_parser`` produces the PRSpec list
  * ``worktree`` + ``workers.*`` execute each PR
  * ``critic`` gates each worker output
  * ``session_guard`` watches for rate-limit signals
  * ``watchdog`` enforces the 8-hour wall-clock ceiling
  * ``night_report`` writes the JSONL trail

This module only wires them together and provides the LangGraph entry
point ``build_graph()``.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date as date_cls
from pathlib import Path

from findevil_swarm import critic as critic_mod
from findevil_swarm import plan_parser, worktree
from findevil_swarm.night_report import emit_event, log_paths_for, write_summary
from findevil_swarm.pr_gate import should_release_rest
from findevil_swarm.session_guard import SessionLimitError
from findevil_swarm.state import NightlyReport, PRSpec, SwarmState
from findevil_swarm.watchdog import Watchdog
from findevil_swarm.workers import (
    PythonWorker,
    RustWorker,
    TypeScriptWorker,
    WorkerInput,
    WorkerResult,
)
from findevil_swarm.workers.base_worker import BaseWorker

# ---------------------------------------------------------------------------
# Configuration.
# ---------------------------------------------------------------------------

DEFAULT_LOGS_DIR = Path("logs/swarm")
DEFAULT_PLANS_DIR = Path("docs/superpowers/plans")
DEFAULT_POSTGRES_CONN = "postgresql://swarm:swarm-local-only@localhost:5432/swarm"


_LANGUAGE_TO_WORKER: dict[str, type[BaseWorker]] = {
    "rust": RustWorker,
    "python": PythonWorker,
    "typescript": TypeScriptWorker,
}


@dataclass(frozen=True)
class SupervisorConfig:
    """Runtime knobs the supervisor needs. Keep small — no secrets here."""

    repo: Path
    week: int
    run_id: str
    logs_dir: Path = DEFAULT_LOGS_DIR
    plans_dir: Path = DEFAULT_PLANS_DIR
    postgres_conn: str = DEFAULT_POSTGRES_CONN
    dry_run_gate: bool = True
    mock_workers: bool = False  # pass through to WorkerInput.dry_run
    wall_clock_deadline_s: int = 8 * 60 * 60
    # Injected for tests — production uses the default ``gh pr create`` call.
    gh_pr_create: Callable[[PRSpec, WorkerResult], int | None] | None = None


# ---------------------------------------------------------------------------
# Node implementations.
#
# These are plain Python functions that take SwarmState and return
# partial SwarmState dicts (the LangGraph reducer model). They do NOT
# import langgraph directly so this module remains unit-testable without
# Postgres or langgraph installed. ``build_graph`` wires them into a
# real StateGraph at the top level.
# ---------------------------------------------------------------------------


def plan_node(state: SwarmState, config: SupervisorConfig) -> SwarmState:
    """Parse this week's plans into PRSpecs and stamp the run ID."""
    event_log, _ = log_paths_for(config.logs_dir, date=_today_utc(), run_id=config.run_id)
    emit_event(
        event_log,
        run_id=config.run_id,
        component="supervisor",
        event="plan_start",
        week=config.week,
    )
    specs = plan_parser.parse_week(week=config.week, plans_dir=config.plans_dir)
    emit_event(
        event_log,
        run_id=config.run_id,
        component="supervisor",
        event="plan_parsed",
        pr_count=len(specs),
        pr_ids=[s.pr_id for s in specs],
    )
    return {
        "week": config.week,
        "run_id": config.run_id,
        "pr_specs": specs,
        "wall_clock_start_ts": int(time.time()),
        "session_halted": False,
        "session_halt_reason": None,
        "dry_run_gate_passed": False,
        "dry_run_gate_pr_id": None,
        "dispatched_pr_ids": [],
        "completed_pr_ids": [],
        "rejected_pr_ids": [],
        "critic_verdicts": [],
    }


def dispatch_node(state: SwarmState, config: SupervisorConfig) -> SwarmState:
    """Dispatch PRs — respecting the dry-run gate — and call critic on each."""
    event_log, _ = log_paths_for(config.logs_dir, date=_today_utc(), run_id=config.run_id)
    specs = state["pr_specs"]
    completed: list[str] = []
    rejected: list[str] = []
    verdicts: list = []
    dispatched: list[str] = []
    session_halted = False
    halt_reason: str | None = None

    gate_first_only = config.dry_run_gate and not should_release_rest(state)
    for i, spec in enumerate(specs):
        # Under dry_run_gate: only the first PR runs. If it comes back
        # with APPROVE + (eventually) green CI, a subsequent supervisor
        # invocation runs with dry_run_gate_passed=True and dispatches
        # the rest.
        if gate_first_only and i > 0:
            emit_event(
                event_log,
                run_id=config.run_id,
                component="supervisor",
                event="dispatch_halt",
                reason="dry_run_gate_pending",
                pending=[s.pr_id for s in specs[i:]],
            )
            break

        worker_cls = _LANGUAGE_TO_WORKER.get(spec.language, PythonWorker)
        worker = worker_cls()
        sidecar = config.logs_dir / "sidecars" / f"{spec.pr_id}-tool-calls.jsonl"
        inp = WorkerInput(
            pr_spec=spec,
            repo=config.repo,
            jsonl_sidecar_path=sidecar,
            dry_run=config.mock_workers,
        )
        emit_event(
            event_log,
            run_id=config.run_id,
            component="supervisor",
            event="worker_dispatch",
            pr_id=spec.pr_id,
            language=spec.language,
        )
        try:
            result = worker.execute(inp)
        except SessionLimitError as e:
            session_halted = True
            halt_reason = e.reason
            emit_event(
                event_log,
                run_id=config.run_id,
                component="supervisor",
                event="session_halt",
                pr_id=spec.pr_id,
                reason=e.reason,
            )
            break

        dispatched.append(spec.pr_id)

        # Critic.
        try:
            verdict = critic_mod.review(
                spec=spec,
                result=result,
                repo=config.repo,
                dry_run=config.mock_workers,
            )
        except SessionLimitError as e:
            session_halted = True
            halt_reason = e.reason
            emit_event(
                event_log,
                run_id=config.run_id,
                component="supervisor",
                event="session_halt",
                pr_id=spec.pr_id,
                reason=e.reason,
                stage="critic",
            )
            break
        verdicts.append(verdict)

        if verdict.decision == "APPROVE":
            # ``gh pr create --draft`` is injectable so tests can stub it.
            pr_number: int | None = None
            if config.gh_pr_create is not None:
                pr_number = config.gh_pr_create(spec, result)
            else:
                pr_number = _default_gh_pr_create(spec, result, config)
            completed.append(spec.pr_id)
            emit_event(
                event_log,
                run_id=config.run_id,
                component="supervisor",
                event="pr_opened",
                pr_id=spec.pr_id,
                branch=result.branch_name,
                gh_pr_number=pr_number,
            )
        else:
            rejected.append(spec.pr_id)
            # Clean up worktree + branch for a REJECT.
            worktree.remove(
                repo=config.repo,
                language=spec.language,
                pr_id=spec.pr_id,
                delete_branch=True,
            )
            emit_event(
                event_log,
                run_id=config.run_id,
                component="supervisor",
                event="pr_rejected",
                pr_id=spec.pr_id,
                reason=verdict.reason[:300],
            )

    # If we dispatched in gated-first-only mode, we aren't passing the gate
    # yet — that signal comes later from pr_gate.poll_ci_until_result
    # (invoked via main.py on the next invocation).
    update: SwarmState = {
        "dispatched_pr_ids": dispatched,
        "completed_pr_ids": completed,
        "rejected_pr_ids": rejected,
        "critic_verdicts": verdicts,
        "session_halted": session_halted,
    }
    if halt_reason is not None:
        update["session_halt_reason"] = halt_reason
    return update


def collect_node(state: SwarmState, config: SupervisorConfig) -> SwarmState:
    """Write NightlyReport + final JSONL event."""
    event_log, summary_log = log_paths_for(config.logs_dir, date=_today_utc(), run_id=config.run_id)

    start_ts = state.get("wall_clock_start_ts", int(time.time()))
    wall_clock_s = max(0, int(time.time()) - start_ts)

    report = NightlyReport(
        date=_today_utc(),
        week=state.get("week", config.week),
        run_id=state.get("run_id", config.run_id),
        prs_opened=state.get("completed_pr_ids", []),
        prs_rejected=state.get("rejected_pr_ids", []),
        wall_clock_seconds=wall_clock_s,
        session_halt_reason=state.get("session_halt_reason"),
        workers_dispatched=len(state.get("dispatched_pr_ids", [])),
        critic_verdicts=len(state.get("critic_verdicts", [])),
    )
    write_summary(summary_log, report)
    emit_event(
        event_log,
        run_id=config.run_id,
        component="supervisor",
        event="night_complete",
        prs_opened=len(report.prs_opened),
        prs_rejected=len(report.prs_rejected),
        wall_clock_s=wall_clock_s,
        session_halt_reason=report.session_halt_reason,
    )
    return {"nightly_report": report}


# ---------------------------------------------------------------------------
# Default ``gh pr create`` caller. Injectable via SupervisorConfig.
# ---------------------------------------------------------------------------


def _default_gh_pr_create(
    spec: PRSpec, result: WorkerResult, config: SupervisorConfig
) -> int | None:
    """Open a draft PR via ``gh``. Returns the PR number or None on failure."""
    if config.mock_workers:
        return None  # mock dispatch doesn't touch GitHub
    body = (
        f"## Auto-generated by find-evil swarm\n\n"
        f"- PR ID: `{spec.pr_id}`\n"
        f"- Week: {spec.week}\n"
        f"- Language: {spec.language}\n"
        f"- L1 exit code: {result.l1_exit_code}\n"
        f"- Diff lines: {result.diff_line_count}\n"
        f"- Wall-clock: {result.wall_clock_seconds}s\n\n"
        f"### Task description\n\n{spec.description[:3000]}\n"
    )
    # The branch was already pushed by base_worker (post-commit). Open
    # the PR against main.
    try:
        proc = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--draft",
                "--title",
                f"swarm: {spec.title}"[:72],
                "--body",
                body,
                "--base",
                "main",
                "--head",
                result.branch_name,
                "--label",
                "swarm-generated",
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(config.repo),
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    # gh pr create prints the PR URL; last /NNN is the number.
    url = proc.stdout.strip()
    try:
        return int(url.rsplit("/", 1)[-1])
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Entry point for production use — builds a LangGraph StateGraph.
# ---------------------------------------------------------------------------


def run_supervisor(
    config: SupervisorConfig,
    *,
    use_langgraph: bool = False,
) -> NightlyReport:
    """Run plan → dispatch → collect in-process, returning the NightlyReport.

    When ``use_langgraph=True``, the nodes are compiled into a real
    LangGraph StateGraph with PostgresSaver. When False (default — the
    pragmatic path for week 1), nodes are called directly. Both paths
    produce identical on-disk artifacts so tests + demos can exercise
    either.
    """
    watchdog = Watchdog(
        deadline_seconds=config.wall_clock_deadline_s,
    )
    watchdog.arm()
    try:
        state = _run_via_langgraph(config) if use_langgraph else _run_in_process(config)
        report = state.get("nightly_report")
        if report is None:
            # Defensive — collect_node always sets it.
            raise RuntimeError("collect_node did not set nightly_report")
        return report
    finally:
        watchdog.cancel()


def _run_in_process(config: SupervisorConfig) -> SwarmState:
    state: SwarmState = {}
    state.update(plan_node(state, config))
    state.update(dispatch_node(state, config))
    state.update(collect_node(state, config))
    return state


def _run_via_langgraph(config: SupervisorConfig) -> SwarmState:
    """Compile the StateGraph + PostgresSaver. Imported lazily."""
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.graph import END, StateGraph

    builder = StateGraph(SwarmState)
    builder.add_node("plan", lambda s: plan_node(s, config))
    builder.add_node("dispatch", lambda s: dispatch_node(s, config))
    builder.add_node("collect", lambda s: collect_node(s, config))
    builder.set_entry_point("plan")
    builder.add_edge("plan", "dispatch")
    builder.add_edge("dispatch", "collect")
    builder.add_edge("collect", END)

    with PostgresSaver.from_conn_string(config.postgres_conn) as saver:
        saver.setup()
        graph = builder.compile(checkpointer=saver)
        thread_id = f"swarm-week-{config.week}-{_today_utc()}-{config.run_id}"
        cfg = {"configurable": {"thread_id": thread_id}}
        final_state = graph.invoke({}, cfg)
        return final_state


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _today_utc() -> str:
    """Local supervisor run date — use actual UTC from os.environ if set for tests."""
    fake = os.environ.get("SWARM_FAKE_DATE")
    if fake:
        return fake
    return date_cls.fromtimestamp(time.time()).isoformat()


__all__ = [
    "DEFAULT_LOGS_DIR",
    "DEFAULT_PLANS_DIR",
    "DEFAULT_POSTGRES_CONN",
    "SupervisorConfig",
    "collect_node",
    "dispatch_node",
    "plan_node",
    "run_supervisor",
]
