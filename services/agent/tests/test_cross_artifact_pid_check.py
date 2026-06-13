"""Tests for findevil_agent.correlator.cross_artifact_pid_check.

The check is a cross-source DEPTH lead: when a case has both memory process
evidence and on-disk execution records (Prefetch / Amcache), a memory-resident
process with no matching disk record is a discrepancy worth a HYPOTHESIS lead.
It is deliberately NOT an execution claim, so the correlator's >=2-artifact
downgrade path must leave it untouched.
"""

from __future__ import annotations

from findevil_agent.correlator import (
    MemoryProcess,
    correlate,
    cross_artifact_pid_check,
)
from findevil_agent.execution_claim import is_execution_claim


def _proc(
    name: str, pid: int = 100, *, source: str = "pslist", tcid: str = "tc-7"
) -> MemoryProcess:
    return MemoryProcess(pid=pid, name=name, source=source, tool_call_id=tcid)


CASE = {"case_id": "c", "memory_artifact_path": "memory.raw"}


class TestEmission:
    def test_emits_hypothesis_for_uncorroborated_process(self) -> None:
        findings = cross_artifact_pid_check(
            [_proc("evil.exe", 1337)], {"cmd.exe", "explorer.exe"}, **CASE
        )
        assert len(findings) == 1
        f = findings[0]
        assert f.confidence == "HYPOTHESIS"
        assert f.description.startswith("hypothesis:")
        assert "evil.exe" in f.description
        assert "1337" in f.description

    def test_emitted_finding_cites_memory_tool_call_id(self) -> None:
        findings = cross_artifact_pid_check([_proc("evil.exe", tcid="tc-42")], {"cmd.exe"}, **CASE)
        assert findings[0].tool_call_id == "tc-42"
        assert findings[0].artifact_path == "memory.raw"

    def test_finding_is_not_an_execution_claim(self) -> None:
        # Critical: description must stay verb-neutral so the correlator's
        # execution >=2-artifact gate does not fire on it.
        findings = cross_artifact_pid_check([_proc("evil.exe")], {"cmd.exe"}, **CASE)
        assert is_execution_claim(findings[0].description, findings[0].mitre_technique) is False
        # correlate() should pass it through unchanged (non-execution claim, kept).
        refined, outcomes = correlate(findings)
        assert refined[0].confidence == "HYPOTHESIS"
        assert outcomes[0].action == "kept"


class TestSuppression:
    def test_corroborated_process_suppressed(self) -> None:
        assert cross_artifact_pid_check([_proc("cmd.exe")], {"cmd.exe"}, **CASE) == []

    def test_case_insensitive_corroboration(self) -> None:
        assert cross_artifact_pid_check([_proc("EVIL.EXE")], {"evil.exe"}, **CASE) == []

    def test_basename_normalization_on_disk_paths(self) -> None:
        # Disk record carried as a full path still corroborates the bare process name.
        assert (
            cross_artifact_pid_check(
                [_proc("evil.exe")], {r"C:\\Windows\\System32\\evil.exe"}, **CASE
            )
            == []
        )

    def test_no_disk_records_returns_empty(self) -> None:
        # Prefetch may be disabled (SSD / EnablePrefetcher=0). With zero disk
        # execution records, absence proves nothing -> suppress entirely.
        assert cross_artifact_pid_check([_proc("evil.exe")], set(), **CASE) == []

    def test_no_memory_processes_returns_empty(self) -> None:
        assert cross_artifact_pid_check([], {"cmd.exe"}, **CASE) == []

    def test_system_processes_skipped(self) -> None:
        procs = [_proc("System", 4), _proc("lsass.exe", 612), _proc("svchost.exe", 800)]
        assert cross_artifact_pid_check(procs, {"cmd.exe"}, **CASE) == []


class TestDedup:
    def test_dedupe_across_pslist_and_psscan(self) -> None:
        procs = [
            _proc("evil.exe", 1337, source="pslist"),
            _proc("evil.exe", 1337, source="psscan"),
        ]
        findings = cross_artifact_pid_check(procs, {"cmd.exe"}, **CASE)
        assert len(findings) == 1

    def test_distinct_processes_each_emit(self) -> None:
        procs = [_proc("evil.exe", 1), _proc("nc.exe", 2)]
        findings = cross_artifact_pid_check(procs, {"cmd.exe"}, **CASE)
        assert len(findings) == 2
        assert {"evil.exe", "nc.exe"} <= {tok for f in findings for tok in f.description.split()}
