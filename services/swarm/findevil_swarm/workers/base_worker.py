"""Base worker — invokes ``claude`` CLI in a git worktree, runs L1.

Spec #1 §5 + Amendment A1. Under Option B the flow is:

  1. Create the worktree (``worktree.create``).
  2. Build a task-specific system prompt from ``PRSpec`` + the
     language-specific fragment supplied by the subclass.
  3. Spawn ``claude`` as a subprocess with:
       * ``cwd`` = worktree path
       * ``--max-turns`` = ``PRSpec.max_turns``
       * ``--model`` per subclass (Opus for architect pass, Sonnet
         for editor pass — Aider split per Spec #1 §5.2)
       * env:
           ``CLAUDE_CODE_FORK_SUBAGENT=1``   (prompt-cache savings)
           ``CLAUDE_CODE_OAUTH_TOKEN=...``   (optional; if set in
                                             parent env, inherited)
           ``CLAUDE_AUTOCOMPACT=0``          (issue #9579 guard)
       * stdin = full task description + files list + L1 command
  4. Capture stdout + stderr to the JSONL sidecar.
  5. Check ``session_guard.detect_halt_reason`` — raises
     ``SessionLimitError`` when a rate-limit / expired-session
     signal is detected.
  6. Compute ``git diff`` against base to get ``diff_line_count``.
  7. Run ``PRSpec.l1_command`` in the worktree. Capture exit code +
     stdout/stderr (truncated to 10k chars each).
  8. Pack everything into ``WorkerResult``.

No retry logic anywhere. The critic handles REJECT (bad diff). The
session_guard handles SessionLimitError (external halt). Everything
else — L1 failures, timeouts — returns a WorkerResult that the
critic will interpret.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from findevil_swarm import worktree as wt
from findevil_swarm.session_guard import (
    SessionLimitError,
    detect_halt_reason,
)
from findevil_swarm.state import PRSpec

_TRUNCATE = 10_000


# ---------------------------------------------------------------------------
# Dataclasses.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkerInput:
    """What ``dispatch_node`` hands each worker."""

    pr_spec: PRSpec
    repo: Path
    jsonl_sidecar_path: Path
    # Optional env overrides. ``CLAUDE_CODE_FORK_SUBAGENT=1`` and
    # ``CLAUDE_AUTOCOMPACT=0`` are always injected; this dict layers
    # on top for testing or special-case PRs.
    env_overrides: dict[str, str] = field(default_factory=dict)
    # For testability — default True invokes real ``claude`` CLI.
    # Tests pass dry_run=True which short-circuits subprocess calls.
    dry_run: bool = False


@dataclass(frozen=True)
class WorkerResult:
    """What a worker returns to ``collect_node``."""

    pr_id: str
    branch_name: str
    worktree_path: Path
    claude_exit_code: int
    claude_stdout: str = ""
    claude_stderr: str = ""
    l1_exit_code: int = -1
    l1_stdout: str = ""
    l1_stderr: str = ""
    diff_line_count: int = 0
    token_count_input: int = 0
    token_count_output: int = 0
    no_progress_killed: bool = False
    wall_clock_seconds: int = 0
    jsonl_sidecar_path: Path | None = None


# ---------------------------------------------------------------------------
# BaseWorker.
# ---------------------------------------------------------------------------


class BaseWorker:
    """Base class; subclasses override ``language`` and ``system_prompt_fragment``."""

    language: ClassVar[str] = "python"
    architect_model: ClassVar[str] = "claude-opus-4-7"
    editor_model: ClassVar[str] = "claude-sonnet-4-6"

    # Absolute, portable default if PRSpec.l1_command is empty.
    default_l1_command: ClassVar[str] = "uv run pytest -xvs"

    # ``{description}`` placeholder is replaced with the full task
    # description by ``build_prompt``. Subclasses extend this with
    # language-specific guidance.
    base_prompt: ClassVar[str] = (
        "You are a Claude Code subagent running autonomously inside a git "
        "worktree for the Find Evil! build swarm (Option B mode).\n\n"
        "Invariants (read agent-config/SOUL.md, CLAUDE.md, and the spec for "
        "your subsystem before writing anything):\n"
        "- No `execute_shell` MCP tool, ever.\n"
        "- Every Finding cites a tool_call_id.\n"
        "- AGPL/GPL tools are subprocess-only; never linked.\n"
        "- Evidence is read-only.\n"
        "- Hash-chained audit JSONL is append-only.\n"
        "- Draft PRs only; never auto-merge.\n\n"
        "Your task for this PR:\n\n{description}\n"
    )

    system_prompt_fragment: ClassVar[str] = ""

    def build_prompt(self, spec: PRSpec) -> str:
        """Assemble the task-specific prompt fed to ``claude`` on stdin."""
        body = self.base_prompt.format(description=spec.description)
        if self.system_prompt_fragment:
            body = f"{body}\n\n{self.system_prompt_fragment}"
        if spec.files_expected:
            files_block = "\n".join(f"  - {p}" for p in spec.files_expected)
            body = (
                f"{body}\n\nExpected files to create or modify (the critic "
                f"will check):\n{files_block}\n"
            )
        body = (
            f"{body}\n\nL1 validation command (must exit 0 before you "
            f"commit): `{spec.l1_command}`\n"
        )
        return body

    def build_env(self, overrides: dict[str, str]) -> dict[str, str]:
        """Compose the subprocess environment. Parent env inherited."""
        env = dict(os.environ)
        env["CLAUDE_CODE_FORK_SUBAGENT"] = "1"
        env["CLAUDE_AUTOCOMPACT"] = "0"
        env.update(overrides)
        return env

    def execute(self, inp: WorkerInput) -> WorkerResult:
        """Run the full worker lifecycle. Raises ``SessionLimitError`` on halt signals."""
        started = time.time()
        spec = inp.pr_spec
        worktree_dir = wt.worktree_path(repo=inp.repo, language=self.language, pr_id=spec.pr_id)
        branch = wt.branch_name(week=spec.week, pr_id=spec.pr_id)

        # Step 1: create worktree.
        wt.create(
            repo=inp.repo,
            language=self.language,
            pr_id=spec.pr_id,
            week=spec.week,
        )

        claude_exit: int = 0
        claude_stdout = ""
        claude_stderr = ""
        l1_exit = -1
        l1_stdout = ""
        l1_stderr = ""
        diff_lines = 0

        try:
            # Step 2-4: build prompt + invoke claude.
            prompt = self.build_prompt(spec)
            env = self.build_env(inp.env_overrides)

            if inp.dry_run:
                # Test mode: don't invoke real claude; simulate a clean run.
                # Also touch a sentinel file inside the worktree so the
                # subsequent git diff is non-empty — otherwise the critic
                # pre-check rejects every mock-workers run for "empty diff"
                # before we ever exercise the critic itself. We stage the
                # file but do NOT commit, so `git diff HEAD` sees it.
                sentinel = worktree_dir / f".swarm-mock-{spec.pr_id}.txt"
                sentinel.write_text(
                    f"# Swarm mock worker output for {spec.pr_id}\n"
                    f"# Week: {spec.week}  Language: {self.language}\n"
                    f"# Generated at worker dry_run time.\n"
                    f"# The real worker would have edited: {spec.files_expected}\n",
                    encoding="utf-8",
                )
                # Stage but don't commit — keeps diff HEAD non-empty.
                subprocess.run(
                    ["git", "-C", str(worktree_dir), "add", sentinel.name],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                claude_exit = 0
                claude_stdout = "[dry-run] prompt length=" + str(len(prompt))
                claude_stderr = ""
            else:
                proc = subprocess.run(
                    [
                        "claude",
                        "--print",
                        "--max-turns",
                        str(spec.max_turns),
                        "--model",
                        self.architect_model,
                    ],
                    cwd=str(worktree_dir),
                    input=prompt,
                    capture_output=True,
                    text=True,
                    env=env,
                    check=False,
                )
                claude_exit = proc.returncode
                claude_stdout = proc.stdout[:_TRUNCATE]
                claude_stderr = proc.stderr[:_TRUNCATE]

            # Step 5: sidecar write (always, even on halt — it's the
            # forensic trail).
            self._write_sidecar(
                inp.jsonl_sidecar_path,
                spec=spec,
                prompt_chars=len(prompt),
                claude_exit=claude_exit,
                claude_stderr_snippet=claude_stderr[:500],
            )

            # Step 6: halt signal? raise early before L1 touches disk.
            halt_reason = detect_halt_reason(exit_code=claude_exit, stderr=claude_stderr)
            if halt_reason is not None:
                raise SessionLimitError(halt_reason)

            # Step 7: diff line count (useful even on failure for critic).
            diff_lines = self._count_diff_lines(inp.repo, worktree_dir)

            # Step 8: L1.
            l1_cmd = spec.l1_command or self.default_l1_command
            if inp.dry_run:
                l1_exit = 0
                l1_stdout = "[dry-run] skipped L1"
                l1_stderr = ""
            else:
                l1_proc = subprocess.run(
                    ["bash", "-lc", l1_cmd],
                    cwd=str(worktree_dir),
                    capture_output=True,
                    text=True,
                    env=env,
                    check=False,
                )
                l1_exit = l1_proc.returncode
                l1_stdout = l1_proc.stdout[:_TRUNCATE]
                l1_stderr = l1_proc.stderr[:_TRUNCATE]

        except SessionLimitError:
            # Halt bubbles up to supervisor's ``collect_node``; worktree
            # is kept (resume path re-hydrates it tomorrow).
            raise

        return WorkerResult(
            pr_id=spec.pr_id,
            branch_name=branch,
            worktree_path=worktree_dir,
            claude_exit_code=claude_exit,
            claude_stdout=claude_stdout,
            claude_stderr=claude_stderr,
            l1_exit_code=l1_exit,
            l1_stdout=l1_stdout,
            l1_stderr=l1_stderr,
            diff_line_count=diff_lines,
            token_count_input=0,  # populated in a later iteration
            token_count_output=0,
            no_progress_killed=(diff_lines == 0 and claude_exit == 0),
            wall_clock_seconds=int(time.time() - started),
            jsonl_sidecar_path=inp.jsonl_sidecar_path,
        )

    # ------------------------------------------------------------------
    # Helpers.
    # ------------------------------------------------------------------

    def _count_diff_lines(self, repo: Path, worktree: Path) -> int:
        """Run ``git diff HEAD`` in the worktree and count changed lines."""
        result = subprocess.run(
            ["git", "-C", str(worktree), "diff", "HEAD", "--numstat"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return 0
        total = 0
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            try:
                added = int(parts[0]) if parts[0] != "-" else 0
                removed = int(parts[1]) if parts[1] != "-" else 0
            except ValueError:
                continue
            total += added + removed
        return total

    def _write_sidecar(
        self,
        sidecar: Path,
        *,
        spec: PRSpec,
        prompt_chars: int,
        claude_exit: int,
        claude_stderr_snippet: str,
    ) -> None:
        """Append a single JSONL record to the sidecar file.

        The full OpenHands-style streaming tool-call replay is Spec #1
        §10.2 territory; this MVP writes one summary record per worker
        run which is already enough for post-hoc triage.
        """
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "pr_id": spec.pr_id,
            "week": spec.week,
            "language": self.language,
            "architect_model": self.architect_model,
            "editor_model": self.editor_model,
            "prompt_chars": prompt_chars,
            "claude_exit_code": claude_exit,
            "claude_stderr_snippet": claude_stderr_snippet,
            "ts_epoch": int(time.time()),
        }
        with sidecar.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


__all__ = [
    "BaseWorker",
    "WorkerInput",
    "WorkerResult",
]
