"""OpenTimestamps Bitcoin anchor for the run manifest.

Spec #2 §7.1 fourth tier. After the verifier approves all findings
and the Merkle root is finalized, ``ots stamp run.manifest.json``
submits the manifest to OpenTimestamps calendar servers; their
aggregation tree includes the next Bitcoin block. ``ots upgrade``
later replaces the calendar receipt with a Bitcoin-block proof.
``ots verify`` reproduces the proof offline with only a Bitcoin
header.

We shell out to the ``ots`` CLI from the ``opentimestamps-client``
PyPI package (Spec #2 §16 pin: ``opentimestamps-client==0.7.2``).
The wrapper handles three calls:

  * ``stamp(path)`` → produces ``path.ots`` (calendar receipt).
  * ``upgrade(path)`` → upgrades the receipt with Bitcoin proof.
  * ``verify(path)`` → green/red against either tier.

All calls are subprocess-based; failures surface as
``OtsError`` with the captured stderr.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class OtsError(RuntimeError):
    """OpenTimestamps subprocess returned non-zero or output was unparseable."""


@dataclass(frozen=True)
class OtsResult:
    """Outcome of an OTS subprocess invocation."""

    ok: bool
    stdout: str
    stderr: str
    receipt_path: Path | None
    """Path to the ``.ots`` receipt file. ``None`` on stamp failure."""


@dataclass(frozen=True)
class OtsVerification:
    """Outcome of ``ots verify``.

    ``upgraded`` is True when the receipt has a Bitcoin attestation
    (i.e. ``ots upgrade`` already succeeded for this receipt).
    Calendar-only proofs are still verifiable but get
    ``upgraded=False`` so callers can flag them as "pending Bitcoin
    confirmation".
    """

    verified: bool
    upgraded: bool
    bitcoin_block_height: int | None
    block_hash: str | None
    detail: str  # human-readable summary, e.g. for the verdict card


# ---------------------------------------------------------------------------
# Subprocess helpers.
# ---------------------------------------------------------------------------


def _ots_binary() -> str:
    """Resolve the ``ots`` CLI path. Raises OtsError if absent."""
    env = shutil.which("ots") or shutil.which("ots-cli")
    if env is None:
        raise OtsError(
            "`ots` CLI not on PATH. Install with `pip install opentimestamps-client==0.7.2` "
            "(matches Spec #2 §16 pin) or set OTS_BIN."
        )
    return env


def stamp(target_path: Path, *, ots_bin: str | None = None) -> OtsResult:
    """Run ``ots stamp <path>``. Produces ``<path>.ots`` on success."""
    if not target_path.is_file():
        raise OtsError(f"target file not found: {target_path}")

    binary = ots_bin or _ots_binary()
    proc = subprocess.run(
        [binary, "stamp", str(target_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    receipt = target_path.with_suffix(target_path.suffix + ".ots")
    if proc.returncode == 0 and receipt.is_file():
        return OtsResult(
            ok=True,
            stdout=proc.stdout,
            stderr=proc.stderr,
            receipt_path=receipt,
        )
    return OtsResult(
        ok=False,
        stdout=proc.stdout,
        stderr=proc.stderr,
        receipt_path=None,
    )


def upgrade(receipt_path: Path, *, ots_bin: str | None = None) -> OtsResult:
    """Run ``ots upgrade <receipt.ots>``. In-place: rewrites the file
    once a Bitcoin proof is available.

    This is async by nature — calendar servers wait for a Bitcoin
    block. Callers typically poll on a background thread; we expose
    a single-shot wrapper.
    """
    if not receipt_path.is_file():
        raise OtsError(f"receipt file not found: {receipt_path}")
    binary = ots_bin or _ots_binary()
    proc = subprocess.run(
        [binary, "upgrade", str(receipt_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return OtsResult(
        ok=proc.returncode == 0,
        stdout=proc.stdout,
        stderr=proc.stderr,
        receipt_path=receipt_path,
    )


def verify(
    target_path: Path,
    *,
    ots_bin: str | None = None,
    receipt_path: Path | None = None,
) -> OtsVerification:
    """Run ``ots verify <path>`` and parse the result.

    ``ots verify`` exits 0 on success regardless of whether the
    receipt is calendar-only or Bitcoin-anchored. We parse the
    stdout to distinguish, populating ``bitcoin_block_height``
    + ``block_hash`` when the upgrade has happened.
    """
    if not target_path.is_file():
        raise OtsError(f"target file not found: {target_path}")
    if receipt_path is None:
        receipt_path = target_path.with_suffix(target_path.suffix + ".ots")
    if not receipt_path.is_file():
        raise OtsError(f"receipt file not found: {receipt_path}")

    binary = ots_bin or _ots_binary()
    proc = subprocess.run(
        [binary, "verify", str(target_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return _parse_verify(proc.returncode, proc.stdout, proc.stderr)


def _parse_verify(returncode: int, stdout: str, stderr: str) -> OtsVerification:
    """Parse the ``ots verify`` output into an OtsVerification.

    The CLI's text output isn't machine-formatted; we look for the
    canonical phrases. Schema-drift fallback: if returncode is 0
    and we can't extract a block, we still return verified=True
    upgraded=False so the verdict UI can show "calendar receipt,
    awaiting Bitcoin confirmation".
    """
    combined = (stdout or "") + "\n" + (stderr or "")
    verified = returncode == 0
    if not verified:
        return OtsVerification(
            verified=False,
            upgraded=False,
            bitcoin_block_height=None,
            block_hash=None,
            detail=(stderr or stdout or "").strip()[:300] or "ots verify failed",
        )

    upgraded = "Bitcoin block" in combined or "block hash" in combined.lower()
    block_height: int | None = None
    block_hash: str | None = None
    for line in combined.splitlines():
        line_l = line.lower().strip()
        if "bitcoin block" in line_l:
            # Common shapes: "Bitcoin block N", "Bitcoin block N (hash)"
            tokens = line.split()
            import contextlib

            for i, tok in enumerate(tokens):
                if tok.lower() == "block" and i + 1 < len(tokens):
                    with contextlib.suppress(ValueError):
                        block_height = int(tokens[i + 1].rstrip("(").rstrip(":"))
                    break
        if "block hash" in line_l:
            for tok in line.split():
                if len(tok) >= 16 and all(c in "0123456789abcdefABCDEF" for c in tok):
                    block_hash = tok.lower()
                    break

    detail = (
        f"Bitcoin block {block_height} ({block_hash})"
        if upgraded and block_height is not None
        else "Calendar receipt — awaiting Bitcoin confirmation"
        if not upgraded
        else "Verified (block detail unparsed)"
    )
    return OtsVerification(
        verified=True,
        upgraded=upgraded,
        bitcoin_block_height=block_height,
        block_hash=block_hash,
        detail=detail,
    )


__all__ = [
    "OtsError",
    "OtsResult",
    "OtsVerification",
    "stamp",
    "upgrade",
    "verify",
]
