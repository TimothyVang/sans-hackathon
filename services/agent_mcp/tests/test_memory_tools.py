"""Tests for memory_remember + memory_recall MCP tools (A3 §2.2)."""

from pathlib import Path

import pytest

from findevil_agent_mcp.tools.memory_recall import (
    SPEC as RECALL_SPEC,
    MemoryRecallInput,
)
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


@pytest.mark.asyncio
async def test_memory_recall_returns_remembered_row(tmp_path: Path) -> None:
    db = tmp_path / "memory.sqlite"
    # Seed via the remember tool.
    await REMEMBER_SPEC.handler(
        MemoryRememberInput(
            store_path=str(db),
            case_id="case-recall-1",
            kind="ioc",
            key="badguy.example",
            value="badguy.example c2 domain",
            sha256="sha256:" + "f" * 64,
        )
    )
    # Recall.
    out = await RECALL_SPEC.handler(
        MemoryRecallInput(store_path=str(db), query="badguy", limit=5)
    )
    assert len(out.hits) == 1
    assert out.hits[0].case_id == "case-recall-1"
    assert out.hits[0].confidence > 0.0
