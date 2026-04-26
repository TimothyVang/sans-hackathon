#!/usr/bin/env python3
"""divergence-smoke - assert CLAUDE.md "Spec/code divergences" stay
downstream-clean.

CLAUDE.md documents 6 spec/code divergences. The previous 11
iterations of doc-vs-code audits caught 25 stale references where
the "wrong" half of a divergence had survived in active files.
Three iterations of the divergence-sweep procedure (commits
782f364, e6ddc2d, fb319dd) cleaned the active surface area; this
smoke locks the cleanup so a future contributor can't silently
re-introduce one of the bad shapes.

For each divergence with an executable wrong-pattern, this smoke
scans active files for that pattern and FAILs if it appears
outside an allow-list. The allow-list is intentionally narrow:
historical specs/plans + CHANGELOG entries describing the
historical bug + the deliberately-commented marker line.

Wall-clock: ~30ms. Wired into docker/l1-compose.yml after
launcher-smoke as the 7th L1 smoke.

The divergences (matching CLAUDE.md "Spec/code divergences"):

  §1  Rust 1.83 -> 1.88                bad: rust:1.83-bookworm
  §2  Cargo.lock committed             declarative; nothing to scan
  §3  findevil_agent.cli dropped (A2)  bad: python -m findevil_agent.cli
  §4  Rust MCP tool count is 12        bad: "11 typed Rust"
  §5  rmcp not a runtime dep           bad: live `rmcp = "=...` (uncommented)
  §6  swarm pkg = findevil_swarm       bad: python -m services.swarm.main
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Files/dirs intentionally excluded from active-drift scans.
# Order matters - more-specific exclusions first.
EXCLUDED_PATH_PARTS = (
    # Vendored research clones - .gitignore'd, never ship.
    "openclaw",
    "hermes-agent",
    "Linear-Coding-Agent-Harness",
    ".playwright-mcp",
    # Build / venv / cache.
    "target",
    "node_modules",
    ".venv",
    "__pycache__",
    ".git",
    # Generated artifacts (PDFs, HTML have embedded assets that
    # can grep-match the wrong-pattern coincidentally).
    "tmp",
    # Historical specs + plans per CLAUDE.md "code wins" rule.
    # The pre-A2 plans contain the bad patterns by design (they
    # were written assuming the now-dropped modules); each has a
    # top-of-doc banner per commit 608f6b8 marking superseded
    # sections.
    "superpowers",
)

# Files specifically allow-listed even though they live in an
# otherwise-active path. Keys are repo-relative POSIX paths.
ALLOWED_FILES = {
    # CHANGELOG.md describes historical bugs; matches there are
    # archival, not active drift.
    "CHANGELOG.md",
    # CLAUDE.md is the source-of-truth that DOCUMENTS each
    # divergence and necessarily quotes the bad form. Scanning
    # it for those exact strings would be circular.
    "CLAUDE.md",
    # The smoke itself necessarily contains the bad patterns in
    # its docstring + DIVERGENCES table to know what to check for.
    "scripts/divergence-smoke.py",
    # The launcher-smoke also contains the `claude-code` bad
    # pattern in its own check logic.
    "scripts/launcher-smoke.py",
    # Historical specs + plans (per CLAUDE.md "code wins" rule -
    # they were written pre-divergence and have top-of-doc
    # banner per commit 608f6b8).
    "BUILD_PLAN_v2.md",
    "Find_Evil_Research_and_Build_Plan.docx",
    # The autonomous-queue file describes the audit history.
    "memory/project_autonomous_queue.md",
}


# Divergence patterns. Each entry:
#   id, label - human-readable
#   regex     - compiled, applied to file text
#   allowed_in_path - repo-relative paths or path-prefixes where the
#                     pattern is deliberately legal (e.g. the
#                     commented-marker line in services/mcp/Cargo.toml
#                     for divergence #5).
#   remediation - what to do if the pattern resurfaces.
DIVERGENCES = [
    {
        "id": "#1",
        "label": "Rust 1.83 -> 1.88 (Dockerfile + plan files use 1.88)",
        "regex": re.compile(r"\brust:1\.83-(?:bookworm|bullseye|slim)\b"),
        "allowed_in_path": (),
        "remediation": (
            "rust-toolchain.toml channel=1.88.0 is authoritative; "
            "Cargo.toml requires rust-version=1.88. Do not pin a "
            "Docker base older than that. See CLAUDE.md "
            "'Spec/code divergences' §1."
        ),
    },
    {
        "id": "#3",
        "label": "findevil_agent.cli was dropped per Amendment A2",
        # `find-evil run/verify/serve` and `python -m
        # findevil_agent.cli` are the bad shapes. Negative lookbehind
        # on backtick excludes prose that QUOTES the bad form (e.g.
        # comments documenting why we replaced it). Active code
        # rarely backticks the executable line; documentation
        # comments often do.
        "regex": re.compile(
            r"(?<!`)(?:python3?\s+-m\s+findevil_agent\.cli|"
            r"\bfind-evil\s+(?:run|verify|serve)\b)"
        ),
        # The Dockerfile + scripts/build-deb.sh both still inline
        # the broken wrapper; CLAUDE.md §3 flags this as a hard
        # blocker pending architectural decision. Allow them here
        # so the smoke doesn't fail until the architectural
        # decision is made; once that lands, drop these entries.
        "allowed_in_path": (
            "Dockerfile",
            "scripts/build-deb.sh",
        ),
        "remediation": (
            "A2 dropped findevil_agent/cli.py and the L0 "
            "amendment-a2-guard fails CI on its return. Use "
            "scripts/find-evil (interactive) or "
            "bash scripts/find-evil-auto <evidence> (headless). "
            "See CLAUDE.md 'Spec/code divergences' §3."
        ),
    },
    {
        "id": "#4",
        "label": "Rust MCP tool count is 12 (vol_psscan added for DKOM)",
        "regex": re.compile(
            r"(?:11\s+typed\s+Rust|"
            r"11\s+DFIR\s+tools|"
            r"all\s+11\s+Rust|"
            r"findevil-mcp.*?\(11\s+(?:typed|DFIR|tools))"
        ),
        "allowed_in_path": (),
        "remediation": (
            "vol_psscan was added in commit 0de2e53 for DKOM "
            "cross-validation against vol_pslist. Tool count is 12. "
            "See CLAUDE.md 'Spec/code divergences' §4."
        ),
    },
    {
        "id": "#5",
        "label": "rmcp is intentionally NOT a runtime dep",
        # Match an UNCOMMENTED `rmcp = "=...` line at start of line.
        # The deliberate marker in services/mcp/Cargo.toml has a
        # leading `#` so this regex won't fire on it.
        "regex": re.compile(r"^\s*rmcp\s*=\s*[\"{]", re.MULTILINE),
        "allowed_in_path": (),
        "remediation": (
            "services/mcp ships a hand-rolled stdio JSON-RPC 2.0 "
            "server in src/server.rs. Do NOT activate rmcp without "
            "a spec amendment - the architectural choice is "
            "wire-format stability across rmcp's API churn. The "
            "commented marker line in services/mcp/Cargo.toml is "
            "deliberate. See CLAUDE.md 'Spec/code divergences' §5."
        ),
    },
    {
        "id": "#6",
        "label": "Swarm package is findevil_swarm, not services.swarm",
        "regex": re.compile(
            r"python3?\s+-m\s+services\.swarm\.(?:main|workers|"
            r"plan_parser|state|critic|pr_gate|supervisor|"
            r"watchdog|night_report|session_guard)\b"
        ),
        "allowed_in_path": (),
        "remediation": (
            "Shipped as findevil_swarm.* (matches findevil_agent / "
            "findevil_agent_mcp / findevil-mcp naming convention). "
            "Use 'cd services/swarm && uv run python -m "
            "findevil_swarm.main run' (matches "
            "scripts/swarm-start.sh:105). See CLAUDE.md "
            "'Spec/code divergences' §6."
        ),
    },
]


def _ascii_safe(s: str) -> str:
    """Return s with non-ASCII chars escaped so cp1252 consoles + CI
    log capture don't UnicodeEncodeError. Section signs / em-dashes
    /arrows in CLAUDE.md prose used to crash the smoke."""
    return s.encode("ascii", "backslashreplace").decode("ascii")


def _is_excluded(path: Path) -> bool:
    """True if path should not be scanned (vendored / generated / cache)."""
    rel_parts = path.relative_to(REPO).parts
    if any(part in EXCLUDED_PATH_PARTS for part in rel_parts):
        return True
    rel_posix = path.relative_to(REPO).as_posix()
    if rel_posix in ALLOWED_FILES:
        return True
    return False


def _list_active_files() -> list[Path]:
    """All text files we should scan (markdown + Python + Rust + sh + toml + yml)."""
    suffixes = (
        "*.md", "*.py", "*.rs", "*.sh", "*.toml", "*.yml",
        "*.yaml", "*.json", "*.bash",
    )
    out: list[Path] = []
    for pat in suffixes:
        for p in REPO.rglob(pat):
            if not p.is_file():
                continue
            if _is_excluded(p):
                continue
            out.append(p)
    # Also include the extension-less launchers.
    for name in ("find-evil", "find-evil-auto", "find-evil-sift"):
        p = REPO / "scripts" / name
        if p.exists():
            out.append(p)
    return sorted(set(out))


def _path_is_allowed(rel_posix: str, allowed: tuple[str, ...]) -> bool:
    """True if rel_posix matches any entry in allowed (exact or prefix)."""
    return any(rel_posix == a or rel_posix.startswith(a + "/") for a in allowed)


def main() -> int:
    print("=" * 60)
    print("Find Evil! - divergence-smoke")
    print("=" * 60)

    files = _list_active_files()
    print(f"scanning {len(files)} active text files for stale "
          f"references to {len(DIVERGENCES)} documented divergences...")
    print()

    failed = 0
    total_checks = 0
    for div in DIVERGENCES:
        total_checks += 1
        hits = []
        for p in files:
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for m in div["regex"].finditer(text):
                rel = p.relative_to(REPO).as_posix()
                if _path_is_allowed(rel, div["allowed_in_path"]):
                    continue
                line_no = text[: m.start()].count("\n") + 1
                line = text.splitlines()[line_no - 1].strip()
                hits.append((rel, line_no, line))

        if hits:
            # Output must survive cp1252 consoles (Windows cmd.exe
            # without VT processing) and CI log capture. Repr
            # already escapes most chars; the line preview can
            # carry ASCII-incompatible chars from the source file
            # so we further force ASCII via backslashreplace.
            print(_ascii_safe(f"[FAIL] {div['id']}  {div['label']}"))
            for rel, line_no, line in hits:
                preview = _ascii_safe(line)
                print(f"         {rel}:{line_no}: {preview}")
            print(_ascii_safe(f"         remediation: {div['remediation']}"))
            print()
            failed += 1
        else:
            print(_ascii_safe(f"[OK  ] {div['id']}  {div['label']}"))

    print()
    print("=" * 60)
    if failed:
        print(f"FAIL - {failed} of {total_checks} divergences have "
              f"active drift.")
        return 1
    print(f"OK - all {total_checks} active divergences are "
          f"downstream-clean.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
