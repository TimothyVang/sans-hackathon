"""``ots_stamp`` tool — anchor a manifest to Bitcoin via OpenTimestamps.

Wraps :func:`findevil_agent.crypto.ots.stamp`. Subprocess invocation
of the ``ots`` CLI from the ``opentimestamps-client`` Python package.
Produces ``<target_path>.ots`` (calendar receipt) on success;
``ots_verify`` later upgrades + verifies it against the next Bitcoin
block.
"""

from __future__ import annotations

from pathlib import Path

from findevil_agent.crypto.ots import OtsError, stamp
from pydantic import BaseModel, ConfigDict, Field

from findevil_agent_mcp.tools._base import ToolSpec


class OtsStampInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_path: str = Field(
        ..., description="Absolute path to file to stamp (typically run.manifest.json)."
    )
    ots_bin: str | None = Field(
        default=None,
        description="Override the `ots` binary path; defaults to PATH lookup.",
    )


class OtsStampOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    receipt_path: str | None
    stdout: str
    stderr: str


async def _handle(inp: BaseModel) -> OtsStampOutput:
    assert isinstance(inp, OtsStampInput)
    try:
        result = stamp(Path(inp.target_path), ots_bin=inp.ots_bin)
    except OtsError as exc:
        return OtsStampOutput(
            ok=False,
            receipt_path=None,
            stdout="",
            stderr=str(exc),
        )
    return OtsStampOutput(
        ok=result.ok,
        receipt_path=str(result.receipt_path) if result.receipt_path else None,
        stdout=result.stdout,
        stderr=result.stderr,
    )


SPEC = ToolSpec(
    name="ots_stamp",
    description=(
        "Bitcoin-anchor a file (typically run.manifest.json from manifest_finalize) via "
        "OpenTimestamps calendar servers. This is the THIRD crypto-custody tier (after "
        "Merkle + sigstore) and is what makes the run FRE 902(14) self-authenticating "
        "without needing our infrastructure online to verify. "
        "Produces a calendar receipt at <path>.ots immediately; that receipt is "
        "'upgradable' to a full Bitcoin proof once the next block confirms (typically "
        "10-30 min). Until then, ots_verify reports verified=True, upgraded=False — "
        "still cryptographically meaningful, just not yet Bitcoin-anchored. "
        "Requires the `ots` CLI on PATH (from `pip install opentimestamps-client==0.7.2`). "
        "On error: ots_bin not found → install opentimestamps-client; calendar server "
        "unreachable → retry later (this tool does not retry internally — the swarm "
        "session_guard pattern applies)."
    ),
    input_model=OtsStampInput,
    output_model=OtsStampOutput,
    handler=_handle,
)

__all__ = ["OtsStampInput", "OtsStampOutput", "SPEC"]
