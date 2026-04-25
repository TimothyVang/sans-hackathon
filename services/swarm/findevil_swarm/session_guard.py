"""Rate-limit + session-expiry detector for Option B (Claude Code subscription).

Spec #1 §3.1 Task 6 + Amendment A1 §2.2. In Option B the swarm cannot
enforce a USD budget cap (there is no metered API in the path), so
``session_guard`` watches every ``claude`` CLI invocation for two
classes of halt signals and stops the supervisor cleanly when either
is seen:

* **Rate-limit signals** — HTTP 429, "usage limit reached", "rate
  limit", "You're out of extra usage", quota-exceeded messages.
* **Session-expiry signals** — auth required, invalid/expired
  OAuth token, session expired.

On detection, ``SessionLimitError`` is raised. The supervisor catches
it in ``collect_node``, writes a ``NightlyReport`` with the halt
reason, and exits cleanly. ``PostgresSaver`` preserves the DAG state
so the next night's run resumes from where we stopped. **No retry**
is attempted; the reason whatever-it-was will still apply a minute
later, and retry loops amplify cost/spend (see Spec #1 §12 W1).

Public surface:
  * ``SessionLimitError`` — the exception the guard raises
  * ``is_rate_limited(stderr: str) -> bool`` — pure predicate
  * ``is_session_expired(stderr: str) -> bool`` — pure predicate
  * ``check_stderr(stderr: str) -> Optional[str]`` — returns a
    halt reason string or ``None``
  * ``check_exit_code(code: int, stderr: str) -> Optional[str]`` —
    combines non-zero exit with stderr pattern
  * ``detect_halt_reason(exit_code: int, stderr: str) -> Optional[str]``
    — top-level detector used by base_worker.py
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Patterns.
#
# RATE_LIMIT_PATTERNS is ordered: more-specific first so the matching
# reason string is the most useful one. The patterns are case-insensitive
# and anchored carefully so a tool *description* mentioning "rate limit"
# in normal output does not accidentally trip the halt.
# ---------------------------------------------------------------------------


_RATE_LIMIT_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Exact strings from real incidents we have evidence of.
    re.compile(r"you're\s+out\s+of\s+extra\s+usage", re.IGNORECASE),
    re.compile(r"usage\s+limit\s+reached", re.IGNORECASE),
    # Variant phrasing — Anthropic's "You have reached your usage limit".
    re.compile(r"reached\s+(?:your\s+)?usage\s+limit", re.IGNORECASE),
    re.compile(r"quota\s+exceeded", re.IGNORECASE),
    # HTTP 429 in common surface forms.
    re.compile(r"\bhttp\s*429\b", re.IGNORECASE),
    re.compile(r"\bstatus\s+code\s+429\b", re.IGNORECASE),
    re.compile(r"\breturned\s+429\b", re.IGNORECASE),
    re.compile(r"\b429\s*:\s*too\s+many\s+requests\b", re.IGNORECASE),
    # "rate limit exceeded" / "rate-limited by" — phrases the claude CLI
    # + provider stacks emit verbatim.
    re.compile(r"rate[\s\-]?limit(?:\s+exceeded|ed\s+by)", re.IGNORECASE),
    # Capture plain "Too Many Requests" without a 429 prefix.
    re.compile(r"\btoo\s+many\s+requests\b", re.IGNORECASE),
)


_SESSION_EXPIRED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"session\s+expired", re.IGNORECASE),
    re.compile(
        r"claude_code_oauth_token\s+is\s+invalid\s+or\s+expired",
        re.IGNORECASE,
    ),
    re.compile(r"oauth\s+token\s+has\s+expired", re.IGNORECASE),
    re.compile(r"\binvalid\s+token\b", re.IGNORECASE),
    re.compile(r"\bnot\s+authenticated\b", re.IGNORECASE),
    re.compile(r"\bauthentication\s+required\b", re.IGNORECASE),
    re.compile(r"\bplease\s+log\s+in\s+again\b", re.IGNORECASE),
    re.compile(r"\bclaude\s+auth\s+login\b", re.IGNORECASE),
)


# A small denylist of innocuous substrings that would otherwise cause
# false positives — e.g. if an agent's README documents "see the
# rate-limits page", that shouldn't halt the swarm. We only suppress
# when the match is *only* inside such a context; a real 429 elsewhere
# in the same stderr still halts.
_FALSE_POSITIVE_CONTEXT = (
    "rate-limits page",
    "see docs at",
    "see the docs",
    "dependencies.oauth",
)


# ---------------------------------------------------------------------------
# Pure predicates.
# ---------------------------------------------------------------------------


def is_rate_limited(stderr: str) -> bool:
    """True if ``stderr`` contains a rate-limit signal worth halting on."""
    if not stderr:
        return False
    text = stderr
    for pat in _RATE_LIMIT_PATTERNS:
        m = pat.search(text)
        if m is None:
            continue
        # Context check: if the surrounding ~40 chars contain a known
        # false-positive marker, keep scanning for a real hit elsewhere.
        start = max(0, m.start() - 40)
        end = min(len(text), m.end() + 40)
        window = text[start:end].lower()
        if any(fp in window for fp in _FALSE_POSITIVE_CONTEXT):
            continue
        return True
    return False


def is_session_expired(stderr: str) -> bool:
    """True if ``stderr`` indicates an auth/session problem."""
    if not stderr:
        return False
    for pat in _SESSION_EXPIRED_PATTERNS:
        m = pat.search(stderr)
        if m is None:
            continue
        start = max(0, m.start() - 40)
        end = min(len(stderr), m.end() + 40)
        window = stderr[start:end].lower()
        if any(fp in window for fp in _FALSE_POSITIVE_CONTEXT):
            continue
        return True
    return False


# ---------------------------------------------------------------------------
# Compound detectors.
# ---------------------------------------------------------------------------


def check_stderr(stderr: str) -> str | None:
    """Return a halt reason for ``stderr``, or None.

    Rate-limit signals take priority over session-expiry because they
    have a reset time and our resume story is cleaner for them.
    """
    if is_rate_limited(stderr):
        return _extract_reason(stderr, _RATE_LIMIT_PATTERNS, prefix="rate-limit")
    if is_session_expired(stderr):
        return _extract_reason(stderr, _SESSION_EXPIRED_PATTERNS, prefix="session-expired")
    return None


def check_exit_code(exit_code: int, stderr: str) -> str | None:
    """Return a halt reason combining exit code + stderr, or None.

    Rules:
      * exit_code == 0 is authoritative: never halt on a clean run,
        even if stderr had scary-looking strings.
      * exit_code != 0 + clean stderr means a code bug (compile/test
        failure). That's *not* a swarm-level halt — the critic rejects
        the PR and the swarm keeps going with the next task.
      * exit_code != 0 + halt-worthy stderr is the halt path.
    """
    if exit_code == 0:
        return None
    return check_stderr(stderr)


def detect_halt_reason(exit_code: int, stderr: str) -> str | None:
    """Top-level detector used by ``base_worker.py``.

    Equivalent to ``check_exit_code`` today but kept as a distinct
    public function so we can layer in additional signals later (e.g.
    inspecting the claude CLI's JSONL output format) without breaking
    callers.
    """
    return check_exit_code(exit_code=exit_code, stderr=stderr)


def _extract_reason(stderr: str, patterns: tuple[re.Pattern[str], ...], prefix: str) -> str:
    """Extract a short, useful halt-reason string from ``stderr``.

    Finds the first pattern hit and returns a ~120-char slice around
    it, prefixed with the category. This is what gets logged to
    ``night_report.jsonl`` and surfaced in Slack alerts.
    """
    for pat in patterns:
        m = pat.search(stderr)
        if m is None:
            continue
        start = max(0, m.start() - 20)
        end = min(len(stderr), m.end() + 80)
        snippet = stderr[start:end].replace("\n", " ").strip()
        return f"{prefix}: {snippet[:120]}"
    return f"{prefix}: (unknown; detector pattern drift)"


# ---------------------------------------------------------------------------
# Exception.
# ---------------------------------------------------------------------------


class SessionLimitError(Exception):
    """Raised by base_worker when a halt-worthy signal is detected.

    Carries a ``reason`` attribute so the supervisor can write it to
    ``NightlyReport.session_halt_reason`` without string-parsing the
    exception message.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


__all__ = [
    "SessionLimitError",
    "check_exit_code",
    "check_stderr",
    "detect_halt_reason",
    "is_rate_limited",
    "is_session_expired",
]
