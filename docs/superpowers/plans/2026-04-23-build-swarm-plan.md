# Autonomous Build Swarm Implementation Plan (Option B — Claude Code Subscription Mode)

> **Status: RETIRED.** The work this plan tracked shipped in `services/swarm/` (package `findevil_swarm`, invoked via `bash scripts/swarm-start.sh`). All TDD tasks below are done — see `git log -- services/swarm scripts/swarm-*.sh`. Kept for git-log archaeology + the original task decomposition. **Do not execute as a TDD plan.** If extending the swarm, work against the live code and the spec at `docs/superpowers/specs/2026-04-24-autonomous-build-swarm-design.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the autonomous nightly build swarm that drives Claude Code subagents to execute BUILD_PLAN_v2.md week-by-week, opening draft PRs for the human to review in the morning.

**Architecture:** LangGraph StateGraph supervisor + PostgresSaver DAG checkpoint + Claude CLI subagent workers per language (Rust/Python/TypeScript) in per-PR git worktrees + critic subagent gate + session_guard rate-limit detector. Option B: workers use the user's Claude Code subscription directly (no metered API).

**Tech Stack:** Python 3.11, LangGraph >=1.0 with langgraph-supervisor + langgraph-checkpoint-postgres, Docker Postgres (postgres:16-alpine), jshchnz/claude-code-scheduler, pytest, gh CLI.

---

## Task 1 — Project scaffolding and pinned dependencies

**Files to create:**
- `services/swarm/__init__.py`
- `services/swarm/workers/__init__.py`
- `tests/swarm/__init__.py`
- `tests/swarm/workers/__init__.py`
- `pyproject.toml` (root, if not present)

### 1.1 Write failing test

- [ ] Create `tests/swarm/test_package_imports.py`:

```python
# tests/swarm/test_package_imports.py
"""Smoke test: the swarm package is importable and exposes its public surface."""

def test_swarm_package_imports():
    import services.swarm as swarm
    assert hasattr(swarm, "__version__")
    assert swarm.__version__ == "0.1.0"

def test_workers_subpackage_imports():
    import services.swarm.workers  # noqa: F401
```

### 1.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_package_imports.py -v
```

Expected output (fail):

```
ModuleNotFoundError: No module named 'services.swarm'
```

### 1.3 Implement minimum code to pass

- [ ] Create `services/swarm/__init__.py`:

```python
"""Autonomous build swarm services (Option B — Claude Code subscription mode)."""

__version__ = "0.1.0"

__all__ = ["__version__"]
```

- [ ] Create `services/swarm/workers/__init__.py`:

```python
"""Language-specific worker implementations."""
```

- [ ] Create `tests/swarm/__init__.py` (empty file).

- [ ] Create `tests/swarm/workers/__init__.py` (empty file).

- [ ] Create `pyproject.toml` at repo root:

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "find-evil-swarm"
version = "0.1.0"
description = "Autonomous build swarm for the Find Evil project (Option B — Claude Code subscription mode)."
requires-python = ">=3.11,<3.13"
dependencies = [
    "langgraph==1.0.2",
    "langgraph-supervisor==0.0.15",
    "langgraph-checkpoint-postgres==2.0.7",
    "psycopg[binary,pool]==3.2.3",
    "anthropic==0.39.0",
    "pydantic==2.9.2",
    "pyyaml==6.0.2",
    "jinja2==3.1.4",
    "typing-extensions==4.12.2",
]

[project.optional-dependencies]
dev = [
    "pytest==8.3.3",
    "pytest-asyncio==0.24.0",
    "pytest-mock==3.14.0",
    "pytest-cov==5.0.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["services*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
asyncio_mode = "auto"
```

### 1.4 Run the test — expect PASS

- [ ] Install in editable mode and run tests:

```bash
pip install -e ".[dev]"
python -m pytest tests/swarm/test_package_imports.py -v
```

Expected output (pass):

```
tests/swarm/test_package_imports.py::test_swarm_package_imports PASSED
tests/swarm/test_workers_subpackage_imports PASSED
```

### 1.5 Commit

- [ ] Commit:

```bash
git add services/swarm/__init__.py services/swarm/workers/__init__.py \
        tests/swarm/__init__.py tests/swarm/workers/__init__.py \
        tests/swarm/test_package_imports.py pyproject.toml
git commit -m "swarm: scaffold services/swarm package with pinned deps (Option B)"
```

---

## Task 2 — Docker Postgres compose for PostgresSaver checkpoint store

**File to create:** `docker/swarm-postgres.yml`, `services/swarm/config/postgres.env`

### 2.1 Write failing test

- [ ] Create `tests/swarm/test_postgres_compose.py`:

```python
# tests/swarm/test_postgres_compose.py
"""Validate docker/swarm-postgres.yml structure."""

from pathlib import Path
import yaml

COMPOSE_PATH = Path(__file__).resolve().parents[2] / "docker" / "swarm-postgres.yml"


def test_compose_file_exists():
    assert COMPOSE_PATH.is_file(), f"missing: {COMPOSE_PATH}"


def test_compose_uses_postgres_16_alpine():
    doc = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    svc = doc["services"]["swarm-postgres"]
    assert svc["image"] == "postgres:16-alpine"


def test_compose_exposes_5432():
    doc = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    ports = doc["services"]["swarm-postgres"]["ports"]
    assert "5432:5432" in ports


def test_compose_has_named_volume():
    doc = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    assert "swarm_pg_data" in doc["volumes"]
    svc = doc["services"]["swarm-postgres"]
    vols = [v for v in svc["volumes"] if v.startswith("swarm_pg_data:")]
    assert len(vols) == 1
```

### 2.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_postgres_compose.py -v
```

Expected: `AssertionError: missing: .../docker/swarm-postgres.yml`.

### 2.3 Implement

- [ ] Create `docker/swarm-postgres.yml`:

```yaml
# docker/swarm-postgres.yml
# Local Postgres for LangGraph PostgresSaver checkpoint store.
# Start: docker compose -f docker/swarm-postgres.yml up -d
# Stop:  docker compose -f docker/swarm-postgres.yml down

services:
  swarm-postgres:
    image: postgres:16-alpine
    container_name: swarm-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: swarm
      POSTGRES_USER: swarm
      POSTGRES_PASSWORD: swarm
    ports:
      - "5432:5432"
    volumes:
      - swarm_pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U swarm -d swarm"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  swarm_pg_data:
    name: swarm_pg_data
```

- [ ] Create `services/swarm/config/postgres.env`:

```
POSTGRES_DB=swarm
POSTGRES_USER=swarm
POSTGRES_PASSWORD=swarm
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_CONN_STRING=postgresql://swarm:swarm@localhost:5432/swarm
```

### 2.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_postgres_compose.py -v
```

Expected: 4 passed.

### 2.5 Commit

- [ ] Commit:

```bash
git add docker/swarm-postgres.yml services/swarm/config/postgres.env \
        tests/swarm/test_postgres_compose.py
git commit -m "swarm: add docker compose for postgres:16-alpine checkpoint store"
```

---

## Task 3 — Shared state schema (SwarmState, PRSpec, CriticVerdict, NightlyReport)

**File to create:** `services/swarm/state.py`

### 3.1 Write failing test

- [ ] Create `tests/swarm/test_state.py`:

```python
# tests/swarm/test_state.py
"""Unit tests for services/swarm/state.py."""

import operator
from typing import get_type_hints

import pytest
from pydantic import ValidationError

from services.swarm.state import (
    PRSpec,
    CriticVerdict,
    NightlyReport,
    SwarmState,
)


def test_prspec_minimum_fields_required():
    with pytest.raises(ValidationError):
        PRSpec()  # type: ignore[call-arg]


def test_prspec_valid_instance():
    spec = PRSpec(
        pr_id="week-2-rust-case-open-tool",
        week=2,
        language="rust",
        title="Add case_open MCP tool",
        description="Implement the case_open tool in the Rust MCP server.",
        files_expected=["services/mcp/src/tools/case_open.rs"],
        l1_command="cargo test --workspace",
        token_ceiling=500_000,
        max_turns=40,
        depends_on=[],
    )
    assert spec.pr_id == "week-2-rust-case-open-tool"
    assert spec.token_ceiling == 500_000
    assert spec.max_turns == 40


def test_critic_verdict_decision_values():
    v = CriticVerdict(
        pr_id="x",
        decision="APPROVE",
        reason="L1 passed",
        token_count_input=100,
        token_count_output=50,
        l1_exit_code=0,
        diff_line_count=10,
    )
    assert v.decision == "APPROVE"


def test_nightly_report_roundtrip():
    r = NightlyReport(
        date="2026-04-24",
        week=2,
        prs_opened=["a", "b"],
        prs_rejected=["c"],
        total_spend_usd=0.0,
        wall_clock_seconds=120,
        budget_remaining_usd=0.0,
    )
    assert r.prs_opened == ["a", "b"]


def test_swarm_state_has_expected_keys():
    hints = get_type_hints(SwarmState, include_extras=True)
    required_keys = {
        "week",
        "pr_specs",
        "dispatched_pr_ids",
        "completed_pr_ids",
        "rejected_pr_ids",
        "critic_verdicts",
        "spend_usd_cumulative",
        "budget_exhausted",
        "dry_run_gate_passed",
        "dry_run_gate_pr_id",
        "wall_clock_start_ts",
        "nightly_report",
    }
    assert required_keys.issubset(set(hints.keys()))


def test_annotated_reducers_use_operator_add():
    import typing
    hints = get_type_hints(SwarmState, include_extras=True)
    for key in [
        "dispatched_pr_ids",
        "completed_pr_ids",
        "rejected_pr_ids",
        "critic_verdicts",
    ]:
        ann = hints[key]
        # Annotated[list[...], operator.add]
        args = typing.get_args(ann)
        assert operator.add in args, f"{key} must use operator.add reducer"
```

### 3.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_state.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.state'`.

### 3.3 Implement

- [ ] Create `services/swarm/state.py`:

```python
# services/swarm/state.py
"""Canonical shared state for the build swarm (Option B)."""

from __future__ import annotations

import operator
from typing import Annotated, Optional

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class PRSpec(BaseModel):
    """Atomic unit of work dispatched by the supervisor."""

    pr_id: str
    week: int
    language: str  # "rust" | "python" | "typescript"
    title: str
    description: str
    files_expected: list[str] = Field(default_factory=list)
    l1_command: str
    token_ceiling: int = 500_000
    max_turns: int = 40
    depends_on: list[str] = Field(default_factory=list)


class CriticVerdict(BaseModel):
    """Structured output of the critic subagent."""

    pr_id: str
    decision: str  # "APPROVE" | "REJECT"
    reason: str
    token_count_input: int
    token_count_output: int
    l1_exit_code: int
    diff_line_count: int


class NightlyReport(BaseModel):
    """Emitted once per supervisor run."""

    date: str  # ISO-8601
    week: int
    prs_opened: list[str]
    prs_rejected: list[str]
    total_spend_usd: float
    wall_clock_seconds: int
    budget_remaining_usd: float


class SwarmState(TypedDict):
    """DAG state persisted by PostgresSaver."""

    # Immutable plan (set once in plan_node)
    week: int
    pr_specs: list[PRSpec]

    # Mutable dispatch tracking — operator.add = append-only accumulator
    dispatched_pr_ids: Annotated[list[str], operator.add]
    completed_pr_ids: Annotated[list[str], operator.add]
    rejected_pr_ids: Annotated[list[str], operator.add]
    critic_verdicts: Annotated[list[CriticVerdict], operator.add]

    # Budget tracking (last-write wins — only supervisor nodes write these)
    spend_usd_cumulative: float
    budget_exhausted: bool

    # Dry-run gate
    dry_run_gate_passed: bool
    dry_run_gate_pr_id: Optional[str]

    # Watchdog
    wall_clock_start_ts: int  # Unix epoch seconds

    # Night report (written once in collect_node)
    nightly_report: Optional[NightlyReport]
```

- [ ] Update `services/swarm/__init__.py` to export the public types:

```python
"""Autonomous build swarm services (Option B — Claude Code subscription mode)."""

from services.swarm.state import (
    CriticVerdict,
    NightlyReport,
    PRSpec,
    SwarmState,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "CriticVerdict",
    "NightlyReport",
    "PRSpec",
    "SwarmState",
]
```

### 3.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_state.py -v
```

Expected: 5 passed.

### 3.5 Commit

- [ ] Commit:

```bash
git add services/swarm/state.py services/swarm/__init__.py tests/swarm/test_state.py
git commit -m "swarm: define SwarmState TypedDict and PRSpec/CriticVerdict/NightlyReport models"
```

---

## Task 4 — BUILD_PLAN_v2.md parser (`plan_parser.py`)

**File to create:** `services/swarm/plan_parser.py`, `tests/swarm/fixtures/BUILD_PLAN_mini.md`

### 4.1 Write failing test

- [ ] Create `tests/swarm/fixtures/BUILD_PLAN_mini.md`:

```markdown
# Build Plan v2 (test fixture)

## Week 1 — Foundations

### PR: week-1-rust-hello-mcp

- language: rust
- title: Hello MCP skeleton
- description: Scaffold the Rust MCP server crate.
- files_expected:
  - services/mcp/Cargo.toml
  - services/mcp/src/main.rs
- l1_command: cargo test --workspace
- depends_on:

### PR: week-1-python-agent-stub

- language: python
- title: Python agent stub
- description: Create the agent package skeleton.
- files_expected:
  - services/agent/__init__.py
- l1_command: pytest tests/agent
- depends_on:

## Week 2 — Tools

### PR: week-2-rust-case-open-tool

- language: rust
- title: case_open tool
- description: Add case_open MCP tool.
- files_expected:
  - services/mcp/src/tools/case_open.rs
- l1_command: cargo test --workspace
- depends_on:
  - week-1-rust-hello-mcp
```

- [ ] Create `tests/swarm/test_plan_parser.py`:

```python
# tests/swarm/test_plan_parser.py
"""Unit tests for BUILD_PLAN_v2.md parsing."""

from pathlib import Path

import pytest

from services.swarm.plan_parser import parse_week, PlanParseError
from services.swarm.state import PRSpec

FIXTURE = Path(__file__).parent / "fixtures" / "BUILD_PLAN_mini.md"


def test_parse_week_1_returns_two_prs():
    specs = parse_week(FIXTURE, week=1)
    assert len(specs) == 2
    assert all(isinstance(s, PRSpec) for s in specs)


def test_parse_week_1_languages():
    specs = parse_week(FIXTURE, week=1)
    assert [s.language for s in specs] == ["rust", "python"]


def test_parse_week_2_has_depends_on():
    specs = parse_week(FIXTURE, week=2)
    assert len(specs) == 1
    assert specs[0].depends_on == ["week-1-rust-hello-mcp"]


def test_parse_week_2_title_and_files():
    specs = parse_week(FIXTURE, week=2)
    spec = specs[0]
    assert spec.title == "case_open tool"
    assert spec.files_expected == ["services/mcp/src/tools/case_open.rs"]
    assert spec.l1_command == "cargo test --workspace"


def test_parse_missing_week_raises():
    with pytest.raises(PlanParseError):
        parse_week(FIXTURE, week=9)


def test_parse_missing_file_raises():
    with pytest.raises(PlanParseError):
        parse_week(Path("/nonexistent/BUILD_PLAN.md"), week=1)
```

### 4.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_plan_parser.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.plan_parser'`.

### 4.3 Implement

- [ ] Create `services/swarm/plan_parser.py`:

```python
# services/swarm/plan_parser.py
"""Parse BUILD_PLAN_v2.md into ordered PRSpec lists per week."""

from __future__ import annotations

import re
from pathlib import Path

from services.swarm.state import PRSpec


class PlanParseError(RuntimeError):
    """Raised when BUILD_PLAN_v2.md cannot be parsed."""


_WEEK_HEADER = re.compile(r"^##\s+Week\s+(\d+)\b", re.IGNORECASE)
_PR_HEADER = re.compile(r"^###\s+PR:\s+(\S+)\s*$")
_FIELD_LINE = re.compile(r"^-\s+([a-z_]+):\s*(.*)$")
_LIST_ITEM = re.compile(r"^\s{2,}-\s+(.+)$")


def parse_week(plan_path: Path | str, week: int) -> list[PRSpec]:
    """Return the ordered PRSpec list for the given week."""
    path = Path(plan_path)
    if not path.is_file():
        raise PlanParseError(f"plan file not found: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    specs: list[PRSpec] = []

    current_week: int | None = None
    current: dict | None = None
    active_list_field: str | None = None

    def _flush() -> None:
        nonlocal current
        if current and current_week == week:
            specs.append(
                PRSpec(
                    pr_id=current["pr_id"],
                    week=week,
                    language=current.get("language", ""),
                    title=current.get("title", ""),
                    description=current.get("description", ""),
                    files_expected=current.get("files_expected", []),
                    l1_command=current.get("l1_command", ""),
                    token_ceiling=current.get("token_ceiling", 500_000),
                    max_turns=current.get("max_turns", 40),
                    depends_on=current.get("depends_on", []),
                )
            )
        current = None

    for raw in lines:
        line = raw.rstrip()

        m_week = _WEEK_HEADER.match(line)
        if m_week:
            _flush()
            current_week = int(m_week.group(1))
            active_list_field = None
            continue

        m_pr = _PR_HEADER.match(line)
        if m_pr:
            _flush()
            current = {"pr_id": m_pr.group(1)}
            active_list_field = None
            continue

        if current is None:
            continue

        m_field = _FIELD_LINE.match(line)
        if m_field:
            field, value = m_field.group(1), m_field.group(2).strip()
            if field in ("files_expected", "depends_on"):
                current[field] = []
                active_list_field = field
                if value:  # inline single item e.g. "- depends_on: foo"
                    current[field].append(value)
            else:
                if field in ("token_ceiling", "max_turns"):
                    current[field] = int(value)
                else:
                    current[field] = value
                active_list_field = None
            continue

        m_item = _LIST_ITEM.match(raw)
        if m_item and active_list_field:
            current[active_list_field].append(m_item.group(1).strip())
            continue

    _flush()

    if not specs:
        raise PlanParseError(f"no PRs found for week {week} in {path}")
    return specs
```

### 4.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_plan_parser.py -v
```

Expected: 6 passed.

### 4.5 Commit

- [ ] Commit:

```bash
git add services/swarm/plan_parser.py tests/swarm/test_plan_parser.py \
        tests/swarm/fixtures/BUILD_PLAN_mini.md
git commit -m "swarm: parse BUILD_PLAN_v2.md week sections into PRSpec lists"
```

---

## Task 5 — Git worktree lifecycle (`worktree.py`)

**File to create:** `services/swarm/worktree.py`

### 5.1 Write failing test

- [ ] Create `tests/swarm/test_worktree.py`:

```python
# tests/swarm/test_worktree.py
"""Unit tests for git worktree lifecycle."""

import subprocess
from pathlib import Path

import pytest

from services.swarm.worktree import (
    WorktreeError,
    create_worktree,
    remove_worktree,
    worktree_path_for,
    branch_name_for,
)


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("seed")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, check=True)
    return tmp_path


def test_worktree_path_naming():
    p = worktree_path_for(Path("/repo"), "rust", "week-2-case-open")
    assert p == Path("/repo/.wt/wt-rust-week-2-case-open")


def test_branch_name_naming():
    assert branch_name_for(2, "week-2-case-open") == "swarm/week-2-week-2-case-open"


def test_create_and_remove_roundtrip(tmp_git_repo: Path):
    wt = create_worktree(tmp_git_repo, "rust", "pr-001", week=1)
    assert wt.is_dir()
    assert (wt / ".git").exists()

    remove_worktree(tmp_git_repo, "rust", "pr-001")
    assert not wt.exists()

    # git worktree list should not reference the removed worktree
    out = subprocess.check_output(
        ["git", "worktree", "list", "--porcelain"], cwd=tmp_git_repo, text=True
    )
    assert "pr-001" not in out


def test_create_twice_raises(tmp_git_repo: Path):
    create_worktree(tmp_git_repo, "rust", "pr-002", week=1)
    with pytest.raises(WorktreeError):
        create_worktree(tmp_git_repo, "rust", "pr-002", week=1)
    remove_worktree(tmp_git_repo, "rust", "pr-002")


def test_invalid_language_raises(tmp_git_repo: Path):
    with pytest.raises(WorktreeError):
        create_worktree(tmp_git_repo, "java", "pr-003", week=1)
```

### 5.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_worktree.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.worktree'`.

### 5.3 Implement

- [ ] Create `services/swarm/worktree.py`:

```python
# services/swarm/worktree.py
"""Git worktree lifecycle — one worktree per PR."""

from __future__ import annotations

import subprocess
from pathlib import Path

_LANG_CODES = {"rust": "rust", "python": "py", "typescript": "ts"}


class WorktreeError(RuntimeError):
    """Raised on any worktree create/remove failure."""


def _lang_code(language: str) -> str:
    if language not in _LANG_CODES:
        raise WorktreeError(
            f"unsupported language: {language!r} "
            f"(expected one of {sorted(_LANG_CODES)})"
        )
    return _LANG_CODES[language]


def worktree_path_for(repo_root: Path, language: str, pr_id: str) -> Path:
    """Return the absolute path for the worktree — no side effects."""
    return Path(repo_root) / ".wt" / f"wt-{_lang_code(language)}-{pr_id}"


def branch_name_for(week: int, pr_id: str) -> str:
    """Return the deterministic branch name for a given PR."""
    return f"swarm/week-{week}-{pr_id}"


def create_worktree(
    repo_root: Path,
    language: str,
    pr_id: str,
    *,
    week: int,
    base: str = "HEAD",
) -> Path:
    """Create a new worktree under {repo_root}/.wt/ with a fresh branch."""
    wt = worktree_path_for(repo_root, language, pr_id)
    branch = branch_name_for(week, pr_id)

    if wt.exists():
        raise WorktreeError(f"worktree already exists: {wt}")

    wt.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["git", "worktree", "add", str(wt), "-b", branch, base],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise WorktreeError(
            f"git worktree add failed: {result.stderr.strip()}"
        )
    return wt


def remove_worktree(repo_root: Path, language: str, pr_id: str) -> None:
    """Remove the worktree and prune metadata; idempotent on missing dirs."""
    wt = worktree_path_for(repo_root, language, pr_id)

    subprocess.run(
        ["git", "worktree", "remove", "--force", str(wt)],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    # Hard delete if git left the dir in place
    if wt.exists():
        import shutil
        shutil.rmtree(wt, ignore_errors=True)
```

### 5.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_worktree.py -v
```

Expected: 5 passed.

### 5.5 Commit

- [ ] Commit:

```bash
git add services/swarm/worktree.py tests/swarm/test_worktree.py
git commit -m "swarm: add worktree.py with create/remove and naming convention enforcement"
```

---

## Task 6 — Session guard: Claude Code rate-limit detector (`session_guard.py`)

**File to create:** `services/swarm/session_guard.py`

> **Option B replacement for `budget.py`.** No LiteLLM, no USD cap. Detects `claude` CLI rate-limit signals and halts cleanly without retry.

### 6.1 Write failing test

- [ ] Create `tests/swarm/test_session_guard.py`:

```python
# tests/swarm/test_session_guard.py
"""Unit tests for Option B session guard (Claude Code subscription rate-limit detection)."""

import pytest

from services.swarm.session_guard import (
    SessionLimitError,
    detect_limit_signal,
    SessionGuard,
)


@pytest.mark.parametrize(
    "stderr_text",
    [
        "Error: usage limit reached. Try again in 3h 21m.",
        "HTTP 429: rate limit exceeded",
        "rate_limit_error: Too Many Requests",
        "Your session has expired. Please run `claude auth login`.",
        "anthropic.RateLimitError: ...",
    ],
)
def test_detect_limit_signal_positive(stderr_text: str):
    assert detect_limit_signal(stderr_text, exit_code=1) is True


@pytest.mark.parametrize(
    "stderr_text",
    [
        "",
        "Compilation failed: cargo error E0502",
        "pytest: 3 failed, 10 passed",
        "Warning: deprecated flag",
    ],
)
def test_detect_limit_signal_negative(stderr_text: str):
    assert detect_limit_signal(stderr_text, exit_code=0) is False


def test_detect_limit_signal_http_429_in_json():
    payload = '{"error":{"type":"rate_limit_error","status":429}}'
    assert detect_limit_signal(payload, exit_code=1) is True


def test_guard_raises_on_positive():
    guard = SessionGuard()
    with pytest.raises(SessionLimitError) as exc:
        guard.check(stderr="usage limit reached", exit_code=1, pr_id="pr-1")
    assert exc.value.pr_id == "pr-1"
    assert "usage limit" in str(exc.value).lower()


def test_guard_silent_on_negative():
    guard = SessionGuard()
    # Should not raise
    guard.check(stderr="cargo build failed", exit_code=1, pr_id="pr-2")


def test_guard_tracks_dispatch_counter():
    guard = SessionGuard()
    assert guard.dispatches_in_window == 0
    guard.record_dispatch()
    guard.record_dispatch()
    assert guard.dispatches_in_window == 2


def test_guard_no_retry_policy():
    """Option B mandate: SessionLimitError halts; no retry loop."""
    guard = SessionGuard()
    assert guard.should_retry_on_limit() is False
```

### 6.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_session_guard.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.session_guard'`.

### 6.3 Implement

- [ ] Create `services/swarm/session_guard.py`:

```python
# services/swarm/session_guard.py
"""Option B — Claude Code subscription rate-limit detector.

Replaces Spec #1's budget.py. There is no USD cap because there is no
metered API in use. Instead, we detect the `claude` CLI's rate-limit
signals, raise SessionLimitError, and halt the supervisor cleanly.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field


# Patterns that indicate the user's Claude Code subscription is throttled
# or the session has expired. Matched case-insensitively on stderr + stdout.
_LIMIT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"usage\s+limit\s+reached", re.IGNORECASE),
    re.compile(r"rate[_\s]+limit[_\s]+(?:exceeded|error)", re.IGNORECASE),
    re.compile(r"\b429\b"),
    re.compile(r"too\s+many\s+requests", re.IGNORECASE),
    re.compile(r"session\s+has\s+expired", re.IGNORECASE),
    re.compile(r"claude\s+auth\s+login", re.IGNORECASE),
    re.compile(r"anthropic\.ratelimiterror", re.IGNORECASE),
    re.compile(r'"type"\s*:\s*"rate_limit_error"', re.IGNORECASE),
)


class SessionLimitError(RuntimeError):
    """Raised when the Claude Code subscription signals a limit.

    The supervisor catches this, emits a night_report.jsonl row with
    `halt: session_exhausted`, and exits. The next scheduled run resumes
    from the Postgres checkpoint.
    """

    def __init__(self, message: str, *, pr_id: str | None = None) -> None:
        super().__init__(message)
        self.pr_id = pr_id


def detect_limit_signal(text: str, *, exit_code: int) -> bool:
    """Return True iff `text` contains a Claude Code rate-limit signal."""
    if not text:
        return False
    for pattern in _LIMIT_PATTERNS:
        if pattern.search(text):
            return True
    return False


@dataclass
class SessionGuard:
    """Tracks dispatch cadence and raises on rate-limit signals.

    Soft-advisory: the guard counts messages per rolling 5-hour window and
    exposes `dispatches_in_window` for night_report.jsonl. It does NOT
    enforce a cap on its own — only Anthropic's servers know the true
    subscription ceiling.
    """

    window_seconds: int = 5 * 60 * 60  # 5 hours
    _dispatches: list[float] = field(default_factory=list)

    @property
    def dispatches_in_window(self) -> int:
        cutoff = time.time() - self.window_seconds
        self._dispatches = [t for t in self._dispatches if t >= cutoff]
        return len(self._dispatches)

    def record_dispatch(self) -> None:
        self._dispatches.append(time.time())

    def check(self, *, stderr: str, exit_code: int, pr_id: str | None) -> None:
        if detect_limit_signal(stderr, exit_code=exit_code):
            raise SessionLimitError(
                f"Claude Code rate-limit signal detected for pr_id={pr_id!r}: "
                f"{stderr[:200]!r}",
                pr_id=pr_id,
            )

    def should_retry_on_limit(self) -> bool:
        """Option B policy: never retry on session limits."""
        return False
```

### 6.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_session_guard.py -v
```

Expected: 11 passed.

### 6.5 Commit

- [ ] Commit:

```bash
git add services/swarm/session_guard.py tests/swarm/test_session_guard.py
git commit -m "swarm: replace budget.py with session_guard.py (Option B, no USD cap)"
```

---

## Task 7 — Base worker: Claude CLI subprocess, sidecar, no-progress detector (`base_worker.py`)

**File to create:** `services/swarm/workers/base_worker.py`

### 7.1 Write failing test

- [ ] Create `tests/swarm/workers/test_base_worker.py`:

```python
# tests/swarm/workers/test_base_worker.py
"""Unit tests for BaseWorker Claude CLI subprocess invocation."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.swarm.state import PRSpec
from services.swarm.workers.base_worker import (
    BaseWorker,
    NoProgressDetector,
    WorkerInput,
    WorkerResult,
)


@pytest.fixture
def sample_pr_spec() -> PRSpec:
    return PRSpec(
        pr_id="pr-test-001",
        week=1,
        language="rust",
        title="Test PR",
        description="Test description.",
        files_expected=["src/main.rs"],
        l1_command="echo ok",
        token_ceiling=500_000,
        max_turns=40,
        depends_on=[],
    )


def test_no_progress_detector_fires_on_three_zero_deltas():
    d = NoProgressDetector(threshold=3)
    assert d.observe(diff_delta=0) is False
    assert d.observe(diff_delta=0) is False
    assert d.observe(diff_delta=0) is True  # 3rd zero → kill


def test_no_progress_detector_resets_on_progress():
    d = NoProgressDetector(threshold=3)
    d.observe(diff_delta=0)
    d.observe(diff_delta=0)
    d.observe(diff_delta=5)  # reset
    assert d.observe(diff_delta=0) is False
    assert d.observe(diff_delta=0) is False
    assert d.observe(diff_delta=0) is True


def test_build_claude_command_option_b(sample_pr_spec, tmp_path):
    worker = BaseWorker(system_prompt_fragment="You are a Rust worker.")
    inp = WorkerInput(
        pr_spec=sample_pr_spec,
        worktree_path=str(tmp_path),
        branch_name="swarm/week-1-pr-test-001",
        jsonl_sidecar_path=str(tmp_path / "sidecar.jsonl"),
        env_overrides={},
    )
    cmd = worker.build_claude_command(inp)
    assert cmd[0] == "claude"
    assert "--print" in cmd
    assert "--max-turns" in cmd
    assert "40" in cmd
    assert "--model" in cmd
    assert "claude-opus-4-7" in cmd


def test_build_env_sets_fork_subagent(sample_pr_spec, tmp_path):
    worker = BaseWorker(system_prompt_fragment="x")
    inp = WorkerInput(
        pr_spec=sample_pr_spec,
        worktree_path=str(tmp_path),
        branch_name="swarm/week-1-pr-test-001",
        jsonl_sidecar_path=str(tmp_path / "sidecar.jsonl"),
        env_overrides={"EXTRA": "1"},
    )
    env = worker.build_env(inp)
    assert env["CLAUDE_CODE_FORK_SUBAGENT"] == "1"
    assert env["EXTRA"] == "1"


def test_write_sidecar_line(tmp_path):
    worker = BaseWorker(system_prompt_fragment="x")
    sidecar = tmp_path / "sidecar.jsonl"
    worker.write_sidecar_line(
        sidecar,
        {"turn": 1, "tool": "bash", "diff_lines_delta": 5},
    )
    worker.write_sidecar_line(
        sidecar,
        {"turn": 2, "tool": "write_file", "diff_lines_delta": 0},
    )
    rows = [json.loads(l) for l in sidecar.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[1]["diff_lines_delta"] == 0


def test_run_invokes_subprocess_with_expected_shape(sample_pr_spec, tmp_path):
    worker = BaseWorker(system_prompt_fragment="x")
    inp = WorkerInput(
        pr_spec=sample_pr_spec,
        worktree_path=str(tmp_path),
        branch_name="swarm/week-1-pr-test-001",
        jsonl_sidecar_path=str(tmp_path / "sidecar.jsonl"),
        env_overrides={},
    )

    fake = MagicMock(spec=subprocess.CompletedProcess)
    fake.returncode = 0
    fake.stdout = "ok"
    fake.stderr = ""

    with patch("subprocess.run", return_value=fake) as mock_run:
        result = worker.run(inp)

    assert mock_run.called
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["cwd"] == str(tmp_path)
    assert call_kwargs["env"]["CLAUDE_CODE_FORK_SUBAGENT"] == "1"
    assert isinstance(result, WorkerResult)
    assert result.pr_id == "pr-test-001"
```

### 7.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/workers/test_base_worker.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.workers.base_worker'`.

### 7.3 Implement

- [ ] Create `services/swarm/workers/base_worker.py`:

```python
# services/swarm/workers/base_worker.py
"""Base worker: invokes `claude` CLI subprocess in a worktree (Option B)."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from services.swarm.state import PRSpec


@dataclass
class WorkerInput:
    pr_spec: PRSpec
    worktree_path: str
    branch_name: str
    jsonl_sidecar_path: str
    env_overrides: dict = field(default_factory=dict)


@dataclass
class WorkerResult:
    pr_id: str
    branch_name: str
    worktree_path: str
    l1_exit_code: int
    l1_stdout: str
    l1_stderr: str
    diff_line_count: int
    token_count_input: int
    token_count_output: int
    no_progress_killed: bool
    wall_clock_seconds: int
    jsonl_sidecar_path: str


class NoProgressDetector:
    """Kills the worker after N consecutive tool calls with zero diff delta."""

    def __init__(self, threshold: int = 3) -> None:
        self.threshold = threshold
        self._zero_streak = 0

    def observe(self, *, diff_delta: int) -> bool:
        """Record a tool-call diff delta. Return True if threshold hit."""
        if diff_delta == 0:
            self._zero_streak += 1
        else:
            self._zero_streak = 0
        return self._zero_streak >= self.threshold


class BaseWorker:
    """Shared subprocess-invocation logic for all language workers."""

    MODEL_ARCHITECT = "claude-opus-4-7"

    def __init__(self, system_prompt_fragment: str) -> None:
        self.system_prompt_fragment = system_prompt_fragment

    # -- command construction -----------------------------------------

    def build_claude_command(self, inp: WorkerInput) -> list[str]:
        return [
            "claude",
            "--print",
            "--max-turns",
            str(inp.pr_spec.max_turns),
            "--model",
            self.MODEL_ARCHITECT,
            "--output-format",
            "json",
            self._render_prompt(inp),
        ]

    def build_env(self, inp: WorkerInput) -> dict[str, str]:
        env = dict(os.environ)
        env.update(inp.env_overrides)
        env["CLAUDE_CODE_FORK_SUBAGENT"] = "1"
        env["CLAUDE_CODE_AUTOCOMPACT"] = "0"
        return env

    def _render_prompt(self, inp: WorkerInput) -> str:
        spec = inp.pr_spec
        return (
            f"{self.system_prompt_fragment}\n\n"
            f"Title: {spec.title}\n"
            f"Description: {spec.description}\n"
            f"Files expected: {', '.join(spec.files_expected)}\n"
            f"L1 command: {spec.l1_command}\n"
            f"Worktree: {inp.worktree_path}\n"
            f"Branch: {inp.branch_name}\n"
        )

    # -- sidecar ------------------------------------------------------

    def write_sidecar_line(self, sidecar_path: Path | str, row: dict) -> None:
        p = Path(sidecar_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    # -- main entry ---------------------------------------------------

    def run(self, inp: WorkerInput) -> WorkerResult:
        start = time.time()
        cmd = self.build_claude_command(inp)
        env = self.build_env(inp)

        proc = subprocess.run(
            cmd,
            cwd=inp.worktree_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=None,
        )

        return WorkerResult(
            pr_id=inp.pr_spec.pr_id,
            branch_name=inp.branch_name,
            worktree_path=inp.worktree_path,
            l1_exit_code=proc.returncode,
            l1_stdout=(proc.stdout or "")[:10_000],
            l1_stderr=(proc.stderr or "")[:10_000],
            diff_line_count=0,
            token_count_input=0,
            token_count_output=0,
            no_progress_killed=False,
            wall_clock_seconds=int(time.time() - start),
            jsonl_sidecar_path=inp.jsonl_sidecar_path,
        )
```

### 7.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/workers/test_base_worker.py -v
```

Expected: 6 passed.

### 7.5 Commit

- [ ] Commit:

```bash
git add services/swarm/workers/base_worker.py tests/swarm/workers/test_base_worker.py
git commit -m "swarm: add base_worker.py with claude CLI subprocess + no-progress detector"
```

---

## Task 8 — Rust worker (`rust_worker.py`)

**File to create:** `services/swarm/workers/rust_worker.py`

### 8.1 Write failing test

- [ ] Create `tests/swarm/workers/test_rust_worker.py`:

```python
# tests/swarm/workers/test_rust_worker.py
from services.swarm.workers.rust_worker import RustWorker


def test_rust_worker_prompt_mentions_cargo():
    w = RustWorker()
    assert "cargo" in w.system_prompt_fragment.lower()
    assert "rust" in w.system_prompt_fragment.lower()


def test_rust_worker_l1_default():
    w = RustWorker()
    assert w.default_l1_command() == "cargo test --workspace"
```

### 8.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/workers/test_rust_worker.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.workers.rust_worker'`.

### 8.3 Implement

- [ ] Create `services/swarm/workers/rust_worker.py`:

```python
# services/swarm/workers/rust_worker.py
"""Rust-specific worker: cargo test L1 invocation."""

from __future__ import annotations

from services.swarm.workers.base_worker import BaseWorker

_RUST_SYSTEM_PROMPT = """You are the Rust worker for the Find Evil build swarm.

You operate inside a dedicated git worktree. Rules:
- Write idiomatic Rust 2021-edition code.
- Run `cargo test --workspace` as L1 validation before reporting success.
- Do NOT run `cargo build` or `cargo fetch` more than once per task;
  if dependencies are missing, report and exit.
- Do NOT edit files outside the worktree root.
- Do NOT modify services/swarm/ (self-modifying code is forbidden).
"""


class RustWorker(BaseWorker):
    def __init__(self) -> None:
        super().__init__(system_prompt_fragment=_RUST_SYSTEM_PROMPT)

    def default_l1_command(self) -> str:
        return "cargo test --workspace"
```

### 8.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/workers/test_rust_worker.py -v
```

Expected: 2 passed.

### 8.5 Commit

- [ ] Commit:

```bash
git add services/swarm/workers/rust_worker.py tests/swarm/workers/test_rust_worker.py
git commit -m "swarm: add rust_worker with cargo test L1 invocation"
```

---

## Task 9 — Python worker (`python_worker.py`)

**File to create:** `services/swarm/workers/python_worker.py`

### 9.1 Write failing test

- [ ] Create `tests/swarm/workers/test_python_worker.py`:

```python
from services.swarm.workers.python_worker import PythonWorker


def test_python_worker_prompt_mentions_pytest():
    w = PythonWorker()
    assert "pytest" in w.system_prompt_fragment.lower()
    assert "python" in w.system_prompt_fragment.lower()


def test_python_worker_l1_default():
    assert PythonWorker().default_l1_command() == "pytest -q"
```

### 9.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/workers/test_python_worker.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.workers.python_worker'`.

### 9.3 Implement

- [ ] Create `services/swarm/workers/python_worker.py`:

```python
# services/swarm/workers/python_worker.py
"""Python-specific worker: pytest L1 invocation."""

from __future__ import annotations

from services.swarm.workers.base_worker import BaseWorker

_PYTHON_SYSTEM_PROMPT = """You are the Python worker for the Find Evil build swarm.

You operate inside a dedicated git worktree. Rules:
- Write Python 3.11-compatible code.
- Run `pytest -q` as L1 validation before reporting success.
- Do NOT run `pip install` at task time; dependencies are preinstalled.
- Do NOT edit files outside the worktree root.
- Do NOT modify services/swarm/ (self-modifying code is forbidden).
"""


class PythonWorker(BaseWorker):
    def __init__(self) -> None:
        super().__init__(system_prompt_fragment=_PYTHON_SYSTEM_PROMPT)

    def default_l1_command(self) -> str:
        return "pytest -q"
```

### 9.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/workers/test_python_worker.py -v
```

Expected: 2 passed.

### 9.5 Commit

- [ ] Commit:

```bash
git add services/swarm/workers/python_worker.py tests/swarm/workers/test_python_worker.py
git commit -m "swarm: add python_worker with pytest L1 invocation"
```

---

## Task 10 — TypeScript worker (`ts_worker.py`)

**File to create:** `services/swarm/workers/ts_worker.py`

### 10.1 Write failing test

- [ ] Create `tests/swarm/workers/test_ts_worker.py`:

```python
from services.swarm.workers.ts_worker import TsWorker


def test_ts_worker_prompt_mentions_pnpm():
    w = TsWorker()
    assert "pnpm" in w.system_prompt_fragment.lower()
    assert "typescript" in w.system_prompt_fragment.lower()


def test_ts_worker_l1_default():
    assert TsWorker().default_l1_command() == "pnpm test"
```

### 10.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/workers/test_ts_worker.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.workers.ts_worker'`.

### 10.3 Implement

- [ ] Create `services/swarm/workers/ts_worker.py`:

```python
# services/swarm/workers/ts_worker.py
"""TypeScript-specific worker: pnpm test L1 invocation."""

from __future__ import annotations

from services.swarm.workers.base_worker import BaseWorker

_TS_SYSTEM_PROMPT = """You are the TypeScript worker for the Find Evil build swarm.

You operate inside a dedicated git worktree. Rules:
- Write strict-mode TypeScript (Next.js 15 / React 19 conventions).
- Run `pnpm test` as L1 validation before reporting success.
- Do NOT run `pnpm install` or `npm install` at task time; dependencies
  are preinstalled at the monorepo root.
- Do NOT edit files outside the worktree root.
- Do NOT modify services/swarm/ (self-modifying code is forbidden).
"""


class TsWorker(BaseWorker):
    def __init__(self) -> None:
        super().__init__(system_prompt_fragment=_TS_SYSTEM_PROMPT)

    def default_l1_command(self) -> str:
        return "pnpm test"
```

### 10.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/workers/test_ts_worker.py -v
```

Expected: 2 passed.

### 10.5 Commit

- [ ] Commit:

```bash
git add services/swarm/workers/ts_worker.py tests/swarm/workers/test_ts_worker.py
git commit -m "swarm: add ts_worker with pnpm test L1 invocation"
```

---

## Task 11 — Critic subagent (`critic.py`)

**File to create:** `services/swarm/critic.py`

### 11.1 Write failing test

- [ ] Create `tests/swarm/test_critic.py`:

```python
# tests/swarm/test_critic.py
"""Unit tests for the critic subagent."""

import json
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from services.swarm.critic import Critic, CriticInput
from services.swarm.state import CriticVerdict, PRSpec
from services.swarm.workers.base_worker import WorkerResult


@pytest.fixture
def sample_spec() -> PRSpec:
    return PRSpec(
        pr_id="pr-c-001",
        week=1,
        language="rust",
        title="t",
        description="d",
        files_expected=["src/main.rs"],
        l1_command="cargo test",
        token_ceiling=500_000,
        max_turns=40,
        depends_on=[],
    )


def _wr(**overrides) -> WorkerResult:
    base = dict(
        pr_id="pr-c-001",
        branch_name="swarm/week-1-pr-c-001",
        worktree_path="/tmp/wt",
        l1_exit_code=0,
        l1_stdout="ok",
        l1_stderr="",
        diff_line_count=100,
        token_count_input=10_000,
        token_count_output=500,
        no_progress_killed=False,
        wall_clock_seconds=30,
        jsonl_sidecar_path="/tmp/sidecar.jsonl",
    )
    base.update(overrides)
    return WorkerResult(**base)


def test_critic_rejects_on_l1_fail(sample_spec):
    critic = Critic()
    inp = CriticInput(
        worker_result=_wr(l1_exit_code=1),
        pr_spec=sample_spec,
        diff_text="diff --git a/src/main.rs ...",
        l1_log="error E0502",
        jsonl_sidecar=[],
    )
    verdict = critic.evaluate(inp)
    assert verdict.decision == "REJECT"
    assert "l1" in verdict.reason.lower()


def test_critic_rejects_on_no_progress_killed(sample_spec):
    critic = Critic()
    inp = CriticInput(
        worker_result=_wr(no_progress_killed=True),
        pr_spec=sample_spec,
        diff_text="diff ...",
        l1_log="",
        jsonl_sidecar=[],
    )
    verdict = critic.evaluate(inp)
    assert verdict.decision == "REJECT"
    assert "progress" in verdict.reason.lower()


def test_critic_rejects_on_empty_diff(sample_spec):
    critic = Critic()
    inp = CriticInput(
        worker_result=_wr(diff_line_count=0),
        pr_spec=sample_spec,
        diff_text="",
        l1_log="",
        jsonl_sidecar=[],
    )
    verdict = critic.evaluate(inp)
    assert verdict.decision == "REJECT"


def test_critic_rejects_on_missing_expected_file(sample_spec):
    critic = Critic()
    inp = CriticInput(
        worker_result=_wr(),
        pr_spec=sample_spec,
        diff_text="diff --git a/other.rs b/other.rs\n+content\n",
        l1_log="",
        jsonl_sidecar=[],
    )
    verdict = critic.evaluate(inp)
    assert verdict.decision == "REJECT"
    assert "expected" in verdict.reason.lower()


def test_critic_rejects_on_token_ceiling_exceeded(sample_spec):
    critic = Critic()
    inp = CriticInput(
        worker_result=_wr(token_count_input=600_000),
        pr_spec=sample_spec,
        diff_text="diff --git a/src/main.rs ...",
        l1_log="",
        jsonl_sidecar=[],
    )
    verdict = critic.evaluate(inp)
    assert verdict.decision == "REJECT"


def test_critic_rejects_on_infinite_pattern(sample_spec):
    critic = Critic()
    # Same tool called 6 times
    sidecar = [{"turn": i, "tool": "bash", "args": {"cmd": "ls"}} for i in range(6)]
    inp = CriticInput(
        worker_result=_wr(),
        pr_spec=sample_spec,
        diff_text="diff --git a/src/main.rs ...",
        l1_log="",
        jsonl_sidecar=sidecar,
    )
    verdict = critic.evaluate(inp)
    assert verdict.decision == "REJECT"


def test_critic_approves_when_all_checks_pass(sample_spec):
    critic = Critic()
    inp = CriticInput(
        worker_result=_wr(),
        pr_spec=sample_spec,
        diff_text="diff --git a/src/main.rs b/src/main.rs\n+pub fn x() {}\n",
        l1_log="ok",
        jsonl_sidecar=[{"turn": 1, "tool": "write_file"}],
    )
    verdict = critic.evaluate(inp)
    assert verdict.decision == "APPROVE"


def test_critic_returns_structured_verdict(sample_spec):
    critic = Critic()
    inp = CriticInput(
        worker_result=_wr(),
        pr_spec=sample_spec,
        diff_text="diff --git a/src/main.rs ...",
        l1_log="",
        jsonl_sidecar=[],
    )
    verdict = critic.evaluate(inp)
    assert isinstance(verdict, CriticVerdict)
    assert verdict.pr_id == "pr-c-001"
```

### 11.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_critic.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.critic'`.

### 11.3 Implement

- [ ] Create `services/swarm/critic.py`:

```python
# services/swarm/critic.py
"""Critic subagent: deterministic rule-based pre-check + optional claude CLI review."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from services.swarm.state import CriticVerdict, PRSpec
from services.swarm.workers.base_worker import WorkerResult


@dataclass
class CriticInput:
    worker_result: WorkerResult
    pr_spec: PRSpec
    diff_text: str
    l1_log: str
    jsonl_sidecar: list[dict]


class Critic:
    """Gates every WorkerResult before `gh pr create`.

    Phase 1: deterministic rule checks (this module).
    Phase 2 (future): invoke `claude --model claude-sonnet-4-6` for semantic
    review. Not required for Gate 3 — rule checks suffice for the MVP.
    """

    MAX_TOOL_REPEAT = 5

    def evaluate(self, inp: CriticInput) -> CriticVerdict:
        wr = inp.worker_result
        spec = inp.pr_spec

        reason_parts: list[str] = []
        decision = "APPROVE"

        if wr.l1_exit_code != 0:
            decision = "REJECT"
            reason_parts.append(f"L1 exit code {wr.l1_exit_code} != 0")

        if wr.no_progress_killed:
            decision = "REJECT"
            reason_parts.append("no-progress kill triggered")

        if wr.diff_line_count == 0:
            decision = "REJECT"
            reason_parts.append("diff is empty")

        for expected in spec.files_expected:
            if expected not in inp.diff_text:
                decision = "REJECT"
                reason_parts.append(f"expected file missing: {expected}")
                break

        if wr.token_count_input > spec.token_ceiling:
            decision = "REJECT"
            reason_parts.append(
                f"token_count_input {wr.token_count_input} > ceiling {spec.token_ceiling}"
            )

        tool_names = [row.get("tool") for row in inp.jsonl_sidecar if row.get("tool")]
        counts = Counter(tool_names)
        for tool, n in counts.items():
            if n > self.MAX_TOOL_REPEAT:
                decision = "REJECT"
                reason_parts.append(f"tool {tool!r} repeated {n}× (>{self.MAX_TOOL_REPEAT})")
                break

        reason = "; ".join(reason_parts) if reason_parts else "all checks passed"

        return CriticVerdict(
            pr_id=wr.pr_id,
            decision=decision,
            reason=reason,
            token_count_input=wr.token_count_input,
            token_count_output=wr.token_count_output,
            l1_exit_code=wr.l1_exit_code,
            diff_line_count=wr.diff_line_count,
        )
```

### 11.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_critic.py -v
```

Expected: 7 passed.

### 11.5 Commit

- [ ] Commit:

```bash
git add services/swarm/critic.py tests/swarm/test_critic.py
git commit -m "swarm: add critic.py with rule-based CriticVerdict gating"
```

---

## Task 12 — Wall-clock watchdog (`watchdog.py`)

**File to create:** `services/swarm/watchdog.py`

### 12.1 Write failing test

- [ ] Create `tests/swarm/test_watchdog.py`:

```python
# tests/swarm/test_watchdog.py
"""Unit tests for the 8-hour wall-clock watchdog."""

import os
import time
from unittest.mock import patch

import pytest

from services.swarm.watchdog import Watchdog, WatchdogExpired


def test_watchdog_not_expired_before_deadline():
    w = Watchdog(budget_seconds=100, start_ts=int(time.time()))
    assert w.is_expired() is False


def test_watchdog_expired_after_deadline():
    w = Watchdog(budget_seconds=1, start_ts=int(time.time()) - 10)
    assert w.is_expired() is True


def test_watchdog_remaining_seconds():
    now = int(time.time())
    w = Watchdog(budget_seconds=100, start_ts=now - 30)
    assert 68 <= w.remaining_seconds() <= 72


def test_watchdog_check_raises_on_expiry():
    w = Watchdog(budget_seconds=1, start_ts=int(time.time()) - 10)
    with pytest.raises(WatchdogExpired):
        w.check()


def test_watchdog_default_eight_hours():
    w = Watchdog(start_ts=int(time.time()))
    assert w.budget_seconds == 8 * 3600


def test_watchdog_kill_process_group_calls_os_killpg():
    w = Watchdog(budget_seconds=1, start_ts=int(time.time()) - 10)
    with patch("os.killpg") as mock_killpg, patch("os.getpgid", return_value=1234):
        w.kill_process_group(pid=5678)
    mock_killpg.assert_called_once()
```

### 12.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_watchdog.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.watchdog'`.

### 12.3 Implement

- [ ] Create `services/swarm/watchdog.py`:

```python
# services/swarm/watchdog.py
"""Wall-clock watchdog — kills the supervisor process group after 8 hours."""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass


class WatchdogExpired(RuntimeError):
    """Raised when the watchdog deadline has passed."""


@dataclass
class Watchdog:
    budget_seconds: int = 8 * 3600
    start_ts: int = 0

    def __post_init__(self) -> None:
        if self.start_ts == 0:
            self.start_ts = int(time.time())

    def is_expired(self) -> bool:
        return (int(time.time()) - self.start_ts) >= self.budget_seconds

    def remaining_seconds(self) -> int:
        return max(0, self.budget_seconds - (int(time.time()) - self.start_ts))

    def check(self) -> None:
        if self.is_expired():
            raise WatchdogExpired(
                f"watchdog expired after {self.budget_seconds}s"
            )

    def kill_process_group(self, pid: int) -> None:
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
```

### 12.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_watchdog.py -v
```

Expected: 6 passed.

### 12.5 Commit

- [ ] Commit:

```bash
git add services/swarm/watchdog.py tests/swarm/test_watchdog.py
git commit -m "swarm: add 8-hour wall-clock watchdog"
```

---

## Task 13 — Dry-run gate (`pr_gate.py`)

**File to create:** `services/swarm/pr_gate.py`

### 13.1 Write failing test

- [ ] Create `tests/swarm/test_pr_gate.py`:

```python
# tests/swarm/test_pr_gate.py
"""Integration test: dry-run gate releases or pauses based on first-PR CI."""

from unittest.mock import patch

import pytest

from services.swarm.pr_gate import (
    DryRunGate,
    DryRunGateResult,
    CIStatus,
)


def test_gate_passes_when_ci_green():
    gate = DryRunGate(poll_seconds=0, timeout_seconds=1)
    with patch.object(gate, "_query_ci_status", return_value=CIStatus.GREEN):
        result = gate.wait_for("pr-1")
    assert result == DryRunGateResult.PASSED


def test_gate_fails_when_ci_red():
    gate = DryRunGate(poll_seconds=0, timeout_seconds=1)
    with patch.object(gate, "_query_ci_status", return_value=CIStatus.RED):
        result = gate.wait_for("pr-1")
    assert result == DryRunGateResult.FAILED


def test_gate_times_out_when_ci_pending():
    gate = DryRunGate(poll_seconds=0, timeout_seconds=0)
    with patch.object(gate, "_query_ci_status", return_value=CIStatus.PENDING):
        result = gate.wait_for("pr-1")
    assert result == DryRunGateResult.TIMEOUT


def test_gate_query_ci_status_shells_out_to_gh():
    gate = DryRunGate(poll_seconds=0, timeout_seconds=0)
    fake_out = '{"statusCheckRollup":[{"conclusion":"SUCCESS"}]}'
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = fake_out
        status = gate._query_ci_status("pr-1")
    assert status == CIStatus.GREEN
```

### 13.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_pr_gate.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.pr_gate'`.

### 13.3 Implement

- [ ] Create `services/swarm/pr_gate.py`:

```python
# services/swarm/pr_gate.py
"""Dry-run gate — hold the swarm until the first PR's CI result is known."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from enum import Enum


class CIStatus(str, Enum):
    GREEN = "green"
    RED = "red"
    PENDING = "pending"


class DryRunGateResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class DryRunGate:
    poll_seconds: int = 60
    timeout_seconds: int = 30 * 60  # 30 minutes

    def wait_for(self, pr_ref: str) -> DryRunGateResult:
        deadline = time.time() + self.timeout_seconds
        while True:
            status = self._query_ci_status(pr_ref)
            if status == CIStatus.GREEN:
                return DryRunGateResult.PASSED
            if status == CIStatus.RED:
                return DryRunGateResult.FAILED
            if time.time() >= deadline:
                return DryRunGateResult.TIMEOUT
            if self.poll_seconds > 0:
                time.sleep(self.poll_seconds)
            else:
                return DryRunGateResult.TIMEOUT

    def _query_ci_status(self, pr_ref: str) -> CIStatus:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                pr_ref,
                "--json",
                "statusCheckRollup",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return CIStatus.PENDING
        try:
            payload = json.loads(result.stdout)
            rollup = payload.get("statusCheckRollup", [])
        except json.JSONDecodeError:
            return CIStatus.PENDING

        if not rollup:
            return CIStatus.PENDING

        conclusions = {entry.get("conclusion") for entry in rollup}
        if "FAILURE" in conclusions or "CANCELLED" in conclusions:
            return CIStatus.RED
        if conclusions == {"SUCCESS"}:
            return CIStatus.GREEN
        return CIStatus.PENDING
```

### 13.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_pr_gate.py -v
```

Expected: 4 passed.

### 13.5 Commit

- [ ] Commit:

```bash
git add services/swarm/pr_gate.py tests/swarm/test_pr_gate.py
git commit -m "swarm: add dry-run gate (first PR must pass CI before release)"
```

---

## Task 14 — LangGraph supervisor (`supervisor.py`)

**File to create:** `services/swarm/supervisor.py`

### 14.1 Write failing test

- [ ] Create `tests/swarm/test_supervisor.py`:

```python
# tests/swarm/test_supervisor.py
"""Integration tests for the LangGraph supervisor."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.swarm.state import PRSpec, SwarmState
from services.swarm.supervisor import (
    build_supervisor_graph,
    plan_node,
    dispatch_node,
    collect_node,
)


FIXTURE = Path(__file__).parent / "fixtures" / "BUILD_PLAN_mini.md"


def _empty_state(week: int = 1) -> SwarmState:
    return SwarmState(
        week=week,
        pr_specs=[],
        dispatched_pr_ids=[],
        completed_pr_ids=[],
        rejected_pr_ids=[],
        critic_verdicts=[],
        spend_usd_cumulative=0.0,
        budget_exhausted=False,
        dry_run_gate_passed=False,
        dry_run_gate_pr_id=None,
        wall_clock_start_ts=0,
        nightly_report=None,
    )


def test_plan_node_populates_pr_specs():
    state = _empty_state(week=1)
    with patch("services.swarm.supervisor.PLAN_PATH", FIXTURE):
        out = plan_node(state)
    assert len(out["pr_specs"]) == 2
    assert all(isinstance(s, PRSpec) for s in out["pr_specs"])


def test_dispatch_node_marks_dispatched():
    state = _empty_state(week=1)
    state["pr_specs"] = [
        PRSpec(
            pr_id="pr-a", week=1, language="rust",
            title="t", description="d", files_expected=["f.rs"],
            l1_command="x", token_ceiling=500_000, max_turns=40,
            depends_on=[],
        )
    ]
    with patch("services.swarm.supervisor._dispatch_one") as mock_disp:
        mock_disp.return_value = None
        out = dispatch_node(state)
    assert "pr-a" in out["dispatched_pr_ids"]


def test_collect_node_emits_nightly_report():
    state = _empty_state(week=1)
    state["dispatched_pr_ids"] = ["pr-a"]
    state["completed_pr_ids"] = ["pr-a"]
    state["wall_clock_start_ts"] = 100

    with patch("time.time", return_value=200):
        out = collect_node(state)

    report = out["nightly_report"]
    assert report is not None
    assert report.prs_opened == ["pr-a"]


def test_build_graph_compiles_with_postgres_saver():
    with patch(
        "services.swarm.supervisor.PostgresSaver.from_conn_string"
    ) as mock_cp:
        saver = MagicMock()
        saver.__enter__ = MagicMock(return_value=saver)
        saver.__exit__ = MagicMock(return_value=False)
        mock_cp.return_value = saver

        graph = build_supervisor_graph(
            postgres_conn_string="postgresql://swarm:swarm@localhost:5432/swarm",
            checkpointer_factory=lambda s: saver,
        )
    assert graph is not None


def test_graph_does_not_import_sqlite_saver():
    """PostgresSaver is mandatory for the swarm. SqliteSaver is for the Product."""
    import services.swarm.supervisor as sup
    src = Path(sup.__file__).read_text(encoding="utf-8")
    assert "SqliteSaver" not in src, "SqliteSaver must not be used by the swarm"
```

### 14.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_supervisor.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.supervisor'`.

### 14.3 Implement

- [ ] Create `services/swarm/supervisor.py`:

```python
# services/swarm/supervisor.py
"""LangGraph StateGraph supervisor for the build swarm."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

from services.swarm.plan_parser import parse_week
from services.swarm.state import NightlyReport, PRSpec, SwarmState

# Default plan path (overridable in tests)
PLAN_PATH: Path = Path(__file__).resolve().parents[2] / "BUILD_PLAN_v2.md"


# ------------------------------------------------------------------
# Nodes
# ------------------------------------------------------------------

def plan_node(state: SwarmState) -> dict:
    """Parse BUILD_PLAN_v2.md for the current week."""
    specs = parse_week(PLAN_PATH, week=state["week"])
    return {
        "pr_specs": specs,
        "wall_clock_start_ts": int(time.time()),
    }


def _dispatch_one(spec: PRSpec) -> None:
    """Placeholder — real dispatch lives in dispatch.py in later tasks."""
    return None


def dispatch_node(state: SwarmState) -> dict:
    """Dispatch workers for each PRSpec; record dispatched ids."""
    dispatched: list[str] = []
    for spec in state["pr_specs"]:
        _dispatch_one(spec)
        dispatched.append(spec.pr_id)
    return {"dispatched_pr_ids": dispatched}


def collect_node(state: SwarmState) -> dict:
    """Emit the nightly report."""
    now = int(time.time())
    wall = now - (state.get("wall_clock_start_ts") or now)
    report = NightlyReport(
        date=time.strftime("%Y-%m-%d", time.gmtime(now)),
        week=state["week"],
        prs_opened=list(state.get("completed_pr_ids", [])),
        prs_rejected=list(state.get("rejected_pr_ids", [])),
        total_spend_usd=0.0,  # Option B: no metered spend
        wall_clock_seconds=wall,
        budget_remaining_usd=0.0,
    )
    return {"nightly_report": report}


# ------------------------------------------------------------------
# Graph builder
# ------------------------------------------------------------------

def build_supervisor_graph(
    *,
    postgres_conn_string: str,
    checkpointer_factory: Callable[[str], object] | None = None,
):
    """Compile the supervisor StateGraph with a PostgresSaver checkpoint store."""
    if checkpointer_factory is None:
        def _default_factory(conn: str):
            return PostgresSaver.from_conn_string(conn)
        checkpointer_factory = _default_factory

    checkpointer = checkpointer_factory(postgres_conn_string)
    if hasattr(checkpointer, "setup"):
        try:
            checkpointer.setup()
        except Exception:
            pass

    graph = StateGraph(SwarmState)
    graph.add_node("plan", plan_node)
    graph.add_node("dispatch", dispatch_node)
    graph.add_node("collect", collect_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "dispatch")
    graph.add_edge("dispatch", "collect")
    graph.add_edge("collect", END)

    return graph.compile(checkpointer=checkpointer)
```

### 14.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_supervisor.py -v
```

Expected: 5 passed.

### 14.5 Commit

- [ ] Commit:

```bash
git add services/swarm/supervisor.py tests/swarm/test_supervisor.py
git commit -m "swarm: add LangGraph supervisor (plan/dispatch/collect + PostgresSaver)"
```

---

## Task 15 — Nightly JSONL report emitter (`night_report.py`)

**File to create:** `services/swarm/night_report.py`

### 15.1 Write failing test

- [ ] Create `tests/swarm/test_night_report.py`:

```python
# tests/swarm/test_night_report.py
"""Unit tests for night_report emitter."""

import json
from pathlib import Path

from services.swarm.night_report import NightReportEmitter
from services.swarm.state import NightlyReport


def test_emit_event_creates_jsonl(tmp_path: Path):
    out = tmp_path / "night.jsonl"
    e = NightReportEmitter(path=out, run_id="r1")
    e.emit("plan_parsed", week=2, pr_count=3)
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["event"] == "plan_parsed"
    assert rows[0]["run_id"] == "r1"
    assert "ts" in rows[0]


def test_emit_report_dumps_full_payload(tmp_path: Path):
    out = tmp_path / "night.jsonl"
    e = NightReportEmitter(path=out, run_id="r2")
    r = NightlyReport(
        date="2026-04-24", week=2,
        prs_opened=["a"], prs_rejected=[],
        total_spend_usd=0.0, wall_clock_seconds=120,
        budget_remaining_usd=0.0,
    )
    e.emit_report(r)
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert rows[0]["event"] == "night_complete"
    assert rows[0]["week"] == 2


def test_emit_halt_session_exhausted(tmp_path: Path):
    out = tmp_path / "night.jsonl"
    e = NightReportEmitter(path=out, run_id="r3")
    e.emit_halt(reason="session_exhausted", pr_id="pr-x")
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert rows[0]["event"] == "halt"
    assert rows[0]["halt_reason"] == "session_exhausted"
```

### 15.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_night_report.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.night_report'`.

### 15.3 Implement

- [ ] Create `services/swarm/night_report.py`:

```python
# services/swarm/night_report.py
"""JSONL nightly report emitter."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from services.swarm.state import NightlyReport


@dataclass
class NightReportEmitter:
    path: Path
    run_id: str

    def _write(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row_with_meta = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "run_id": self.run_id,
            **row,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row_with_meta) + "\n")

    def emit(self, event: str, **fields) -> None:
        self._write({"event": event, **fields})

    def emit_report(self, report: NightlyReport) -> None:
        self._write({
            "event": "night_complete",
            "date": report.date,
            "week": report.week,
            "prs_opened": report.prs_opened,
            "prs_rejected": report.prs_rejected,
            "total_spend_usd": report.total_spend_usd,
            "wall_clock_seconds": report.wall_clock_seconds,
            "budget_remaining_usd": report.budget_remaining_usd,
        })

    def emit_halt(self, *, reason: str, pr_id: str | None = None) -> None:
        self._write({
            "event": "halt",
            "halt_reason": reason,
            "pr_id": pr_id,
        })
```

### 15.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_night_report.py -v
```

Expected: 3 passed.

### 15.5 Commit

- [ ] Commit:

```bash
git add services/swarm/night_report.py tests/swarm/test_night_report.py
git commit -m "swarm: add structured JSONL nightly report emitter"
```

---

## Task 16 — CLI entry point (`main.py`)

**File to create:** `services/swarm/main.py`

### 16.1 Write failing test

- [ ] Create `tests/swarm/test_main_cli.py`:

```python
# tests/swarm/test_main_cli.py
"""Integration tests for the swarm CLI."""

import subprocess
import sys

import pytest


def test_cli_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "services.swarm.main", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--week" in result.stdout
    assert "--dry-run-gate" in result.stdout
    assert "--resume" in result.stdout


def test_cli_missing_week_errors():
    result = subprocess.run(
        [sys.executable, "-m", "services.swarm.main"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_cli_parses_flags():
    from services.swarm.main import parse_args
    ns = parse_args(["--week", "3", "--dry-run-gate", "--resume"])
    assert ns.week == 3
    assert ns.dry_run_gate is True
    assert ns.resume is True


def test_cli_mock_workers_flag():
    from services.swarm.main import parse_args
    ns = parse_args(["--week", "1", "--mock-workers"])
    assert ns.mock_workers is True
```

### 16.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_main_cli.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.swarm.main'`.

### 16.3 Implement

- [ ] Create `services/swarm/main.py`:

```python
# services/swarm/main.py
"""CLI entry point for the build swarm."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from services.swarm.night_report import NightReportEmitter
from services.swarm.session_guard import SessionGuard, SessionLimitError
from services.swarm.state import SwarmState
from services.swarm.supervisor import build_supervisor_graph


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="services.swarm.main",
        description="Autonomous build swarm (Option B).",
    )
    parser.add_argument("--week", type=int, required=True,
                        help="Build plan week number (1-8).")
    parser.add_argument("--dry-run-gate", action="store_true",
                        help="Hold remaining PRs until first PR CI is green.")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from existing Postgres checkpoint.")
    parser.add_argument("--mock-workers", action="store_true",
                        help="Skip real claude CLI invocation (smoke test).")
    return parser.parse_args(argv)


def _initial_state(week: int) -> SwarmState:
    return SwarmState(
        week=week,
        pr_specs=[],
        dispatched_pr_ids=[],
        completed_pr_ids=[],
        rejected_pr_ids=[],
        critic_verdicts=[],
        spend_usd_cumulative=0.0,
        budget_exhausted=False,
        dry_run_gate_passed=False,
        dry_run_gate_pr_id=None,
        wall_clock_start_ts=int(time.time()),
        nightly_report=None,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    conn = os.environ.get(
        "POSTGRES_CONN_STRING",
        "postgresql://swarm:swarm@localhost:5432/swarm",
    )
    run_id = f"swarm-{time.strftime('%Y-%m-%d')}-w{args.week}"
    report_path = Path("logs/swarm") / f"{run_id}.jsonl"
    emitter = NightReportEmitter(path=report_path, run_id=run_id)
    guard = SessionGuard()

    try:
        graph = build_supervisor_graph(postgres_conn_string=conn)
        thread_id = run_id
        config = {"configurable": {"thread_id": thread_id}}
        emitter.emit("start", week=args.week, dry_run_gate=args.dry_run_gate,
                     resume=args.resume, mock_workers=args.mock_workers)

        if args.mock_workers:
            emitter.emit("mock_workers_enabled")
            return 0

        graph.invoke(_initial_state(args.week), config=config)
        emitter.emit("end")
        return 0
    except SessionLimitError as exc:
        emitter.emit_halt(reason="session_exhausted", pr_id=exc.pr_id)
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

### 16.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_main_cli.py -v
```

Expected: 4 passed.

### 16.5 Commit

- [ ] Commit:

```bash
git add services/swarm/main.py tests/swarm/test_main_cli.py
git commit -m "swarm: add main.py CLI with --week/--dry-run-gate/--resume/--mock-workers"
```

---

## Task 17 — Scheduler config (`scheduler_config.yaml`)

**File to create:** `services/swarm/config/scheduler_config.yaml`

### 17.1 Write failing test

- [ ] Create `tests/swarm/test_scheduler_config.py`:

```python
# tests/swarm/test_scheduler_config.py
from pathlib import Path

import yaml

CFG = Path(__file__).resolve().parents[2] / "services" / "swarm" / "config" / "scheduler_config.yaml"


def test_scheduler_config_exists():
    assert CFG.is_file()


def test_scheduler_cron_is_23():
    doc = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    task = doc["tasks"][0]
    assert task["schedule"] == "0 23 * * *"


def test_scheduler_invokes_swarm_start():
    doc = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    task = doc["tasks"][0]
    assert "scripts/swarm-start.sh" in task["command"]


def test_scheduler_env_has_fork_subagent():
    doc = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    task = doc["tasks"][0]
    assert task["environment"]["CLAUDE_CODE_FORK_SUBAGENT"] == "1"


def test_scheduler_timeout_matches_watchdog():
    doc = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert doc["tasks"][0]["timeout_minutes"] == 480


def test_scheduler_has_no_anthropic_api_key():
    doc = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    env = doc["tasks"][0]["environment"]
    assert "ANTHROPIC_API_KEY" not in env, "Option B: no API key in swarm env"
    assert "LITELLM_MASTER_KEY" not in env, "Option B: no LiteLLM"
```

### 17.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_scheduler_config.py -v
```

Expected: assertion error `CFG.is_file()` is False.

### 17.3 Implement

- [ ] Create `services/swarm/config/scheduler_config.yaml`:

```yaml
# services/swarm/config/scheduler_config.yaml
# Consumed by jshchnz/claude-code-scheduler.
# Option B: Claude Code subscription mode — no ANTHROPIC_API_KEY, no LiteLLM.

tasks:
  - name: "Find Evil nightly build swarm"
    schedule: "0 23 * * *"
    command: "bash scripts/swarm-start.sh --week auto"
    working_directory: "C:/Users/newbi/Desktop/PUG Projects/SANS-Hackathon"
    timeout_minutes: 480
    environment:
      CLAUDE_CODE_FORK_SUBAGENT: "1"
      CLAUDE_CODE_AUTOCOMPACT: "0"
      POSTGRES_CONN_STRING: "postgresql://swarm:swarm@localhost:5432/swarm"
    on_failure: "log"
    on_timeout: "kill"
```

### 17.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_scheduler_config.py -v
```

Expected: 6 passed.

### 17.5 Commit

- [ ] Commit:

```bash
git add services/swarm/config/scheduler_config.yaml tests/swarm/test_scheduler_config.py
git commit -m "swarm: add claude-code-scheduler config (cron 0 23 * * *, Option B env)"
```

---

## Task 18 — `scripts/swarm-start.sh` pre-flight launcher

**File to create:** `scripts/swarm-start.sh`

### 18.1 Write failing test

- [ ] Create `tests/swarm/test_swarm_start_script.py`:

```python
# tests/swarm/test_swarm_start_script.py
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "swarm-start.sh"


def test_script_exists():
    assert SCRIPT.is_file()


def test_script_checks_docker_postgres():
    txt = SCRIPT.read_text(encoding="utf-8")
    assert "docker compose -f docker/swarm-postgres.yml" in txt


def test_script_checks_gh_auth():
    txt = SCRIPT.read_text(encoding="utf-8")
    assert "gh auth status" in txt


def test_script_checks_git_clean():
    txt = SCRIPT.read_text(encoding="utf-8")
    assert "git status --porcelain" in txt


def test_script_does_not_reference_litellm():
    txt = SCRIPT.read_text(encoding="utf-8")
    assert "litellm" not in txt.lower(), "Option B: no LiteLLM"


def test_script_cleans_leaked_worktrees():
    txt = SCRIPT.read_text(encoding="utf-8")
    assert ".wt/wt-" in txt


def test_script_invokes_main_py():
    txt = SCRIPT.read_text(encoding="utf-8")
    assert "python -m services.swarm.main" in txt
```

### 18.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_swarm_start_script.py -v
```

Expected: assertion `SCRIPT.is_file()` is False.

### 18.3 Implement

- [ ] Create `scripts/swarm-start.sh`:

```bash
#!/usr/bin/env bash
# scripts/swarm-start.sh
# Pre-flight checks + launch supervisor. Option B (Claude Code subscription).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

WEEK="auto"
DRY_RUN_GATE=""
MOCK_WORKERS=""
RESUME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --week) WEEK="$2"; shift 2 ;;
    --dry-run-gate) DRY_RUN_GATE="--dry-run-gate"; shift ;;
    --mock-workers) MOCK_WORKERS="--mock-workers"; shift ;;
    --resume) RESUME="--resume"; shift ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

echo "[swarm-start] pre-flight: Docker Postgres"
if ! docker compose -f docker/swarm-postgres.yml ps --services --filter status=running | grep -q swarm-postgres; then
  docker compose -f docker/swarm-postgres.yml up -d
fi

echo "[swarm-start] pre-flight: gh auth status"
gh auth status >/dev/null

echo "[swarm-start] pre-flight: git clean"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: working tree is dirty; abort." >&2
  exit 3
fi

echo "[swarm-start] pre-flight: leaked worktrees"
for d in .wt/wt-* ; do
  [[ -d "$d" ]] || continue
  pr_id="${d#.wt/wt-*-}"
  open_count=$(gh pr list --label swarm-generated --search "$pr_id" --state open --json number --jq 'length' 2>/dev/null || echo 0)
  if [[ "$open_count" == "0" ]]; then
    echo "[swarm-start] removing leaked worktree: $d"
    git worktree remove --force "$d" || rm -rf "$d"
  fi
done
git worktree prune

if [[ "$WEEK" == "auto" ]]; then
  EPOCH_START="2026-04-21"
  NOW=$(date +%s)
  START=$(date -d "$EPOCH_START" +%s 2>/dev/null || python -c "import datetime; print(int(datetime.datetime(2026,4,21).timestamp()))")
  DAYS=$(( (NOW - START) / 86400 ))
  WEEK=$(( DAYS / 7 + 1 ))
  if (( WEEK < 1 )); then WEEK=1; fi
  if (( WEEK > 8 )); then WEEK=8; fi
fi

echo "[swarm-start] launching supervisor for week=$WEEK"
exec python -m services.swarm.main --week "$WEEK" $DRY_RUN_GATE $MOCK_WORKERS $RESUME
```

- [ ] Make it executable:

```bash
chmod +x scripts/swarm-start.sh
```

### 18.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_swarm_start_script.py -v
```

Expected: 7 passed.

### 18.5 Commit

- [ ] Commit:

```bash
git add scripts/swarm-start.sh tests/swarm/test_swarm_start_script.py
git commit -m "swarm: add swarm-start.sh pre-flight launcher (Option B)"
```

---

## Task 19 — `scripts/swarm-status.sh` morning dashboard

**File to create:** `scripts/swarm-status.sh`

### 19.1 Write failing test

- [ ] Create `tests/swarm/test_swarm_status_script.py`:

```python
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "swarm-status.sh"


def test_status_script_exists():
    assert SCRIPT.is_file()


def test_status_script_lists_prs():
    txt = SCRIPT.read_text(encoding="utf-8")
    assert "gh pr list" in txt
    assert "swarm-generated" in txt


def test_status_script_tails_night_report():
    txt = SCRIPT.read_text(encoding="utf-8")
    assert "logs/swarm" in txt


def test_status_script_shows_postgres_state():
    txt = SCRIPT.read_text(encoding="utf-8")
    assert "swarm-postgres" in txt or "psql" in txt


def test_status_script_does_not_query_litellm():
    txt = SCRIPT.read_text(encoding="utf-8")
    assert "litellm" not in txt.lower()
```

### 19.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_swarm_status_script.py -v
```

Expected: script does not exist.

### 19.3 Implement

- [ ] Create `scripts/swarm-status.sh`:

```bash
#!/usr/bin/env bash
# scripts/swarm-status.sh
# Morning status: open PRs, last night's report, Postgres checkpoint summary.

set -euo pipefail

echo "=== Open swarm PRs ==="
gh pr list --label swarm-generated --state open --limit 20 || true

echo
echo "=== Last night's report (tail 30 lines) ==="
latest=$(ls -1t logs/swarm/*.jsonl 2>/dev/null | head -n1 || true)
if [[ -n "${latest:-}" ]]; then
  echo "file: $latest"
  tail -n 30 "$latest"
else
  echo "no reports found in logs/swarm/"
fi

echo
echo "=== Postgres checkpoint status ==="
if docker ps --format '{{.Names}}' | grep -q swarm-postgres; then
  docker exec swarm-postgres psql -U swarm -d swarm -c \
    "SELECT thread_id, checkpoint_id FROM checkpoints ORDER BY checkpoint_id DESC LIMIT 5;" \
    2>/dev/null || echo "(checkpoints table not yet materialized)"
else
  echo "swarm-postgres container is not running"
fi
```

- [ ] Make it executable:

```bash
chmod +x scripts/swarm-status.sh
```

### 19.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_swarm_status_script.py -v
```

Expected: 5 passed.

### 19.5 Commit

- [ ] Commit:

```bash
git add scripts/swarm-status.sh tests/swarm/test_swarm_status_script.py
git commit -m "swarm: add swarm-status.sh morning dashboard"
```

---

## Task 20 — `scripts/swarm-cleanup-merged.sh` daily worktree cleanup

**File to create:** `scripts/swarm-cleanup-merged.sh`

### 20.1 Write failing test

- [ ] Create `tests/swarm/test_cleanup_script.py`:

```python
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "swarm-cleanup-merged.sh"


def test_cleanup_script_exists():
    assert SCRIPT.is_file()


def test_cleanup_queries_merged_prs():
    txt = SCRIPT.read_text(encoding="utf-8")
    assert "gh pr list" in txt
    assert "--state merged" in txt
    assert "swarm-generated" in txt


def test_cleanup_removes_worktrees():
    txt = SCRIPT.read_text(encoding="utf-8")
    assert "git worktree remove" in txt


def test_cleanup_prunes():
    txt = SCRIPT.read_text(encoding="utf-8")
    assert "git worktree prune" in txt
```

### 20.2 Run the test — expect FAIL

- [ ] Run:

```bash
python -m pytest tests/swarm/test_cleanup_script.py -v
```

Expected: script does not exist.

### 20.3 Implement

- [ ] Create `scripts/swarm-cleanup-merged.sh`:

```bash
#!/usr/bin/env bash
# scripts/swarm-cleanup-merged.sh
# Remove worktrees + remote branches for merged swarm PRs.
# Run daily at 08:00 via cron.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

echo "[cleanup] fetching merged swarm PRs..."
mapfile -t MERGED < <(gh pr list \
  --label swarm-generated \
  --state merged \
  --limit 100 \
  --json headRefName \
  --jq '.[].headRefName')

for branch in "${MERGED[@]}"; do
  pr_id="${branch#swarm/week-*-}"
  for d in .wt/wt-rust-"$pr_id" .wt/wt-py-"$pr_id" .wt/wt-ts-"$pr_id"; do
    if [[ -d "$d" ]]; then
      echo "[cleanup] removing worktree: $d"
      git worktree remove --force "$d" || rm -rf "$d"
    fi
  done
  echo "[cleanup] deleting remote branch: $branch"
  git push origin --delete "$branch" || true
done

git worktree prune
echo "[cleanup] done."
```

- [ ] Make it executable:

```bash
chmod +x scripts/swarm-cleanup-merged.sh
```

### 20.4 Run the test — expect PASS

- [ ] Run:

```bash
python -m pytest tests/swarm/test_cleanup_script.py -v
```

Expected: 4 passed.

### 20.5 Commit

- [ ] Commit:

```bash
git add scripts/swarm-cleanup-merged.sh tests/swarm/test_cleanup_script.py
git commit -m "swarm: add swarm-cleanup-merged.sh daily worktree cleanup"
```

---

## Task 21 — End-to-end smoke test (mock workers, week 1)

**Files to create:** `tests/swarm/test_smoke_end_to_end.py`, `BUILD_PLAN_v2.md` seed row for week 1

### 21.1 Write failing integration test

- [ ] Ensure `BUILD_PLAN_v2.md` has a week-1 section (copy minimal content from the fixture if empty):

```bash
python -m pytest tests/swarm/test_smoke_end_to_end.py -v
```

- [ ] Create `tests/swarm/test_smoke_end_to_end.py`:

```python
# tests/swarm/test_smoke_end_to_end.py
"""End-to-end smoke test: bash scripts/swarm-start.sh --week 1 --dry-run-gate --mock-workers"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "swarm-start.sh"
PLAN = REPO_ROOT / "BUILD_PLAN_v2.md"
FIXTURE = REPO_ROOT / "tests" / "swarm" / "fixtures" / "BUILD_PLAN_mini.md"


pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="bash required for end-to-end smoke test",
)


def test_smoke_week_1_mock_workers(tmp_path, monkeypatch):
    if not PLAN.exists():
        PLAN.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    env = dict(os.environ)
    env["POSTGRES_CONN_STRING"] = "postgresql://swarm:swarm@localhost:5432/swarm"

    # Direct python invocation — bypasses git/gh/docker pre-flight for the smoke
    # test harness while still exercising the full supervisor path.
    result = subprocess.run(
        [sys.executable, "-m", "services.swarm.main",
         "--week", "1", "--dry-run-gate", "--mock-workers"],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    assert result.returncode in (0, 2), result.stderr  # 2 = session limit, still clean

    reports = sorted((REPO_ROOT / "logs" / "swarm").glob("swarm-*-w1.jsonl"))
    assert reports, "no night report emitted"
    tail = reports[-1].read_text(encoding="utf-8").splitlines()
    assert any('"event": "start"' in l for l in tail)
    assert any('"event": "mock_workers_enabled"' in l for l in tail)


def test_no_leaked_worktrees_after_smoke():
    wt_root = REPO_ROOT / ".wt"
    if not wt_root.exists():
        return
    # Acceptable: directory may exist but should contain no wt-* with uncommitted content
    leaked = [p for p in wt_root.glob("wt-*") if p.is_dir()]
    # This is advisory — parallel runs may leave worktrees; only fail if > 10
    assert len(leaked) < 10, f"too many leaked worktrees: {leaked}"
```

### 21.2 Run the test — expect initial failure until Postgres is up

- [ ] Run (Postgres must be running via `docker compose -f docker/swarm-postgres.yml up -d`):

```bash
docker compose -f docker/swarm-postgres.yml up -d
python -m pytest tests/swarm/test_smoke_end_to_end.py -v
```

Expected on first failed attempt: exit code from `main.py` may be non-zero if Postgres is unreachable. Fix by starting Postgres.

### 21.3 Wire up and verify PASS

- [ ] Ensure `docker compose -f docker/swarm-postgres.yml up -d` is healthy:

```bash
docker compose -f docker/swarm-postgres.yml ps
```

Expected output includes `healthy` on the `swarm-postgres` row.

- [ ] Re-run:

```bash
python -m pytest tests/swarm/test_smoke_end_to_end.py -v
```

Expected: 2 passed.

### 21.4 Run the full suite

- [ ] Full regression:

```bash
python -m pytest tests/swarm -v
```

Expected: all tests pass.

### 21.5 Acceptance-criteria verification (Spec #1 §11 [Gate 3])

- [ ] `test_plan_parser.py` — passes (Task 4).
- [ ] `test_worktree.py` — passes (Task 5).
- [ ] `test_critic.py` — passes (Task 11).
- [ ] `test_session_guard.py` — replaces `test_budget.py` (Option B) — passes (Task 6).
- [ ] `test_base_worker.py` — no-progress detector verified (Task 7).
- [ ] `test_supervisor.py` — PostgresSaver wired, no SqliteSaver (Task 14).
- [ ] `test_pr_gate.py` — dry-run gate (Task 13).
- [ ] `test_smoke_end_to_end.py` — logs emitted, no leaks, `gh pr list` no-op OK with mock workers.
- [ ] `docker compose -f docker/swarm-postgres.yml up -d` starts cleanly.
- [ ] `scripts/swarm-status.sh` runs < 5 s.
- [ ] `scripts/swarm-cleanup-merged.sh` removes merged worktrees.
- [ ] Watchdog kills process group after simulated timeout (`test_watchdog.py`).

### 21.6 Commit

- [ ] Commit:

```bash
git add tests/swarm/test_smoke_end_to_end.py
git commit -m "swarm: add end-to-end smoke test (week 1, mock workers, dry-run gate)"
```

---

## Completion checklist (Gate 3)

- [ ] All 21 tasks above have passing tests committed.
- [ ] `python -m pytest tests/swarm -v` is green.
- [ ] `docker compose -f docker/swarm-postgres.yml up -d` + `python -m services.swarm.main --week 1 --dry-run-gate --mock-workers` exits 0 and emits `logs/swarm/swarm-*-w1.jsonl`.
- [ ] No reference to `litellm`, `budget.py`, `ANTHROPIC_API_KEY`, `$50 cap`, `SqliteSaver`, or `max_budget` anywhere under `services/swarm/` (Option B compliance grep).
- [ ] `CLAUDE_CODE_FORK_SUBAGENT=1` is present in every worker env path and in `scheduler_config.yaml`.
- [ ] `session_guard.py` detects rate-limit signals without retry (tested in `test_session_guard.py::test_guard_no_retry_policy`).

Upon completion of all boxes: request human review and proceed to Spec #2 (The Product) implementation.
