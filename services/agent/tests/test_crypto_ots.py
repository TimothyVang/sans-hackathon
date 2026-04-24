"""Tests for findevil_agent.crypto.ots — wraps the `ots` CLI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from findevil_agent.crypto.ots import (
    OtsError,
    OtsVerification,
    _parse_verify,
    stamp,
    upgrade,
    verify,
)


class TestOtsBinary:
    def test_stamp_target_must_exist(self, tmp_path: Path) -> None:
        with pytest.raises(OtsError):
            stamp(tmp_path / "nope.json", ots_bin="/usr/bin/false")

    def test_upgrade_receipt_must_exist(self, tmp_path: Path) -> None:
        with pytest.raises(OtsError):
            upgrade(tmp_path / "nope.ots", ots_bin="/usr/bin/false")

    def test_verify_target_must_exist(self, tmp_path: Path) -> None:
        with pytest.raises(OtsError):
            verify(tmp_path / "nope.json", ots_bin="/usr/bin/false")

    def test_verify_receipt_must_exist(self, tmp_path: Path) -> None:
        target = tmp_path / "manifest.json"
        target.write_text("{}", encoding="utf-8")
        # No .ots receipt next to the target.
        with pytest.raises(OtsError):
            verify(target, ots_bin="/usr/bin/false")


class TestParseVerify:
    def test_failed_returncode_returns_unverified(self) -> None:
        v = _parse_verify(returncode=1, stdout="", stderr="bad")
        assert isinstance(v, OtsVerification)
        assert v.verified is False
        assert v.upgraded is False
        assert "bad" in v.detail.lower()

    def test_calendar_only_receipt(self) -> None:
        stdout = "Calendar verification: success\n"
        v = _parse_verify(returncode=0, stdout=stdout, stderr="")
        assert v.verified is True
        assert v.upgraded is False
        assert "calendar" in v.detail.lower() or "awaiting" in v.detail.lower()

    def test_bitcoin_anchored_receipt(self) -> None:
        stdout = (
            "Verification successful\n"
            "Bitcoin block 873421\n"
            "block hash 00000000000000000001a2b3c4d5e6f700112233445566778899aabbccddeeff0\n"
        )
        v = _parse_verify(returncode=0, stdout=stdout, stderr="")
        assert v.verified is True
        assert v.upgraded is True
        assert v.bitcoin_block_height == 873421
        assert v.block_hash is not None
        assert "873421" in v.detail

    def test_unparseable_success_returns_partial(self) -> None:
        # Schema drift: returncode 0 but no recognizable phrases.
        v = _parse_verify(returncode=0, stdout="ok\n", stderr="")
        assert v.verified is True
        # Not upgraded — we never saw the Bitcoin marker.
        assert v.upgraded is False


class TestStampSubprocessMocked:
    def test_stamp_success_returns_receipt_path(self, tmp_path: Path) -> None:
        target = tmp_path / "manifest.json"
        target.write_text('{"x":1}', encoding="utf-8")
        # Pretend the subprocess wrote the receipt + returned 0.
        receipt_path = target.with_suffix(target.suffix + ".ots")
        receipt_path.write_bytes(b"fake-receipt")
        with patch(
            "findevil_agent.crypto.ots.subprocess.run"
        ) as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            result = stamp(target, ots_bin="/fake/ots")
        assert result.ok is True
        assert result.receipt_path == receipt_path

    def test_stamp_failure_returns_no_receipt(self, tmp_path: Path) -> None:
        target = tmp_path / "manifest.json"
        target.write_text('{"x":1}', encoding="utf-8")
        with patch(
            "findevil_agent.crypto.ots.subprocess.run"
        ) as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = "calendar unreachable"
            result = stamp(target, ots_bin="/fake/ots")
        assert result.ok is False
        assert result.receipt_path is None
        assert "calendar" in result.stderr


class TestUpgradeSubprocessMocked:
    def test_upgrade_calls_ots_upgrade(self, tmp_path: Path) -> None:
        receipt = tmp_path / "manifest.json.ots"
        receipt.write_bytes(b"fake")
        with patch(
            "findevil_agent.crypto.ots.subprocess.run"
        ) as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Got 1 attestation"
            mock_run.return_value.stderr = ""
            result = upgrade(receipt, ots_bin="/fake/ots")
        assert result.ok is True
        # Verify the binary was invoked with the right subcommand.
        args = mock_run.call_args[0][0]
        assert args[0] == "/fake/ots"
        assert args[1] == "upgrade"
        assert args[2] == str(receipt)
