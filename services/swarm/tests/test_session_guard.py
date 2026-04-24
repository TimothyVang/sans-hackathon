"""Tests for findevil_swarm.session_guard.

Spec #1 §3.1 Task 6 + Amendment A1. The guard replaces the Option-A
``budget.py`` — in Option B (Claude Code subscription mode), the
swarm cannot enforce a USD cap because the subscription is session-
based, not metered. Instead it watches ``claude`` CLI output for
rate-limit / auth-expiry signals and halts cleanly — no retry,
Postgres checkpoint carries forward to the next night.
"""

from __future__ import annotations

import pytest

from findevil_swarm.session_guard import (
    SessionLimitError,
    check_exit_code,
    check_stderr,
    detect_halt_reason,
    is_rate_limited,
    is_session_expired,
)


# ---------------------------------------------------------------------------
# Pattern detectors — exhaustive because false negatives here leak
# stuck workers through the night and real dollars/tokens with them.
# ---------------------------------------------------------------------------


class TestIsRateLimited:
    @pytest.mark.parametrize(
        "stderr",
        [
            "Error: HTTP 429 Too Many Requests",
            "claude-code: rate limit exceeded",
            "You have reached your usage limit",
            "usage limit reached. resets at 2026-04-23T22:20:00Z",
            "Rate-limited by upstream provider",
            "status code 429",
            "anthropic returned 429",
            "429: too many requests in window",
            "You're out of extra usage",  # exact string from the real incident
            "quota exceeded for this billing period",
        ],
    )
    def test_positive_cases(self, stderr: str) -> None:
        assert is_rate_limited(stderr) is True

    @pytest.mark.parametrize(
        "stderr",
        [
            "",
            "compiled successfully",
            "42 tests passed",
            "Warning: deprecation at line 42",
            "connection refused",  # transient network issue, NOT a halt reason
            "timeout waiting for response",  # transient, NOT halt
            # Prose mentions of rate limit in a passing message must not halt —
            # the guard only fires on *actual* limit signals.
            "see docs at example.com/rate-limits for details",
        ],
    )
    def test_negative_cases(self, stderr: str) -> None:
        assert is_rate_limited(stderr) is False


class TestIsSessionExpired:
    @pytest.mark.parametrize(
        "stderr",
        [
            "Session expired. Please run `claude auth login` again",
            "authentication required",
            "not authenticated",
            "Please log in again",
            "Invalid token",
            "OAuth token has expired",
            "CLAUDE_CODE_OAUTH_TOKEN is invalid or expired",
        ],
    )
    def test_positive_cases(self, stderr: str) -> None:
        assert is_session_expired(stderr) is True

    @pytest.mark.parametrize(
        "stderr",
        [
            "",
            "Compilation succeeded",
            "Test failed: expected 42, got 41",
            # Don't confuse 'auth' in a tool description with a real auth
            # failure from the claude CLI itself.
            "Cargo.toml has an [dependencies.oauth] section",
        ],
    )
    def test_negative_cases(self, stderr: str) -> None:
        assert is_session_expired(stderr) is False


# ---------------------------------------------------------------------------
# Higher-level detectors — combine stderr + exit code into a halt
# reason or None.
# ---------------------------------------------------------------------------


class TestCheckStderr:
    def test_rate_limit_returns_reason(self) -> None:
        r = check_stderr("HTTP 429: too many requests")
        assert r is not None
        assert "rate" in r.lower() or "429" in r

    def test_session_expiry_returns_reason(self) -> None:
        r = check_stderr("Session expired")
        assert r is not None
        assert "session" in r.lower()

    def test_clean_stderr_returns_none(self) -> None:
        assert check_stderr("ok") is None
        assert check_stderr("") is None


class TestCheckExitCode:
    def test_zero_exit_never_halts(self) -> None:
        # Exit 0 means the worker finished normally. Even if stderr had
        # scary text, a clean exit is authoritative.
        assert check_exit_code(0, "429 rate limit") is None

    def test_nonzero_plus_rate_limit_stderr_halts(self) -> None:
        r = check_exit_code(1, "HTTP 429 from provider")
        assert r is not None
        assert "rate" in r.lower() or "429" in r

    def test_nonzero_clean_stderr_returns_none(self) -> None:
        # Non-zero exit with clean stderr = a code bug, not a session
        # limit. Guard should not halt the swarm for code bugs.
        assert check_exit_code(1, "compilation error: mismatched types") is None


class TestDetectHaltReason:
    def test_clean_run_returns_none(self) -> None:
        assert detect_halt_reason(exit_code=0, stderr="everything ok") is None

    def test_rate_limit_prioritizes_over_session_expiry(self) -> None:
        # If both signals appear, rate-limit is the more informative
        # label for the night report.
        r = detect_halt_reason(
            exit_code=1,
            stderr="HTTP 429 rate limit exceeded. Session expired too.",
        )
        assert r is not None
        assert "rate" in r.lower() or "429" in r

    def test_nonzero_exit_with_rate_limit_halts(self) -> None:
        r = detect_halt_reason(exit_code=1, stderr="usage limit reached")
        assert r is not None


# ---------------------------------------------------------------------------
# Exception type.
# ---------------------------------------------------------------------------


class TestSessionLimitError:
    def test_is_exception_subclass(self) -> None:
        assert issubclass(SessionLimitError, Exception)

    def test_carries_reason(self) -> None:
        e = SessionLimitError("HTTP 429 at 22:41 CT")
        assert "429" in str(e)
        assert e.reason == "HTTP 429 at 22:41 CT"

    def test_raising_preserves_chain(self) -> None:
        with pytest.raises(SessionLimitError) as exc:
            try:
                raise RuntimeError("upstream")
            except RuntimeError as upstream:
                raise SessionLimitError("halting") from upstream
        assert exc.value.__cause__ is not None
