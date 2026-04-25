"""Tests for findevil_swarm.worktree — thin wrapper over ``git worktree``.

Spec #1 §3.1 Task 5 + §8. These tests use a temporary git repo fixture
so nothing touches the user's real workspace. They don't require a
live ``claude`` CLI or Postgres.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from findevil_swarm.worktree import (
    branch_name,
    create,
    iter_leaked,
    remove,
    slug_pr_id,
    worktree_path,
)

# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """Throwaway git repo with a single commit on ``main``."""
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "test"], check=True)
    (tmp_path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "README.md"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "seed"],
        check=True,
        capture_output=True,
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Pure helpers.
# ---------------------------------------------------------------------------


class TestSlug:
    def test_lowercases(self) -> None:
        assert slug_pr_id("Week2-Rust-FOO") == "week2-rust-foo"

    def test_replaces_nonalnum_with_hyphen(self) -> None:
        assert slug_pr_id("Task 4: plan_parser!") == "task-4-plan-parser"

    def test_trims_hyphens(self) -> None:
        assert slug_pr_id("--x--") == "x"

    def test_truncates_long(self) -> None:
        s = slug_pr_id("x" * 100)
        assert len(s) <= 60  # bounded so .wt paths stay short on Windows

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            slug_pr_id("")


class TestWorktreePath:
    def test_rust(self) -> None:
        p = worktree_path(repo=Path("/r"), language="rust", pr_id="week2-case-open")
        assert p == Path("/r/.wt/wt-rust-week2-case-open")

    def test_python_slug_lowercased(self) -> None:
        p = worktree_path(repo=Path("/r"), language="python", pr_id="Week2-PLAN-PARSER")
        assert p == Path("/r/.wt/wt-python-week2-plan-parser")

    def test_typescript(self) -> None:
        p = worktree_path(repo=Path("/r"), language="typescript", pr_id="week7-widget-timeline")
        assert p == Path("/r/.wt/wt-typescript-week7-widget-timeline")

    def test_rejects_unknown_language(self) -> None:
        with pytest.raises(ValueError):
            worktree_path(repo=Path("/r"), language="cobol", pr_id="x")


class TestBranchName:
    def test_format(self) -> None:
        assert branch_name(week=2, pr_id="case-open") == "swarm/week-2-case-open"

    def test_slugs_the_pr_id(self) -> None:
        assert branch_name(week=4, pr_id="Task 14: supervisor") == "swarm/week-4-task-14-supervisor"

    def test_rejects_bad_week(self) -> None:
        for bad in (0, 9, -1):
            with pytest.raises(ValueError):
                branch_name(week=bad, pr_id="x")


# ---------------------------------------------------------------------------
# Side-effecting operations against the tmp repo fixture.
# ---------------------------------------------------------------------------


class TestCreateAndRemove:
    def test_create_produces_valid_worktree(self, tmp_repo: Path) -> None:
        wt = create(repo=tmp_repo, language="rust", pr_id="test-pr-001", week=2)
        assert wt.is_dir()
        assert (wt / ".git").exists()  # worktrees have a .git file, not dir
        # Verify branch got created.
        result = subprocess.run(
            ["git", "-C", str(tmp_repo), "branch", "--list", "swarm/week-2-test-pr-001"],
            check=True,
            capture_output=True,
            text=True,
        )
        assert "swarm/week-2-test-pr-001" in result.stdout

    def test_create_then_remove_cleanly(self, tmp_repo: Path) -> None:
        wt = create(repo=tmp_repo, language="python", pr_id="test-pr-002", week=3)
        assert wt.is_dir()
        remove(repo=tmp_repo, language="python", pr_id="test-pr-002", delete_branch=True)
        assert not wt.exists()
        # Branch should also be gone.
        result = subprocess.run(
            ["git", "-C", str(tmp_repo), "branch", "--list", "swarm/week-3-test-pr-002"],
            capture_output=True,
            text=True,
        )
        assert "swarm/week-3-test-pr-002" not in result.stdout

    def test_remove_without_branch_keeps_branch(self, tmp_repo: Path) -> None:
        create(repo=tmp_repo, language="rust", pr_id="test-pr-003", week=2)
        remove(repo=tmp_repo, language="rust", pr_id="test-pr-003", delete_branch=False)
        # Branch still exists — useful when the worker committed and we want
        # to preserve history while freeing the worktree slot.
        result = subprocess.run(
            ["git", "-C", str(tmp_repo), "branch", "--list", "swarm/week-2-test-pr-003"],
            capture_output=True,
            text=True,
        )
        assert "swarm/week-2-test-pr-003" in result.stdout

    def test_double_create_raises(self, tmp_repo: Path) -> None:
        create(repo=tmp_repo, language="rust", pr_id="test-pr-004", week=2)
        with pytest.raises(RuntimeError):
            create(repo=tmp_repo, language="rust", pr_id="test-pr-004", week=2)

    def test_remove_missing_is_idempotent(self, tmp_repo: Path) -> None:
        # Removing a worktree that doesn't exist should not raise —
        # morning cleanup script needs this to be a no-op.
        remove(repo=tmp_repo, language="rust", pr_id="nope", delete_branch=True)


class TestIterLeaked:
    def test_no_leaks_in_clean_repo(self, tmp_repo: Path) -> None:
        assert list(iter_leaked(repo=tmp_repo)) == []

    def test_finds_leaked_worktree(self, tmp_repo: Path) -> None:
        wt = create(repo=tmp_repo, language="rust", pr_id="test-leak", week=2)
        # Manually remove the filesystem side so the git metadata becomes
        # a leak that `git worktree prune` would catch.
        import shutil

        shutil.rmtree(wt)
        leaks = list(iter_leaked(repo=tmp_repo))
        assert len(leaks) == 1
        # We report the branch name for the leak for targeted cleanup.
        assert "swarm/week-2-test-leak" in leaks[0].branch

    def test_detects_orphan_dot_wt_dir(self, tmp_repo: Path) -> None:
        # A .wt/wt-* directory with no corresponding git worktree metadata
        # (e.g. a crash left it behind) is also reportable.
        orphan = tmp_repo / ".wt" / "wt-rust-crashed"
        orphan.mkdir(parents=True)
        leaks = list(iter_leaked(repo=tmp_repo))
        paths = [str(x.path) for x in leaks]
        assert any("wt-rust-crashed" in p for p in paths)
