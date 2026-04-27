"""Tests for memory_remember + memory_recall MCP tools (A3 §2.2)."""

from pathlib import Path

import pytest

from findevil_agent_mcp.tools.memory_remember import (
    SPEC as REMEMBER_SPEC,
    MemoryRememberInput,
)


@pytest.mark.asyncio
async def test_memory_remember_writes_row(tmp_path: Path) -> None:
    db = tmp_path / "memory.sqlite"
    inp = MemoryRememberInput(
        store_path=str(db),
        case_id="case-001",
        kind="hash",
        key="evil.exe",
        value="evil.exe sha=abc",
        sha256="sha256:" + "a" * 64,
    )
    out = await REMEMBER_SPEC.handler(inp)
    assert out.case_id == "case-001"
    assert out.kind == "hash"
    assert db.exists()
