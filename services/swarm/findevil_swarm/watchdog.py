"""Wall-clock watchdog — kills the swarm process tree after N hours.

Spec #1 §10.4. The watchdog is armed on supervisor startup and runs
as a daemon thread. If the supervisor hasn't exited by the deadline,
the watchdog sends SIGTERM to the whole process group, then SIGKILL
5 seconds later. This is the last line of defense when session_guard
misses a signal or Postgres gets wedged.

Kept deliberately small. Not a replacement for session_guard or
budget enforcement — a complementary belt-and-suspenders.
"""

from __future__ import annotations

import os
import signal
import threading
import time
from typing import Optional

DEFAULT_DEADLINE_SECONDS = 8 * 60 * 60  # 8 hours per Spec #1 §10.4


class Watchdog:
    """Single-shot wall-clock killer."""

    def __init__(
        self,
        deadline_seconds: int = DEFAULT_DEADLINE_SECONDS,
        *,
        on_fire: Optional[callable] = None,  # type: ignore[type-arg]
    ) -> None:
        if deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")
        self.deadline_seconds = deadline_seconds
        self.on_fire = on_fire
        self._thread: Optional[threading.Thread] = None
        self._cancel = threading.Event()
        self._started_at: Optional[float] = None
        self._fired = threading.Event()

    def arm(self) -> None:
        """Start the watchdog thread. Idempotent."""
        if self._thread is not None:
            return
        self._started_at = time.time()
        self._thread = threading.Thread(
            target=self._run, name="swarm-watchdog", daemon=True
        )
        self._thread.start()

    def cancel(self) -> None:
        """Stop the watchdog without firing."""
        self._cancel.set()

    def seconds_remaining(self) -> float:
        """How many seconds until the watchdog would fire."""
        if self._started_at is None:
            return self.deadline_seconds
        elapsed = time.time() - self._started_at
        return max(0.0, self.deadline_seconds - elapsed)

    @property
    def fired(self) -> bool:
        return self._fired.is_set()

    def _run(self) -> None:
        # Wait up to the deadline or until cancelled.
        if self._cancel.wait(self.deadline_seconds):
            return  # cancelled before firing
        self._fired.set()
        if self.on_fire is not None:
            try:
                self.on_fire()
            except Exception:  # nosec - callback must not crash the watchdog
                pass
        _signal_process_group()


def _signal_process_group() -> None:
    """Send SIGTERM to the current process group, then SIGKILL 5s later.

    Windows has no process groups so we fall back to ``os._exit(137)``
    on Windows — the supervisor in production runs in WSL2 anyway.
    """
    try:
        pgid = os.getpgrp()
    except (AttributeError, OSError):
        # Windows path.
        os._exit(137)  # 137 = 128 + SIGKILL, semantically "killed by watchdog"

    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return

    # Give subprocesses 5s to shut down cleanly.
    time.sleep(5)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


__all__ = ["Watchdog", "DEFAULT_DEADLINE_SECONDS"]
