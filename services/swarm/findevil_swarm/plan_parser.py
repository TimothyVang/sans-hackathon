"""Parse TDD implementation plans into dispatchable ``PRSpec`` objects.

Spec #1 §3.1 task: read the plan markdown(s) for a given week and emit
an ordered ``PRSpec`` list that ``dispatch_node`` hands off to the
workers. Plans live at ``docs/plans/*.md`` and follow the
format described by ``superpowers:writing-plans``:

    ## Task N: <title>

    ### N.X Failing test — `Create: path/to/file.py`

    - Create: `path/a`
    - Modify: `path/b:LINE-LINE`

    Run: `<shell command>`
    Expected: PASS

The parser is intentionally conservative — it never invents a field.
Anything it can't infer falls back to an explicit, documented default
(e.g. missing L1 command → ``uv run pytest -xvs``).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from findevil_swarm.state import PRSpec

# ---------------------------------------------------------------------------
# Week → plan-file + task-range mapping.
#
# Each tuple is ``(plan_file_relative_path, (start_task, end_task_inclusive))``.
# ``end_task`` may be ``None`` to mean "all tasks from start onward".
# ---------------------------------------------------------------------------

WEEK_TO_PLANS: dict[int, list[tuple[str, tuple[int, int | None]]]] = {
    # Week 1 (Apr 22-28): sandbox bootstrap only.
    1: [("2026-04-23-sandbox-plan.md", (1, 6))],
    # Week 2 (Apr 29-May 5): Rust MCP scaffold + first 3 tools + M2 skeleton.
    2: [("2026-04-23-product-plan.md", (1, 5))],
    # Week 3 (May 6-12): remaining MCP tools + M2 complete.
    3: [("2026-04-23-product-plan.md", (6, 12))],
    # Week 4 (May 13-19): Python agent graph + supervisor + pools.
    4: [
        ("2026-04-23-product-plan.md", (13, 20)),
        ("2026-04-23-sandbox-plan.md", (7, 9)),
    ],
    # Week 5 (May 20-26): correlator + contradiction + HypothesisBoard.
    5: [("2026-04-23-product-plan.md", (21, 28))],
    # Week 6 (May 27-Jun 2): benchmark + leaderboard + glue.
    6: [
        ("2026-04-23-product-plan.md", (29, 35)),
        ("2026-04-23-orchestration-glue-plan.md", (1, 10)),
        ("2026-04-23-sandbox-plan.md", (10, 13)),
    ],
    # Week 7 (Jun 3-9): Lovable polish + MCP widgets + vocab audit.
    7: [("2026-04-23-product-plan.md", (36, None))],
    # Week 8 (Jun 10-15): demo + Devpost submission package.
    8: [("2026-04-23-orchestration-glue-plan.md", (11, None))],
}


# ---------------------------------------------------------------------------
# Core data class — intermediate representation before building PRSpec.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedTask:
    task_number: int
    title: str
    body: str
    files: list[str]
    l1_command: str
    language: str


# ---------------------------------------------------------------------------
# Regexes — tight enough to not bleed across tasks.
# ---------------------------------------------------------------------------

# Accept "## Task N: title", "## Task N (em-dash) title", or
# "## Task N - title". The em-dash form is what writing-plans-skill
# plans use; the colon form is the spec template. Both must match.
# We spell em-dash and en-dash as Unicode escapes so they appear in
# the compiled pattern but no source-code character can be confused
# for an ASCII hyphen by a future reader (ruff RUF001).
_TASK_HEADER_RE = re.compile(
    "^## Task (?P<num>\\d+)(?:\\.\\d+)?\\s*"
    "(?::|—|–|-)"  # noqa: RUF001 - regex must match U+2014/U+2013 dashes literally
    "\\s*(?P<title>.+?)\\s*$",
    re.MULTILINE,
)
_FILE_LINE_RE = re.compile(
    r"(?i)^[-*]\s*(?:Create|Modify|Test):\s*`(?P<path>[^`:]+)(?::\d+(?:-\d+)?)?`",
    re.MULTILINE,
)
_RUN_LINE_RE = re.compile(
    r"(?i)(?:^|\n)\s*Run:\s*`(?P<cmd>[^`]+)`",
)

# Dominant-extension classifier. Extensions not listed → python bucket,
# which is where Dockerfiles, YAML, and generic shell scripts land.
#
# .toml is intentionally NOT mapped — Cargo.toml is special-cased in
# detect_language() (it's the only TOML that signals Rust); pyproject.toml,
# uv.lock, etc. shouldn't accidentally route to the Rust worker.
_EXT_TO_LANG: dict[str, str] = {
    ".rs": "rust",
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "typescript",
    ".jsx": "typescript",
    ".mjs": "typescript",
    ".cjs": "typescript",
}

_DEFAULT_L1_COMMAND = "uv run pytest -xvs"


# ---------------------------------------------------------------------------
# Public helpers.
# ---------------------------------------------------------------------------


def detect_language(files: list[str]) -> str:
    """Infer the worker language from a list of file paths.

    Rules:
      * Count extensions against ``_EXT_TO_LANG``.
      * Pick the single most common mapped language.
      * If no mapped extensions appear (Dockerfiles, YAML, *.sh), default
        to ``"python"`` — those artifacts are swarm-routed through the
        Python worker's build system.
      * Tiebreak Rust > Python > TypeScript (Rust is the rarest in the
        plan so a single Rust file is usually intentional).
    """
    counts: Counter[str] = Counter()
    for p in files:
        # Cargo.toml special case — .toml alone isn't Rust-y, but if a
        # file named Cargo.toml appears, it's definitely Rust.
        name = Path(p).name
        if name == "Cargo.toml":
            counts["rust"] += 5
            continue
        ext = Path(p).suffix.lower()
        lang = _EXT_TO_LANG.get(ext)
        if lang is not None:
            counts[lang] += 1

    if not counts:
        return "python"

    # Tiebreak: rust > python > typescript when counts tie.
    priority = {"rust": 2, "python": 1, "typescript": 0}
    ranked = sorted(counts.items(), key=lambda kv: (kv[1], priority[kv[0]]), reverse=True)
    return ranked[0][0]


def extract_files(body: str) -> list[str]:
    """Extract referenced file paths from a task body.

    Only lines shaped like ``- Create:``, ``- Modify:``, ``- Test:``
    with a backticked path count. A ``path:LINE-LINE`` suffix is stripped.
    Returns a de-duplicated list in first-occurrence order.
    """
    seen: set[str] = set()
    out: list[str] = []
    for m in _FILE_LINE_RE.finditer(body):
        p = m.group("path").strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def extract_l1_command(body: str) -> str:
    """Extract the first ``Run: `<cmd>``` line or fall back to pytest."""
    m = _RUN_LINE_RE.search(body)
    if m is None:
        return _DEFAULT_L1_COMMAND
    return m.group("cmd").strip()


def parse_plan_file(plan_path: Path) -> list[ParsedTask]:
    """Parse one plan markdown into a list of ``ParsedTask``.

    Splits on ``## Task N:`` headers. Sub-tasks (``Task N.X``) belong to
    their parent and are not returned separately.
    """
    text = plan_path.read_text(encoding="utf-8")

    # Find all task start offsets + headers.
    headers = [
        (m.start(), int(m.group("num")), m.group("title").strip())
        for m in _TASK_HEADER_RE.finditer(text)
    ]
    if not headers:
        return []

    # For each task header, the body runs until the next header or EOF.
    tasks: list[ParsedTask] = []
    seen_numbers: set[int] = set()
    for i, (offset, num, title) in enumerate(headers):
        if num in seen_numbers:
            continue  # defensive — should never happen with well-formed plans
        seen_numbers.add(num)
        end = headers[i + 1][0] if i + 1 < len(headers) else len(text)
        body = text[offset:end]
        files = extract_files(body)
        l1 = extract_l1_command(body)
        tasks.append(
            ParsedTask(
                task_number=num,
                title=title[:72],  # PRSpec title cap
                body=body,
                files=files,
                l1_command=l1,
                language=detect_language(files),
            )
        )
    return tasks


def _filter_task_range(
    tasks: list[ParsedTask], task_range: tuple[int, int | None]
) -> list[ParsedTask]:
    start, end = task_range
    if end is None:
        return [t for t in tasks if t.task_number >= start]
    return [t for t in tasks if start <= t.task_number <= end]


def _task_to_prspec(task: ParsedTask, week: int, plan_file: str) -> PRSpec:
    """Build a ``PRSpec`` from a ``ParsedTask``. Never invents fields."""
    pr_id = f"week{week}-{task.language}-{_slugify(task.title)}-t{task.task_number}"
    description = (
        f"**From:** `docs/plans/{plan_file}` Task {task.task_number}\n\n"
        f"{task.body.strip()[:4000]}"
    )
    return PRSpec(
        pr_id=pr_id,
        week=week,
        language=task.language,
        title=task.title,
        description=description,
        files_expected=task.files,
        l1_command=task.l1_command,
        token_ceiling=500_000,
        max_turns=40,
        depends_on=[],
    )


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(s: str) -> str:
    """Slugify for use in a pr_id. Lowercase, hyphenated, trimmed."""
    out = _SLUG_RE.sub("-", s.lower()).strip("-")
    return out[:40] if len(out) > 40 else out


def parse_week(week: int, plans_dir: Path) -> list[PRSpec]:
    """Resolve the week-to-plan mapping and emit an ordered ``PRSpec`` list.

    Raises ``ValueError`` for unknown weeks. Empty list is a possible
    legitimate return value (e.g. if a plan hasn't landed yet) but is
    not silently hidden behind an unknown-week exception.
    """
    if week not in WEEK_TO_PLANS:
        raise ValueError(f"week {week} is outside the supported range 1..8")

    specs: list[PRSpec] = []
    for plan_file, task_range in WEEK_TO_PLANS[week]:
        plan_path = plans_dir / plan_file
        if not plan_path.is_file():
            # Plan not on disk yet — skip. Production run would have
            # all plans present from day 1; tests tolerate absence.
            continue
        tasks = parse_plan_file(plan_path)
        for t in _filter_task_range(tasks, task_range):
            specs.append(_task_to_prspec(t, week, plan_file))
    return specs


__all__ = [
    "WEEK_TO_PLANS",
    "ParsedTask",
    "detect_language",
    "extract_files",
    "extract_l1_command",
    "parse_plan_file",
    "parse_week",
]
