"""Structured JSONL night-report emitter.

Spec #1 §10.1. Every supervisor, worker, and critic event lands in
``logs/swarm/{date}-{run_id}.jsonl`` — one JSON object per line,
ready for ``jq`` / ``grep`` triage in the morning.

Separately, the final summary NightlyReport is written to
``logs/swarm/{date}-{run_id}-summary.jsonl`` so ``swarm-status.sh``
can read it in one slurp.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from findevil_swarm.state import NightlyReport


def emit_event(
    log_path: Path,
    *,
    run_id: str,
    component: str,
    event: str,
    **fields: Any,
) -> None:
    """Append a single JSONL event record to ``log_path``.

    Always-present fields: ts (ISO-8601Z), run_id, component, event.
    Extra fields are event-specific.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "ts": _utc_iso(),
        "run_id": run_id,
        "component": component,
        "event": event,
    }
    record.update(fields)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def write_summary(summary_path: Path, report: NightlyReport) -> None:
    """Write the final NightlyReport to a single-line JSON file."""
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


def log_paths_for(logs_dir: Path, *, date: str, run_id: str) -> tuple[Path, Path]:
    """Return ``(event_log, summary_log)`` paths for a given run."""
    event_log = logs_dir / f"{date}-{run_id}.jsonl"
    summary_log = logs_dir / f"{date}-{run_id}-summary.json"
    return event_log, summary_log


def _utc_iso() -> str:
    """UTC ISO-8601 with trailing Z and millisecond precision."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


__all__ = ["emit_event", "write_summary", "log_paths_for"]
