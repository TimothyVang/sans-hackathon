#!/usr/bin/env python3
"""autonomous-loop - drive the Find Evil queue in one Python process,
not via /loop wakeups.

Replaces the `/loop` pattern with a real harness:

  - Reads `memory/project_autonomous_queue.md` once per iteration.
  - Picks the highest-priority unblocked item (first `- [ ] **<name>**`).
  - Spawns `claude -p --permission-mode acceptEdits` headless to do
    the work end-to-end (read context, implement, test, commit, update
    the queue marking the item done).
  - Loops until: queue is exhausted after the optional --min-hours
    floor is satisfied, --max-hours wall-clock cap is hit, or a 429
    rate-limit is detected (clean halt with checkpoint).

Why not `/loop`?  /loop fires the same prompt every N seconds; each
firing is a fresh prompt that re-reads the queue and rediscovers
state.  The bookkeeping cost (commit + CHANGELOG + queue update +
re-arm) is comparable to the actual work in any iteration that's
not finding new bugs.  This harness keeps state across iterations
and stops cleanly when the queue is exhausted, rather than padding
cycles to satisfy a cron.

Auth: spawns the existing `claude` CLI as a subprocess, so it
inherits whatever auth `claude` already has - subscription via
~/.claude/ or CLAUDE_CODE_OAUTH_TOKEN env var per CLAUDE.md
"Credential modes (Amendment A1)".  No new ANTHROPIC_API_KEY
needed.

Usage:
    python scripts/autonomous-loop.py [--max-hours N] [--min-hours N] [--dry-run]

    --max-hours N            wall-clock cap (default: 24)
    --min-hours N            keep running/waiting for queue work until this floor
    --empty-sleep-seconds N  wait interval when the queue is empty before min-hours
    --dry-run                print what would be sent to claude, don't spawn
    --queue PATH             override the default queue file path
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

DEFAULT_QUEUE = (
    Path.home() / ".claude/projects/C--Users-newbi-Desktop-PUG-Projects-SANS-Hackathon/"
    "memory/project_autonomous_queue.md"
)

# Match `- [ ] **<title>**` (unblocked).  `- [x]` is done; skip.
UNBLOCKED_RE = re.compile(r"^\s*-\s+\[\s\]\s+\*\*([^*]+)\*\*\s*(.*?)$", re.MULTILINE)

# Hard-blocker section header (everything below this is user-required).
HARD_BLOCKERS_RE = re.compile(
    r"^###\s+Hard\s+blockers\s*\(require\s+user\)", re.MULTILINE
)

# Rate-limit signals from claude / Anthropic API stderr.  Anthropic
# emits two phrasings of the same condition: "usage limit reached"
# (system-side framing) and "You have reached your usage limit"
# (user-facing framing).  Catch both - smoke-regex-tests covers the
# distinction.
RATE_LIMIT_PATTERNS = (
    re.compile(r"\b429\b"),
    re.compile(r"rate.limit.exceeded", re.IGNORECASE),
    re.compile(r"usage limit reached", re.IGNORECASE),
    re.compile(r"reached your usage limit", re.IGNORECASE),
    re.compile(r"out of extra usage", re.IGNORECASE),
)


def _next_unblocked(queue_text: str) -> tuple[str, str] | None:
    """Returns (title, description) of the first unblocked item, or
    None if none.  Items below the Hard-blockers heading are skipped."""
    cutoff = HARD_BLOCKERS_RE.search(queue_text)
    if cutoff:
        queue_text = queue_text[: cutoff.start()]
    m = UNBLOCKED_RE.search(queue_text)
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def _is_rate_limited(stderr: str) -> bool:
    return any(p.search(stderr) for p in RATE_LIMIT_PATTERNS)


def _should_wait_for_queue_item(
    now: float, min_deadline: float, deadline: float
) -> bool:
    """True when queue exhaustion should wait instead of ending the loop."""
    return now < min_deadline and now < deadline


def _queue_empty_sleep_seconds(
    now: float, min_deadline: float, deadline: float, requested: float
) -> float:
    """Cap empty-queue sleep so min/max deadlines are not overshot by waiting."""
    return max(0.0, min(requested, min_deadline - now, deadline - now))


def _build_prompt(title: str, description: str, queue_path: Path) -> str:
    """Construct the per-iteration prompt for claude."""
    return f"""You are the SANS Find Evil autonomous build loop.

The queue file at `{queue_path}` lists work items.  The next
unblocked item is:

    {title}
    {description}

Your job, end-to-end, in this one session:

1. Read CLAUDE.md and the relevant per-subsystem spec/plan in
   docs/.  Apply Karpathy's 4 principles in CLAUDE.md.
2. Implement the item.  TDD where applicable.  Surgical changes only.
3. Verify: `cargo test --workspace --locked` + `cargo clippy
   --workspace --all-targets --locked -- -D warnings` + `ruff check .`
   + `ruff format --check .` - all green.
4. Commit locally with a Conventional Commits message
   (`feat(scope): ...`, `fix(scope): ...`, etc.).  Never push.
5. Update the queue file: change the item's `- [ ]` to `- [x]` and
   append the commit SHA + a one-line summary of what shipped.
6. Stop.  Do not start another item; the harness picks the next one.

Pause and ask if rate-limited, if a change would be destructive
(deleting files, force-pushing), or if a task takes more than 2x
its estimate.

Run `bash scripts/run-all-smokes.sh` before committing to confirm
the full L1 + lint+fmt gate set passes."""


def main() -> int:
    p = argparse.ArgumentParser(prog="autonomous-loop")
    p.add_argument("--max-hours", type=float, default=24.0)
    p.add_argument(
        "--min-hours",
        type=float,
        default=0.0,
        help="Minimum wall-clock floor. If the queue is empty before this, wait for more work instead of stopping.",
    )
    p.add_argument(
        "--empty-sleep-seconds",
        type=float,
        default=300.0,
        help="Sleep interval when the queue is empty before --min-hours is satisfied (default: 300).",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    p.add_argument(
        "--effort",
        choices=("low", "medium", "high", "xhigh", "max"),
        default="medium",
        help="claude --effort level per iteration (default: medium)",
    )
    args = p.parse_args()

    if args.max_hours <= 0:
        p.error("--max-hours must be greater than 0")
    if args.min_hours < 0:
        p.error("--min-hours must be >= 0")
    if args.min_hours > args.max_hours:
        p.error("--min-hours cannot exceed --max-hours")
    if args.empty_sleep_seconds <= 0:
        p.error("--empty-sleep-seconds must be greater than 0")

    if not args.queue.exists():
        print(f"error: queue file missing: {args.queue}", file=sys.stderr)
        return 1

    start = time.time()
    deadline = start + args.max_hours * 3600
    min_deadline = start + args.min_hours * 3600
    iteration = 0
    while time.time() < deadline:
        iteration += 1
        queue_text = args.queue.read_text(encoding="utf-8")
        item = _next_unblocked(queue_text)
        if item is None:
            now = time.time()
            if _should_wait_for_queue_item(now, min_deadline, deadline):
                sleep_for = _queue_empty_sleep_seconds(
                    now, min_deadline, deadline, args.empty_sleep_seconds
                )
                if args.dry_run:
                    print(
                        f"\n[autonomous-loop] DRY-RUN: queue exhausted before "
                        f"--min-hours={args.min_hours}; would wait "
                        f"{sleep_for:.0f}s for new queue items."
                    )
                    return 0
                print(
                    f"\n[autonomous-loop] iteration {iteration}: queue exhausted "
                    f"before --min-hours={args.min_hours}. Waiting "
                    f"{sleep_for:.0f}s for new queue items."
                )
                time.sleep(sleep_for)
                continue
            print(
                f"\n[autonomous-loop] iteration {iteration}: queue exhausted "
                "(only Hard blockers remain, or no unblocked work before the "
                "hard-blocker section). Stopping cleanly."
            )
            return 0

        title, description = item
        print(f"\n[autonomous-loop] iteration {iteration}: {title}")
        print(
            f"[autonomous-loop] elapsed: {(time.time() - start):.0f}s "
            f"of {args.max_hours * 3600:.0f}s budget"
        )
        prompt = _build_prompt(title, description, args.queue)

        if args.dry_run:
            print("--- DRY-RUN: would send to claude ---")
            print(prompt)
            print("--- end prompt ---")
            return 0

        if not shutil.which("claude"):
            print(
                "error: `claude` not on PATH.\n"
                "Install: https://docs.anthropic.com/en/docs/claude-code/install",
                file=sys.stderr,
            )
            return 127

        # Spawn claude headless. cwd=REPO so the agent has the right
        # working directory; permission-mode=acceptEdits so it can
        # edit files without per-tool prompts.
        result = subprocess.run(
            [
                "claude",
                "-p",
                "--permission-mode",
                "acceptEdits",
                "--effort",
                args.effort,
                prompt,
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=4 * 3600,  # per-item: 4hr cap
        )
        # Print claude's stdout to our stdout for the operator's log.
        print(result.stdout)
        if result.stderr:
            print("--- claude stderr ---", file=sys.stderr)
            print(result.stderr, file=sys.stderr)

        if _is_rate_limited(result.stderr):
            print(
                "\n[autonomous-loop] rate limit detected; halting cleanly. "
                "Re-run after the limit window resets - the queue file "
                "carries state forward, so we pick up where we left off."
            )
            return 2

        if result.returncode != 0:
            print(
                f"\n[autonomous-loop] iteration {iteration}: claude exited "
                f"non-zero ({result.returncode}). Halting cleanly to avoid "
                "burning cycles on a stuck task. Investigate manually and "
                "re-run when ready."
            )
            return 3

        # Loop back: re-read queue, pick next unblocked.

    print(f"\n[autonomous-loop] {args.max_hours}h budget exhausted; stopping.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
