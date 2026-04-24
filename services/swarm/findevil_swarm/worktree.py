"""Thin wrapper over ``git worktree``.

Spec #1 §3.1 Task 5 + §8. Every worker gets its own worktree under
``<repo>/.wt/wt-{language}-{slug(pr_id)}`` on a branch named
``swarm/week-{N}-{slug(pr_id)}``. One worktree per PR — non-negotiable
per Spec #1 §12 W6 (parallel workers on the same branch → corruption).

The wrapper:
  * enforces the naming convention,
  * is idempotent on remove (morning cleanup needs this),
  * reports leaked worktrees so ``swarm-start.sh`` pre-flight can
    clean them before dispatch.

Uses only the Python stdlib — no GitPython, no pygit2. ``git`` on
``$PATH`` is the contract.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_ALLOWED_LANGS = frozenset({"rust", "python", "typescript"})
_SLUG_MAX = 60
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug_pr_id(pr_id: str) -> str:
    """Return a lowercased, hyphen-joined, trimmed slug for a pr_id.

    Empty input raises ``ValueError`` — an empty slug cannot produce a
    unique worktree path.
    """
    if not pr_id:
        raise ValueError("pr_id is required")
    out = _SLUG_RE.sub("-", pr_id.lower()).strip("-")
    if not out:
        raise ValueError(f"pr_id {pr_id!r} produced empty slug")
    if len(out) > _SLUG_MAX:
        out = out[:_SLUG_MAX].rstrip("-")
    return out


def worktree_path(repo: Path, language: str, pr_id: str) -> Path:
    """Compute the canonical worktree path for a (language, pr_id) pair.

    Pure function — no filesystem side effects. Paths are always under
    ``<repo>/.wt/wt-{language}-{slug}`` so the ``.gitignore`` entry
    ``/.wt/`` (added in L0 Task 1) keeps them off the tree.
    """
    if language not in _ALLOWED_LANGS:
        raise ValueError(
            f"language {language!r} not in {sorted(_ALLOWED_LANGS)}"
        )
    return repo / ".wt" / f"wt-{language}-{slug_pr_id(pr_id)}"


def branch_name(week: int, pr_id: str) -> str:
    """Compute the canonical branch name for a (week, pr_id) pair.

    Format: ``swarm/week-{N}-{slug(pr_id)}``. Week must be 1..8 per
    the 8-week roadmap in BUILD_PLAN_v2.md §7.
    """
    if week < 1 or week > 8:
        raise ValueError(f"week {week} outside supported 1..8 range")
    return f"swarm/week-{week}-{slug_pr_id(pr_id)}"


# ---------------------------------------------------------------------------
# Leaked worktree reporting.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeakedWorktree:
    """A worktree metadata entry whose filesystem copy is missing or orphaned.

    ``path`` is the absolute path where git thinks the worktree lives.
    ``branch`` is the branch that was checked out (may be None if
    detected via orphan-dir scan rather than git metadata).
    """

    path: Path
    branch: str


def iter_leaked(repo: Path) -> Iterator[LeakedWorktree]:
    """Yield leaked worktrees discoverable from ``repo``.

    Two sources of leaks:
      1. ``git worktree list`` entries whose path no longer exists
         (process crashed mid-run or someone ``rm -rf``'d the dir).
      2. ``<repo>/.wt/wt-*`` directories with no corresponding git
         metadata entry (git cleanup partially completed).
    """
    # Source 1 — ask git what it thinks exists.
    gitside = _git_worktrees(repo)
    for entry in gitside:
        if entry.path.exists():
            continue
        yield LeakedWorktree(path=entry.path, branch=entry.branch)

    # Source 2 — scan the .wt directory for orphan dirs git doesn't know about.
    wt_root = repo / ".wt"
    if not wt_root.is_dir():
        return

    git_paths = {str(e.path).lower() for e in gitside}
    for child in wt_root.iterdir():
        if not child.is_dir():
            continue
        if not child.name.startswith("wt-"):
            continue
        if str(child).lower() in git_paths:
            continue
        yield LeakedWorktree(path=child, branch="<orphan-no-git-metadata>")


@dataclass(frozen=True)
class _GitWorktreeEntry:
    path: Path
    branch: str


def _git_worktrees(repo: Path) -> list[_GitWorktreeEntry]:
    """Parse ``git worktree list --porcelain`` into structured entries."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return []
    except FileNotFoundError:
        return []

    entries: list[_GitWorktreeEntry] = []
    cur_path: Path | None = None
    cur_branch: str = ""
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            if cur_path is not None:
                entries.append(_GitWorktreeEntry(path=cur_path, branch=cur_branch))
            cur_path = Path(line[len("worktree ") :])
            cur_branch = ""
        elif line.startswith("branch refs/heads/"):
            cur_branch = line[len("branch refs/heads/") :]
    if cur_path is not None:
        entries.append(_GitWorktreeEntry(path=cur_path, branch=cur_branch))
    # Drop the main worktree (the repo itself); only swarm-created ones matter
    # for leak tracking.
    return [e for e in entries if ".wt" in str(e.path)]


# ---------------------------------------------------------------------------
# Create / remove.
# ---------------------------------------------------------------------------


def create(
    repo: Path, language: str, pr_id: str, week: int, base: str = "HEAD"
) -> Path:
    """Create a fresh worktree for (language, pr_id) on a new branch.

    Raises ``RuntimeError`` if the target path already exists — callers
    must call ``remove`` first, or use a different pr_id.
    """
    wt = worktree_path(repo=repo, language=language, pr_id=pr_id)
    br = branch_name(week=week, pr_id=pr_id)
    if wt.exists():
        raise RuntimeError(f"worktree already exists at {wt}")

    # Make sure the parent .wt/ directory is there.
    wt.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "worktree",
            "add",
            "-b",
            br,
            str(wt),
            base,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git worktree add failed for {wt}: {result.stderr.strip()}"
        )
    return wt


def remove(
    repo: Path, language: str, pr_id: str, delete_branch: bool = True
) -> None:
    """Remove a worktree. Idempotent — missing worktree is a silent success.

    If ``delete_branch`` is True, the associated branch is deleted too
    (forced, since we may be deleting a branch that's been pushed). The
    canonical branch name is inferred from pr_id — pass delete_branch=False
    to preserve history when the worker committed useful work.
    """
    wt = worktree_path(repo=repo, language=language, pr_id=pr_id)

    # git worktree remove --force handles both "exists but dirty" and
    # "exists cleanly"; if the path doesn't exist, we still want to
    # prune git's metadata so subsequent `worktree list` is clean.
    if wt.exists():
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
            capture_output=True,
            text=True,
        )

    # Always prune in case git metadata drifted from the filesystem.
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "prune"],
        capture_output=True,
        text=True,
    )

    # Fallback — if the dir still exists after git's remove (shouldn't, but
    # crashes happen), blow it away. Safe: .wt/ is gitignored, contents
    # are worker-owned throwaways.
    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)

    if delete_branch:
        # Infer week from *listing* existing branches that match the slug —
        # we don't have the week number on this path. Use -D to force.
        slug = slug_pr_id(pr_id)
        branches = subprocess.run(
            ["git", "-C", str(repo), "branch", "--list", f"swarm/week-*-{slug}"],
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        for b in branches:
            name = b.strip().lstrip("*").strip()
            if name:
                subprocess.run(
                    ["git", "-C", str(repo), "branch", "-D", name],
                    capture_output=True,
                    text=True,
                )


__all__ = [
    "LeakedWorktree",
    "branch_name",
    "create",
    "iter_leaked",
    "remove",
    "slug_pr_id",
    "worktree_path",
]
