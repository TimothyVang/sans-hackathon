"""Tests for workers/*.py.

Uses dry_run=True to skip real claude CLI invocations; these tests
still exercise prompt composition, env setup, worktree creation, diff
counting, sidecar writing, and WorkerResult shape.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from findevil_swarm.state import PRSpec
from findevil_swarm.workers import (
    BaseWorker,
    PythonWorker,
    RustWorker,
    TypeScriptWorker,
    WorkerInput,
)


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "test"], check=True
    )
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


@pytest.fixture()
def sample_spec() -> PRSpec:
    return PRSpec(
        pr_id="test-pr-001",
        week=2,
        language="python",
        title="Sample PR for worker tests",
        description="Implement the foo function per Spec #2 §6.",
        files_expected=["services/foo/bar.py"],
        l1_command="pytest tests/foo/ -v",
        token_ceiling=500_000,
        max_turns=40,
    )


# ---------------------------------------------------------------------------
# Language classes + defaults.
# ---------------------------------------------------------------------------


class TestLanguageDefaults:
    def test_rust_language(self) -> None:
        assert RustWorker.language == "rust"
        assert "cargo test" in RustWorker.default_l1_command

    def test_python_language(self) -> None:
        assert PythonWorker.language == "python"
        assert "pytest" in PythonWorker.default_l1_command

    def test_typescript_language(self) -> None:
        assert TypeScriptWorker.language == "typescript"
        assert "pnpm" in TypeScriptWorker.default_l1_command

    def test_rust_prompt_mentions_rmcp(self) -> None:
        assert "rmcp" in RustWorker.system_prompt_fragment.lower()

    def test_python_prompt_mentions_uv(self) -> None:
        assert "uv" in PythonWorker.system_prompt_fragment.lower()

    def test_ts_prompt_mentions_pnpm(self) -> None:
        assert "pnpm" in TypeScriptWorker.system_prompt_fragment.lower()

    def test_ts_prompt_calls_out_dfir_vocabulary(self) -> None:
        assert "DFIR vocabulary" in TypeScriptWorker.system_prompt_fragment


class TestBuildPrompt:
    def test_base_prompt_includes_description(self, sample_spec: PRSpec) -> None:
        prompt = PythonWorker().build_prompt(sample_spec)
        assert sample_spec.description in prompt

    def test_prompt_lists_expected_files(self, sample_spec: PRSpec) -> None:
        prompt = PythonWorker().build_prompt(sample_spec)
        assert "services/foo/bar.py" in prompt

    def test_prompt_includes_l1_command(self, sample_spec: PRSpec) -> None:
        prompt = PythonWorker().build_prompt(sample_spec)
        assert sample_spec.l1_command in prompt

    def test_rust_prompt_layers_in_rust_fragment(self, sample_spec: PRSpec) -> None:
        # Even with a python spec, RustWorker layers in its own guidance.
        prompt = RustWorker().build_prompt(sample_spec)
        assert "rmcp" in prompt.lower()


class TestBuildEnv:
    def test_fork_subagent_always_set(self) -> None:
        env = PythonWorker().build_env({})
        assert env["CLAUDE_CODE_FORK_SUBAGENT"] == "1"

    def test_autocompact_always_disabled(self) -> None:
        env = PythonWorker().build_env({})
        assert env["CLAUDE_AUTOCOMPACT"] == "0"

    def test_overrides_layer_on_top(self) -> None:
        env = PythonWorker().build_env({"CUSTOM_VAR": "xyz"})
        assert env["CUSTOM_VAR"] == "xyz"

    def test_overrides_can_replace_defaults(self) -> None:
        env = PythonWorker().build_env({"CLAUDE_AUTOCOMPACT": "1"})
        assert env["CLAUDE_AUTOCOMPACT"] == "1"


# ---------------------------------------------------------------------------
# execute() — dry-run path; doesn't touch the real claude CLI.
# ---------------------------------------------------------------------------


class TestExecuteDryRun:
    def test_dry_run_produces_worker_result(
        self, tmp_repo: Path, sample_spec: PRSpec, tmp_path: Path
    ) -> None:
        sidecar = tmp_path / "sidecar.jsonl"
        inp = WorkerInput(
            pr_spec=sample_spec,
            repo=tmp_repo,
            jsonl_sidecar_path=sidecar,
            dry_run=True,
        )
        result = PythonWorker().execute(inp)
        assert result.pr_id == sample_spec.pr_id
        assert result.claude_exit_code == 0
        assert result.l1_exit_code == 0
        assert result.worktree_path.is_dir()

    def test_dry_run_writes_sidecar_record(
        self, tmp_repo: Path, sample_spec: PRSpec, tmp_path: Path
    ) -> None:
        sidecar = tmp_path / "sidecar.jsonl"
        inp = WorkerInput(
            pr_spec=sample_spec,
            repo=tmp_repo,
            jsonl_sidecar_path=sidecar,
            dry_run=True,
        )
        PythonWorker().execute(inp)
        assert sidecar.is_file()
        lines = sidecar.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["pr_id"] == sample_spec.pr_id
        assert record["language"] == "python"
        assert record["claude_exit_code"] == 0

    def test_dry_run_creates_worktree(
        self, tmp_repo: Path, sample_spec: PRSpec, tmp_path: Path
    ) -> None:
        sidecar = tmp_path / "sidecar.jsonl"
        inp = WorkerInput(
            pr_spec=sample_spec,
            repo=tmp_repo,
            jsonl_sidecar_path=sidecar,
            dry_run=True,
        )
        result = PythonWorker().execute(inp)
        assert result.worktree_path.name.startswith("wt-python-")
        assert result.worktree_path.is_dir()


# ---------------------------------------------------------------------------
# BaseWorker class-level smoke (no subclass).
# ---------------------------------------------------------------------------


class TestBaseWorker:
    def test_base_is_instantiable(self) -> None:
        # BaseWorker defaults to python; instantiable for testing purposes.
        w = BaseWorker()
        assert w.language == "python"
