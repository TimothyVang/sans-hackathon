"""CLI entry point for the build swarm.

Spec #1 §3.1 Task 16 + Amendment A1.

Subcommands:
  * ``findevil-swarm run --week N``         — execute one nightly run
  * ``findevil-swarm run --week auto``      — resolve week from ISO date
  * ``findevil-swarm run --resume``         — resume last unfinished run
  * ``findevil-swarm status``               — print last summary + PRs

Flags:
  * ``--dry-run-gate``     dispatch first PR only; rest gated on CI
  * ``--mock-workers``     don't invoke claude CLI; exercise the pipeline
  * ``--langgraph``        use real LangGraph StateGraph + PostgresSaver
  * ``--week-start-date``  override week-0 anchor date for --week auto
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

from findevil_swarm.night_report import log_paths_for
from findevil_swarm.supervisor import (
    DEFAULT_LOGS_DIR,
    DEFAULT_PLANS_DIR,
    DEFAULT_POSTGRES_CONN,
    SupervisorConfig,
    run_supervisor,
)

WEEK_1_START = date(2026, 4, 22)  # Apr 22 per BUILD_PLAN_v2 §7


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return _cmd_run(args)
    if args.command == "status":
        return _cmd_status(args)
    parser.error(f"unknown command: {args.command}")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="findevil-swarm")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Execute one nightly supervisor run")
    run.add_argument(
        "--week",
        default="auto",
        help='Week number 1-8 or "auto" (default). "auto" resolves via today\'s date.',
    )
    run.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: cwd)",
    )
    run.add_argument(
        "--logs-dir",
        type=Path,
        default=DEFAULT_LOGS_DIR,
        help=f"Logs directory (default: {DEFAULT_LOGS_DIR})",
    )
    run.add_argument(
        "--plans-dir",
        type=Path,
        default=DEFAULT_PLANS_DIR,
        help=f"Plans directory (default: {DEFAULT_PLANS_DIR})",
    )
    run.add_argument(
        "--postgres-conn",
        default=os.environ.get("POSTGRES_CONN_STRING", DEFAULT_POSTGRES_CONN),
        help="Postgres conn string (default: env POSTGRES_CONN_STRING or local)",
    )
    run.add_argument(
        "--dry-run-gate",
        action="store_true",
        default=True,
        help="Dispatch first PR only; release rest on green CI (default: on)",
    )
    run.add_argument(
        "--no-dry-run-gate",
        dest="dry_run_gate",
        action="store_false",
        help="Disable the dry-run gate (dangerous; all PRs dispatch at once)",
    )
    run.add_argument(
        "--mock-workers",
        action="store_true",
        help="Don't invoke claude CLI — dry-run workers + auto-approve critic",
    )
    run.add_argument(
        "--langgraph",
        action="store_true",
        help="Use real LangGraph StateGraph + PostgresSaver (requires Docker Postgres)",
    )
    run.add_argument(
        "--week-start-date",
        default="",
        help=f"Override week-1 anchor date for --week auto (default: {WEEK_1_START.isoformat()})",
    )

    stat = sub.add_parser("status", help="Print last run summary + open PRs")
    stat.add_argument(
        "--logs-dir",
        type=Path,
        default=DEFAULT_LOGS_DIR,
    )

    return p


def _cmd_run(args: argparse.Namespace) -> int:
    week = _resolve_week(args.week, args.week_start_date)
    run_id = f"swarm-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"

    config = SupervisorConfig(
        repo=args.repo.resolve(),
        week=week,
        run_id=run_id,
        logs_dir=args.logs_dir,
        plans_dir=args.plans_dir,
        postgres_conn=args.postgres_conn,
        dry_run_gate=args.dry_run_gate,
        mock_workers=args.mock_workers,
    )

    print(
        f"[findevil-swarm] run_id={run_id} week={week} "
        f"mock_workers={args.mock_workers} langgraph={args.langgraph}",
        file=sys.stderr,
    )

    try:
        report = run_supervisor(config, use_langgraph=args.langgraph)
    except KeyboardInterrupt:
        print("[findevil-swarm] interrupted by user", file=sys.stderr)
        return 130

    print(
        f"[findevil-swarm] done. prs_opened={len(report.prs_opened)} "
        f"prs_rejected={len(report.prs_rejected)} "
        f"wall_clock_s={report.wall_clock_seconds} "
        f"halt_reason={report.session_halt_reason or 'none'}",
        file=sys.stderr,
    )
    # Exit codes:
    #   0 = run completed cleanly
    #   2 = session halt (rate-limit / session-expiry)
    #   3 = no PRs merged and no halt (stuck somewhere)
    if report.session_halt_reason:
        return 2
    if not report.prs_opened and not report.prs_rejected:
        return 3
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    logs_dir: Path = args.logs_dir
    if not logs_dir.is_dir():
        print(f"[findevil-swarm] no logs dir at {logs_dir}", file=sys.stderr)
        return 1
    summaries = sorted(logs_dir.glob("*-summary.json"))
    if not summaries:
        print(f"[findevil-swarm] no summary files in {logs_dir}", file=sys.stderr)
        return 1
    latest = summaries[-1]
    print(f"--- latest summary: {latest.name} ---")
    print(latest.read_text(encoding="utf-8"))
    return 0


def _resolve_week(week_flag: str, week_start_date: str) -> int:
    if week_flag != "auto":
        try:
            n = int(week_flag)
        except ValueError:
            raise SystemExit(f"--week expected int or 'auto', got {week_flag!r}")
        if not 1 <= n <= 8:
            raise SystemExit(f"--week must be 1..8, got {n}")
        return n
    anchor = (
        date.fromisoformat(week_start_date) if week_start_date else WEEK_1_START
    )
    days_since = (date.today() - anchor).days
    if days_since < 0:
        return 1
    week = max(1, min(8, math.ceil((days_since + 1) / 7)))
    return week


if __name__ == "__main__":
    raise SystemExit(main())
