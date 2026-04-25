"""``ots_verify`` tool — verify the OpenTimestamps Bitcoin proof.

Wraps :func:`findevil_agent.crypto.ots.verify`. Returns
``upgraded=True`` when the receipt has a Bitcoin attestation;
``upgraded=False`` when only a calendar receipt is present (the
server has accepted the stamp but Bitcoin hasn't confirmed yet).
"""

from __future__ import annotations

from pathlib import Path

from findevil_agent.crypto.ots import OtsError, verify
from pydantic import BaseModel, ConfigDict, Field

from findevil_agent_mcp.tools._base import ToolSpec


class OtsVerifyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_path: str = Field(..., description="Absolute path to the stamped file.")
    receipt_path: str | None = Field(
        default=None,
        description="Override the .ots receipt path; defaults to <target>.ots.",
    )
    ots_bin: str | None = Field(
        default=None,
        description="Override the `ots` binary path; defaults to PATH lookup.",
    )


class OtsVerifyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verified: bool
    upgraded: bool = Field(..., description="True if the receipt has a Bitcoin block attestation.")
    bitcoin_block_height: int | None
    block_hash: str | None
    detail: str


async def _handle(inp: BaseModel) -> OtsVerifyOutput:
    assert isinstance(inp, OtsVerifyInput)
    try:
        result = verify(
            Path(inp.target_path),
            ots_bin=inp.ots_bin,
            receipt_path=Path(inp.receipt_path) if inp.receipt_path else None,
        )
    except OtsError as exc:
        return OtsVerifyOutput(
            verified=False,
            upgraded=False,
            bitcoin_block_height=None,
            block_hash=None,
            detail=str(exc),
        )
    return OtsVerifyOutput(
        verified=result.verified,
        upgraded=result.upgraded,
        bitcoin_block_height=result.bitcoin_block_height,
        block_hash=result.block_hash,
        detail=result.detail,
    )


SPEC = ToolSpec(
    name="ots_verify",
    description=(
        "Verify an OpenTimestamps receipt (.ots) against its target file. This is the "
        "step that proves to a third party that the manifest existed at or before a "
        "specific Bitcoin block height — the cornerstone of the FRE 902(14) "
        "self-authenticating evidence claim. "
        "Two outcome states: (a) verified=True, upgraded=True with a populated "
        "bitcoin_block_height + block_hash → fully Bitcoin-anchored proof; "
        "(b) verified=True, upgraded=False → calendar receipt only, awaiting Bitcoin "
        "confirmation (this is normal in the first 10-30 min after ots_stamp). "
        "verified=False means the receipt does NOT match the target file's bytes — "
        "either tampering or wrong receipt path; the detail string explains which. "
        "Requires the `ots` CLI on PATH (same as ots_stamp). "
        "Pass receipt_path explicitly if the .ots file was renamed or moved away from "
        "<target>.ots."
    ),
    input_model=OtsVerifyInput,
    output_model=OtsVerifyOutput,
    handler=_handle,
)

__all__ = ["OtsVerifyInput", "OtsVerifyOutput", "SPEC"]
