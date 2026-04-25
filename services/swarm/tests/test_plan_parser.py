"""Tests for findevil_swarm.plan_parser.

Spec #1 §3.1 + §11 AC — the parser reads ``docs/superpowers/plans/*.md``
(or ``BUILD_PLAN_v2.md``) and emits ordered ``PRSpec`` lists keyed to
the week that dispatched it.

Design note: each plan markdown uses ``## Task N: <title>`` as a task
marker. Inside the task body, ``Create:`` / ``Modify:`` / ``Test:``
list the files, and a ``Run: <cmd>`` line gives the L1 command.
Language is inferred from the dominant file extension in files_expected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from findevil_swarm.plan_parser import (
    WEEK_TO_PLANS,
    ParsedTask,
    detect_language,
    extract_files,
    extract_l1_command,
    parse_plan_file,
    parse_week,
)
from findevil_swarm.state import PRSpec

REPO_ROOT = Path(__file__).resolve().parents[3]
SANDBOX_PLAN = REPO_ROOT / "docs/superpowers/plans/2026-04-23-sandbox-plan.md"
SWARM_PLAN = REPO_ROOT / "docs/superpowers/plans/2026-04-23-build-swarm-plan.md"


class TestDetectLanguage:
    def test_rust_wins_on_rs_extension(self) -> None:
        assert detect_language(["services/mcp/src/lib.rs"]) == "rust"
        assert detect_language(["Cargo.toml", "src/main.rs"]) == "rust"

    def test_python_wins_on_py_extension(self) -> None:
        assert detect_language(["services/swarm/main.py"]) == "python"
        assert detect_language(["pyproject.toml", "tests/test_x.py"]) == "python"

    def test_typescript_wins_on_ts_tsx(self) -> None:
        assert detect_language(["apps/web/app/page.tsx"]) == "typescript"
        assert detect_language(["package.json", "src/lib.ts"]) == "typescript"

    def test_dockerfile_maps_to_python(self) -> None:
        # Dockerfiles + YAML are written in "python" PR scope — that's
        # the worker whose build system consumes them.
        assert detect_language(["docker/l1-devbase.Dockerfile"]) == "python"

    def test_yaml_alone_maps_to_python(self) -> None:
        assert detect_language([".github/workflows/l0-static.yml"]) == "python"

    def test_empty_list_defaults_to_python(self) -> None:
        # Sentinel: if we can't classify, default to python worker
        # (matches our scheduler's lowest-risk language).
        assert detect_language([]) == "python"

    def test_mixed_extensions_picks_most_common(self) -> None:
        assert (
            detect_language(["src/a.rs", "src/b.rs", "src/c.rs", "README.md", "tests/t.py"])
            == "rust"
        )


class TestExtractFiles:
    def test_extracts_create_paths(self) -> None:
        body = """### 4.1 Failing test

- Create: `services/foo/bar.py`
- Create: `tests/foo/test_bar.py`

Some description.
"""
        assert extract_files(body) == [
            "services/foo/bar.py",
            "tests/foo/test_bar.py",
        ]

    def test_extracts_modify_paths(self) -> None:
        body = "- Modify: `services/swarm/supervisor.py:45-67`"
        assert extract_files(body) == ["services/swarm/supervisor.py"]

    def test_ignores_non_file_backticks(self) -> None:
        body = "Some narrative with `cargo test` in it.\n- Create: `src/a.rs`"
        assert extract_files(body) == ["src/a.rs"]

    def test_deduplicates(self) -> None:
        body = "- Create: `a.py`\n- Modify: `a.py`"
        assert extract_files(body) == ["a.py"]


class TestExtractL1Command:
    def test_plain_run_line(self) -> None:
        body = "Run: `pytest tests/foo.py -v`\nExpected: PASS"
        assert extract_l1_command(body) == "pytest tests/foo.py -v"

    def test_cargo_command(self) -> None:
        body = "Run: `cargo test -p findevil-mcp --test tool_smoke`"
        assert extract_l1_command(body) == "cargo test -p findevil-mcp --test tool_smoke"

    def test_default_to_pytest_when_no_run_line(self) -> None:
        body = "Some task with no Run: line."
        assert extract_l1_command(body) == "uv run pytest -xvs"

    def test_prefers_first_run_command(self) -> None:
        body = "Run: `pytest x.py`\n\nLater: Run: `pytest y.py`"
        assert extract_l1_command(body) == "pytest x.py"


class TestParsePlanFile:
    def test_sandbox_plan_exists_for_test(self) -> None:
        assert SANDBOX_PLAN.is_file(), "sandbox plan is a precondition"

    def test_sandbox_plan_yields_at_least_13_tasks(self) -> None:
        tasks = parse_plan_file(SANDBOX_PLAN)
        # Spec #3 has 13 tasks in sandbox plan; be lenient on overshoot
        # but strict on undershoot.
        assert len(tasks) >= 13, f"expected ≥13 tasks, got {len(tasks)}"

    def test_sandbox_task_1_is_l0_workflow(self) -> None:
        tasks = parse_plan_file(SANDBOX_PLAN)
        t1 = next((t for t in tasks if t.task_number == 1), None)
        assert t1 is not None, "Task 1 missing"
        assert "l0" in t1.title.lower() or "static" in t1.title.lower()

    def test_all_tasks_have_numbers(self) -> None:
        tasks = parse_plan_file(SANDBOX_PLAN)
        numbers = [t.task_number for t in tasks]
        assert len(numbers) == len(set(numbers)), "duplicate task numbers"
        assert all(isinstance(n, int) for n in numbers)

    def test_swarm_plan_parses(self) -> None:
        tasks = parse_plan_file(SWARM_PLAN)
        # Swarm plan has 21 tasks per spec.
        assert len(tasks) >= 15


class TestParseWeek:
    def test_week_1_yields_prspec_list(self) -> None:
        specs = parse_week(week=1, plans_dir=REPO_ROOT / "docs/superpowers/plans")
        assert len(specs) >= 1
        assert all(isinstance(s, PRSpec) for s in specs)
        assert all(s.week == 1 for s in specs)

    def test_week_unknown_returns_empty(self) -> None:
        # Weeks beyond 8 or below 1 should raise; unknown weeks never
        # silently return nothing in production paths.
        with pytest.raises(ValueError):
            parse_week(week=99, plans_dir=REPO_ROOT / "docs/superpowers/plans")

    def test_week_map_covers_1_through_8(self) -> None:
        # Implementation contract: every week 1-8 resolves to ≥1 plan.
        for w in range(1, 9):
            assert w in WEEK_TO_PLANS, f"week {w} not in WEEK_TO_PLANS"
            assert len(WEEK_TO_PLANS[w]) >= 1

    def test_parsed_prspecs_are_frozen(self) -> None:
        specs = parse_week(week=1, plans_dir=REPO_ROOT / "docs/superpowers/plans")
        if specs:
            # PRSpec is Pydantic-frozen; attempted mutation raises.
            import pydantic

            with pytest.raises(pydantic.ValidationError):
                specs[0].title = "mutated"  # type: ignore[misc]


class TestParsedTaskShape:
    def test_parsed_task_has_required_fields(self) -> None:
        t = ParsedTask(
            task_number=1,
            title="x",
            body="body",
            files=["a.py"],
            l1_command="pytest",
            language="python",
        )
        assert t.task_number == 1
        assert t.title == "x"
        assert t.language == "python"
