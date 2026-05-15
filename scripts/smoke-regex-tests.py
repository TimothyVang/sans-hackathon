#!/usr/bin/env python3
"""smoke-regex-tests - regression tests for the audit-smoke regexes.

The audit smokes (divergence-smoke, launcher-smoke, path-existence-
smoke) catch drift in the rest of the codebase, but the smokes
themselves have no automated regression coverage.  If a future
contributor breaks a regex (over-broad / over-narrow / typo), the
smoke would still report "all clean" while silently letting bugs
through.

This script imports each smoke module and runs synthetic
positive + negative cases against its key regexes.  Exits 0 if
all cases classify correctly, 1 if any case is wrong.

The test fixtures here are derived from the manual negative tests
I ran when each smoke was first shipped (commits 0155503 +
c5bfa1b + e90b4f9).  Each fixture documents WHY it should match
or not match in a comment.

Wall-clock: ~30ms (no subprocess spawn; just regex matching).
Wired into docker/l1-compose.yml after the audit smokes as their
self-test gate.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(name: str, path: str):
    """Import a script module by file path."""
    full = REPO / path
    spec = importlib.util.spec_from_file_location(name, full)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# Test cases:
#   (label, regex_attr, fixture_text, expected_count)
# regex_attr is a dotted path inside the module's DIVERGENCES /
# BAD_BINARY_PATTERNS / etc. structure.

DIVERGENCE_CASES = [
    # (test label, divergence #idx, fixture, expected match count)
    ("rust:1.83-bookworm Docker base", 0, "FROM rust:1.83-bookworm", 1),
    ("rust:1.88-bookworm is allowed", 0, "FROM rust:1.88-bookworm", 0),
    (
        "exec python3 -m findevil_agent.cli active drift",
        1,
        'exec python3 -m findevil_agent.cli "$@"',
        1,
    ),
    (
        "find-evil run active drift",
        1,
        "find-evil run --case foo",
        1,
    ),
    (
        "backticked find-evil run is doc-quote, not drift",
        1,
        "# Comment quoting `find-evil run` from old docs",
        0,
    ),
    (
        "11 typed Rust active drift",
        2,
        "wraps 11 typed Rust MCP tools",
        1,
    ),
    (
        "12 typed Rust active drift",
        2,
        "wraps 12 typed Rust MCP tools",
        1,
    ),
    (
        "13 typed Rust is correct",
        2,
        "wraps 13 typed Rust MCP tools",
        0,
    ),
    (
        "uncommented rmcp = is active drift",
        3,
        'rmcp = "=0.16.0"',
        1,
    ),
    (
        "commented rmcp = is the deliberate marker",
        3,
        '# rmcp = "=0.16.0"  # commented marker',
        0,
    ),
    (
        "python -m services.swarm.main is active drift",
        4,
        "python -m services.swarm.main --week 4",
        1,
    ),
    (
        "python -m findevil_swarm.main is correct",
        4,
        "python -m findevil_swarm.main run --week 4",
        0,
    ),
]


LAUNCHER_BAD_BINARY_CASES = [
    # (label, fixture, expected count from BAD_BINARY_PATTERNS combined)
    ("exec claude-code . is bug", "exec claude-code .", 1),
    ("command -v claude-code is bug", "command -v claude-code", 1),
    ("exec claude is correct", "exec claude", 0),
    ("command -v claude is correct", "command -v claude", 0),
    ("comment quoting claude-code-mode.md is OK", "# see claude-code-mode.md", 0),
    (
        "URL path .../claude-code/install is OK",
        "https://docs.anthropic.com/en/docs/claude-code/install",
        0,
    ),
]

LAUNCHER_BAD_INVOCATION_CASES = [
    # (label, fixture, expected count)
    ("exec claude . is bug", "exec claude .", 1),
    ("exec claude is correct", "exec claude", 0),
    (
        'exec claude . " is bug (followed by quote)',
        'exec claude . "interactive"',
        1,
    ),
]

AUTONOMOUS_LOOP_UNBLOCKED_CASES = [
    # (label, queue_text, expected_title-or-None)
    (
        "Single unblocked item is found",
        "- [ ] **First item** description here\n- [ ] **Second item** description\n",
        "First item",
    ),
    (
        "Done item is skipped, next unblocked picked",
        "- [x] **Done item** completed\n- [ ] **Next item** description\n",
        "Next item",
    ),
    (
        "Items below 'Hard blockers' heading are NOT picked",
        "### Some section\n- [x] **Done** completed\n\n### Hard blockers (require user)\n- [ ] **GitHub remote** user-required\n",
        None,
    ),
    (
        "Empty queue returns None",
        "## Notes\n\nNo items here.\n",
        None,
    ),
    (
        "Whitespace before list bullet still matches",
        "  - [ ] **Indented item** description\n",
        "Indented item",
    ),
]

AUTONOMOUS_LOOP_RATE_LIMIT_CASES = [
    # (label, stderr_text, expected_is_rate_limited)
    ("HTTP 429 in stderr is rate-limited", "Error: HTTP 429 Too Many Requests", True),
    (
        "Phrase 'rate limit exceeded' is rate-limited",
        "claude: rate limit exceeded",
        True,
    ),
    (
        "Phrase 'usage limit reached' is rate-limited",
        "You have reached your usage limit",
        True,
    ),
    (
        "Phrase 'out of extra usage' is rate-limited (real Anthropic message)",
        "You're out of extra usage.",
        True,
    ),
    ("Empty stderr is not rate-limited", "", False),
    ("Compilation message is not rate-limited", "compiled successfully", False),
    (
        "Generic 4xx with different code is not rate-limited",
        "HTTP 400 Bad Request",
        False,
    ),
]

AUTONOMOUS_LOOP_MIN_HOURS_CASES = [
    # (label, now, min_deadline, deadline, expected_wait)
    ("Before min and max deadlines waits", 10.0, 20.0, 30.0, True),
    ("After min deadline stops", 25.0, 20.0, 30.0, False),
    ("After max deadline stops", 31.0, 40.0, 30.0, False),
]

AUTONOMOUS_LOOP_EMPTY_SLEEP_CASES = [
    # (label, now, min_deadline, deadline, requested_sleep, expected_sleep)
    ("Sleep caps at min deadline", 0.0, 100.0, 200.0, 300.0, 100.0),
    ("Sleep uses requested interval when safe", 0.0, 100.0, 200.0, 30.0, 30.0),
    ("Sleep caps at max deadline", 0.0, 500.0, 200.0, 300.0, 200.0),
]


PATH_EXISTENCE_ALLOW_CASES = [
    # (label, candidate, expected_allowed)
    ("URL is allowed", "https://example.com/x/y", True),
    ("MCP wire identifier tools/list", "tools/list", True),
    ("MCP wire identifier tools/call", "tools/call", True),
    ("Runtime user dir ~/.claude/", "~/.claude/foo", True),
    ("Install path /usr/bin/find-evil", "/usr/bin/find-evil", True),
    ("Deferred-A2 apps/web/", "apps/web/lib/foo.ts", True),
    (
        "Dropped-A2 findevil_agent/cli.py is allow-listed",
        "services/agent/findevil_agent/cli.py",
        True,
    ),
    (
        "OTRF external dataset path",
        "datasets/atomic/windows/credential_access",
        True,
    ),
    (
        "Real local path is NOT allow-listed",
        "scripts/find-evil-auto",
        False,
    ),
    (
        "Real-but-broken path is NOT allow-listed",
        "services/foo/bar.py",
        False,
    ),
]


def _run_divergence_cases(div_smoke) -> list[tuple[str, str]]:
    """Returns list of (label, error) for failing cases."""
    failures = []
    for label, idx, fixture, expected in DIVERGENCE_CASES:
        regex = div_smoke.DIVERGENCES[idx]["regex"]
        actual = len(list(regex.finditer(fixture)))
        if actual != expected:
            failures.append(
                (
                    label,
                    f"expected {expected} match(es), got {actual}",
                )
            )
    return failures


def _run_launcher_cases(launch_smoke) -> list[tuple[str, str]]:
    failures = []
    # Bad-binary patterns (any-of).
    for label, fixture, expected in LAUNCHER_BAD_BINARY_CASES:
        actual = sum(
            len(list(p.finditer(fixture))) for p in launch_smoke.BAD_BINARY_PATTERNS
        )
        if actual != expected:
            failures.append(
                (label, f"expected {expected} bad-binary match(es), got {actual}")
            )
    # Bad-invocation patterns (any-of).
    for label, fixture, expected in LAUNCHER_BAD_INVOCATION_CASES:
        actual = sum(
            len(list(p.finditer(fixture))) for p in launch_smoke.BAD_INVOCATION_PATTERNS
        )
        if actual != expected:
            failures.append(
                (label, f"expected {expected} bad-invocation match(es), got {actual}")
            )
    return failures


def _run_autonomous_loop_cases(auto_loop) -> list[tuple[str, str]]:
    """Returns list of (label, error) for failing autonomous-loop
    queue-parser + rate-limit-detector cases."""
    failures = []
    for label, queue_text, expected_title in AUTONOMOUS_LOOP_UNBLOCKED_CASES:
        result = auto_loop._next_unblocked(queue_text)
        actual = result[0] if result else None
        if actual != expected_title:
            failures.append(
                (label, f"_next_unblocked: expected {expected_title!r}, got {actual!r}")
            )
    for label, stderr, expected in AUTONOMOUS_LOOP_RATE_LIMIT_CASES:
        actual = auto_loop._is_rate_limited(stderr)
        if actual != expected:
            failures.append(
                (
                    label,
                    f"_is_rate_limited({stderr!r}): expected {expected}, got {actual}",
                )
            )
    for label, now, min_deadline, deadline, expected in AUTONOMOUS_LOOP_MIN_HOURS_CASES:
        actual = auto_loop._should_wait_for_queue_item(now, min_deadline, deadline)
        if actual != expected:
            failures.append(
                (
                    label,
                    "_should_wait_for_queue_item: "
                    f"expected {expected}, got {actual}",
                )
            )
    for (
        label,
        now,
        min_deadline,
        deadline,
        requested_sleep,
        expected_sleep,
    ) in AUTONOMOUS_LOOP_EMPTY_SLEEP_CASES:
        actual = auto_loop._queue_empty_sleep_seconds(
            now, min_deadline, deadline, requested_sleep
        )
        if actual != expected_sleep:
            failures.append(
                (
                    label,
                    "_queue_empty_sleep_seconds: "
                    f"expected {expected_sleep}, got {actual}",
                )
            )
    return failures


def _run_path_existence_cases(pes_smoke) -> list[tuple[str, str]]:
    failures = []
    for label, candidate, expected_allowed in PATH_EXISTENCE_ALLOW_CASES:
        actual = pes_smoke._is_allowed(candidate)
        if actual != expected_allowed:
            failures.append(
                (
                    label,
                    f"_is_allowed({candidate!r}): expected {expected_allowed}, got {actual}",
                )
            )
    return failures


def main() -> int:
    print("=" * 60)
    print("Find Evil! - smoke-regex-tests")
    print("=" * 60)

    div_smoke = _load("div_smoke", "scripts/divergence-smoke.py")
    launch_smoke = _load("launch_smoke", "scripts/launcher-smoke.py")
    pes_smoke = _load("pes_smoke", "scripts/path-existence-smoke.py")
    auto_loop = _load("auto_loop", "scripts/autonomous-loop.py")

    all_failures: list[tuple[str, str, str]] = []

    div_failures = _run_divergence_cases(div_smoke)
    print(
        f"divergence-smoke regexes: {len(DIVERGENCE_CASES) - len(div_failures)}"
        f" / {len(DIVERGENCE_CASES)} passed"
    )
    for label, err in div_failures:
        all_failures.append(("divergence-smoke", label, err))

    launcher_failures = _run_launcher_cases(launch_smoke)
    n_launcher = len(LAUNCHER_BAD_BINARY_CASES) + len(LAUNCHER_BAD_INVOCATION_CASES)
    print(
        f"launcher-smoke regexes:   {n_launcher - len(launcher_failures)}"
        f" / {n_launcher} passed"
    )
    for label, err in launcher_failures:
        all_failures.append(("launcher-smoke", label, err))

    pes_failures = _run_path_existence_cases(pes_smoke)
    print(
        f"path-existence-smoke allow-list: "
        f"{len(PATH_EXISTENCE_ALLOW_CASES) - len(pes_failures)}"
        f" / {len(PATH_EXISTENCE_ALLOW_CASES)} passed"
    )
    for label, err in pes_failures:
        all_failures.append(("path-existence-smoke", label, err))

    auto_loop_failures = _run_autonomous_loop_cases(auto_loop)
    n_auto_loop = (
        len(AUTONOMOUS_LOOP_UNBLOCKED_CASES)
        + len(AUTONOMOUS_LOOP_RATE_LIMIT_CASES)
        + len(AUTONOMOUS_LOOP_MIN_HOURS_CASES)
        + len(AUTONOMOUS_LOOP_EMPTY_SLEEP_CASES)
    )
    print(
        f"autonomous-loop regexes:  {n_auto_loop - len(auto_loop_failures)}"
        f" / {n_auto_loop} passed"
    )
    for label, err in auto_loop_failures:
        all_failures.append(("autonomous-loop", label, err))

    print()
    if all_failures:
        print(f"FAIL - {len(all_failures)} regex test case(s) failed:")
        for smoke, label, err in all_failures:
            print(f"  [{smoke}] {label}: {err}")
        print()
        print("To fix: a regex in the named smoke has drifted.  Read")
        print("the test fixture comment in scripts/smoke-regex-tests.py")
        print("for what the regex is supposed to match (or not match).")
        print("=" * 60)
        return 1

    total = (
        len(DIVERGENCE_CASES)
        + n_launcher
        + len(PATH_EXISTENCE_ALLOW_CASES)
        + n_auto_loop
    )
    print("=" * 60)
    print(f"OK - all {total} regex test cases pass.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
