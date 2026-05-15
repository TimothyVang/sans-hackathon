#!/usr/bin/env python3
"""autonomous-loop-smoke - CLI-level checks for the queue driver.

The smoke uses temporary synthetic queues and a PATH that deliberately omits
`claude`. This keeps it local-only while proving dry-run and empty-queue timing
paths do not consume Claude usage or require credentials.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AUTO_LOOP = REPO / "scripts" / "autonomous-loop.py"


def _run_autonomous_loop(
    args: list[str], path_dir: Path
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = str(path_dir)
    return subprocess.run(
        [sys.executable, str(AUTO_LOOP), *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _check(label: str, condition: bool, details: str, failures: list[str]) -> None:
    marker = "OK  " if condition else "FAIL"
    print(f"  [{marker}] {label}")
    if not condition:
        print(f"         {details}")
        failures.append(f"{label}: {details}")


def main() -> int:
    print("=" * 60)
    print("Find Evil! - autonomous-loop-smoke")
    print("=" * 60)
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        no_claude_path = root / "no-claude-on-path"
        no_claude_path.mkdir()

        work_queue = root / "queue.md"
        work_queue.write_text(
            "### Finish-project queue for 99% DFIR autonomy (unblocked)\n\n"
            "- [ ] **Synthetic loop item** - dry-run only.\n\n"
            "### Hard blockers (require user)\n\n"
            "- [ ] **External approval** - requires user.\n",
            encoding="utf-8",
        )
        dry = _run_autonomous_loop(
            [
                "--queue",
                str(work_queue),
                "--min-hours",
                "8",
                "--max-hours",
                "8",
                "--empty-sleep-seconds",
                "1",
                "--dry-run",
            ],
            no_claude_path,
        )
        dry_output = dry.stdout + dry.stderr
        _check(
            "8h dry-run accepts synthetic queue without claude on PATH",
            dry.returncode == 0
            and "Synthetic loop item" in dry.stdout
            and "DRY-RUN: would send to claude" in dry.stdout
            and "`claude` not on PATH" not in dry_output,
            f"exit={dry.returncode} output={dry_output!r}",
            failures,
        )

        empty_queue = root / "empty-queue.md"
        empty_queue.write_text(
            "### Finish-project queue for 99% DFIR autonomy (unblocked)\n\n"
            "- [x] **Done item** - already complete.\n\n"
            "### Hard blockers (require user)\n\n"
            "- [ ] **External approval** - requires user.\n",
            encoding="utf-8",
        )
        empty = _run_autonomous_loop(
            [
                "--queue",
                str(empty_queue),
                "--min-hours",
                "0.00005",
                "--max-hours",
                "0.0001",
                "--empty-sleep-seconds",
                "0.05",
            ],
            no_claude_path,
        )
        empty_output = empty.stdout + empty.stderr
        _check(
            "tiny empty-queue run waits before min-hours then stops cleanly",
            empty.returncode == 0
            and "queue exhausted before --min-hours" in empty.stdout
            and "Stopping cleanly" in empty.stdout
            and "`claude` not on PATH" not in empty_output,
            f"exit={empty.returncode} output={empty_output!r}",
            failures,
        )

    print()
    print("=" * 60)
    if not failures:
        print("OK - all autonomous-loop smoke cases pass.")
        print("=" * 60)
        return 0

    print(f"FAIL - {len(failures)} autonomous-loop smoke case(s) failed.")
    for failure in failures:
        print(f"  - {failure}")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
