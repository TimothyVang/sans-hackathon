"""Critic subagent — reviews WorkerResult and emits a CriticVerdict.

Spec #1 §6 + Amendment A1. The critic is the second Claude invocation
per PR (first is the worker). It runs after the worker returns, reads
the worker's diff + L1 log + JSONL sidecar, and decides APPROVE or
REJECT. An APPROVE triggers ``gh pr create --draft``; REJECT cleans
up the worktree + branch.

The critic model is Sonnet (not Opus) — this is classification, not
generation. Cheap + fast.

Deterministic pre-checks run *before* Claude is called so obvious
failures (L1 red, empty diff, no-progress kill, token ceiling blown)
are cheap REJECTs with no tokens spent.

Under Option B, the critic obeys session_guard — a rate-limit signal
during critic invocation halts the supervisor same as during a worker.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from findevil_swarm.session_guard import (
    SessionLimitError,
    detect_halt_reason,
)
from findevil_swarm.state import CriticVerdict, PRSpec
from findevil_swarm.workers.base_worker import WorkerResult


# ---------------------------------------------------------------------------
# Deterministic pre-checks.
# ---------------------------------------------------------------------------


def pre_check(spec: PRSpec, result: WorkerResult) -> Optional[CriticVerdict]:
    """Return a REJECT ``CriticVerdict`` for obvious failures, else None.

    These are cheap bail-outs that don't need Claude at all:
      * L1 exit != 0 → REJECT
      * no_progress_killed → REJECT (worker stuck)
      * diff_line_count == 0 → REJECT (nothing written)
      * claude_exit != 0 → REJECT (worker crashed; wasn't already a
        halt signal since session_guard already handled those)
    """
    if result.claude_exit_code != 0:
        return _reject(spec, result, f"claude CLI exited {result.claude_exit_code}")
    if result.no_progress_killed:
        return _reject(spec, result, "worker produced no diff (no_progress_killed)")
    if result.diff_line_count == 0:
        return _reject(spec, result, "empty diff — no files changed")
    if result.l1_exit_code != 0:
        l1_tail = result.l1_stderr[-500:] or result.l1_stdout[-500:]
        return _reject(spec, result, f"L1 exit {result.l1_exit_code}: {l1_tail}")
    return None


def _reject(spec: PRSpec, result: WorkerResult, reason: str) -> CriticVerdict:
    return CriticVerdict(
        pr_id=spec.pr_id,
        decision="REJECT",
        reason=reason[:2000],
        token_count_input=result.token_count_input,
        token_count_output=result.token_count_output,
        l1_exit_code=result.l1_exit_code,
        diff_line_count=result.diff_line_count,
    )


def _approve(spec: PRSpec, result: WorkerResult, reason: str) -> CriticVerdict:
    return CriticVerdict(
        pr_id=spec.pr_id,
        decision="APPROVE",
        reason=reason[:2000],
        token_count_input=result.token_count_input,
        token_count_output=result.token_count_output,
        l1_exit_code=result.l1_exit_code,
        diff_line_count=result.diff_line_count,
    )


# ---------------------------------------------------------------------------
# Claude-CLI-backed review.
# ---------------------------------------------------------------------------


_CRITIC_PROMPT_TEMPLATE = """You are the critic for a Find Evil! build-swarm PR.

The worker produced this diff (truncated, 10k chars max):
--- DIFF START
{diff}
--- DIFF END

L1 validation exit code: {l1_exit_code}
L1 stdout tail (500 chars):
{l1_stdout_tail}

L1 stderr tail (500 chars):
{l1_stderr_tail}

Expected files (from PRSpec):
{files_expected}

Your checklist (REJECT if ANY fails):
- [ ] Expected files appear in the diff
- [ ] No single tool-call pattern repeated >5 times
- [ ] No mass deletions (>50% of an existing module removed)
- [ ] No fabricated tool output — only real diffs
- [ ] Diff is non-trivial and matches the task description

Output EXACTLY one line of JSON:
{{"decision": "APPROVE" | "REJECT", "reason": "<short human reason, <=200 chars>"}}

No prose before or after. No markdown. Just the JSON line.
"""


def review(
    spec: PRSpec,
    result: WorkerResult,
    repo: Path,
    *,
    model: str = "claude-sonnet-4-6",
    dry_run: bool = False,
) -> CriticVerdict:
    """Review a worker result; return a ``CriticVerdict``.

    Raises ``SessionLimitError`` if the critic invocation itself hits
    a rate-limit signal. Deterministic pre-checks run first; Claude is
    only invoked when the PR passes the cheap bail-outs.
    """
    # Cheap bail-outs.
    rejected = pre_check(spec, result)
    if rejected is not None:
        return rejected

    # Ask Claude.
    diff_text = _git_diff(repo=repo, worktree=result.worktree_path)
    prompt = _CRITIC_PROMPT_TEMPLATE.format(
        diff=diff_text[:10_000],
        l1_exit_code=result.l1_exit_code,
        l1_stdout_tail=result.l1_stdout[-500:] or "(empty)",
        l1_stderr_tail=result.l1_stderr[-500:] or "(empty)",
        files_expected="\n".join(f"  - {p}" for p in spec.files_expected)
        or "  (none declared)",
    )

    if dry_run:
        # Test mode: always approve if pre-check passed.
        return _approve(spec, result, "dry-run auto-approve")

    env = dict(os.environ)
    env["CLAUDE_CODE_FORK_SUBAGENT"] = "1"
    env["CLAUDE_AUTOCOMPACT"] = "0"
    proc = subprocess.run(
        [
            "claude",
            "--print",
            "--max-turns",
            "3",  # critic is 1-2 turns max
            "--model",
            model,
        ],
        input=prompt,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    halt = detect_halt_reason(exit_code=proc.returncode, stderr=proc.stderr)
    if halt is not None:
        raise SessionLimitError(halt)

    verdict = _parse_critic_json(proc.stdout)
    if verdict is None:
        # Unparseable critic output ≡ REJECT per Spec #1 §6.4.
        return _reject(
            spec, result, f"critic output was not valid JSON: {proc.stdout[:200]}"
        )
    return CriticVerdict(
        pr_id=spec.pr_id,
        decision=verdict["decision"],
        reason=verdict["reason"][:2000],
        token_count_input=result.token_count_input,
        token_count_output=result.token_count_output,
        l1_exit_code=result.l1_exit_code,
        diff_line_count=result.diff_line_count,
    )


def _git_diff(repo: Path, worktree: Path) -> str:
    """Get ``git diff HEAD`` from the worktree, truncated to 20k chars."""
    result = subprocess.run(
        ["git", "-C", str(worktree), "diff", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout[:20_000]


def _parse_critic_json(stdout: str) -> Optional[dict[str, str]]:
    """Parse the critic's one-line JSON output. Tolerates surrounding text."""
    import json
    import re

    # Look for the first {...} that parses as JSON with the expected shape.
    # The critic is instructed to emit ONLY the JSON line, but we're
    # defensive.
    for m in re.finditer(r"\{[^{}]*\}", stdout):
        try:
            obj = json.loads(m.group())
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        decision = obj.get("decision")
        reason = obj.get("reason", "")
        if decision in ("APPROVE", "REJECT") and isinstance(reason, str):
            return {"decision": decision, "reason": reason}
    return None


__all__ = ["pre_check", "review"]
