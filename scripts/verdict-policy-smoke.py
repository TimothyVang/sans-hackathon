#!/usr/bin/env python3
"""verdict-policy-smoke — lock in the compute_verdict policy in CI.

`docs/verdict-semantics.md` describes the verdict policy as
"deterministic policy, not learned classifier; changing the policy
is a code change with a clear diff and CI run." This smoke test
makes that claim load-bearing — every CI build asserts that
`compute_verdict` produces the documented output for each
canonical case.

Loads `Investigation.compute_verdict` from `find_evil_auto.py` via
importlib (same pattern find_evil_auto uses for fleet_correlate's
COMMON_WIN_PROCS — single-source-of-truth, no copy-paste of
policy logic).

If you intend to change the policy, change `compute_verdict` AND
update this file's expected outputs together. The diff in the
commit will then encode the policy change explicitly.

Exit code: 0 on full pass, 1 on first assertion failure.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent


def load_find_evil_auto():
    """Load scripts/find_evil_auto.py as a module without spinning up
    the orchestrator's main()."""
    spec = importlib.util.spec_from_file_location(
        "find_evil_auto_under_test",
        REPO / "scripts" / "find_evil_auto.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not build spec for find_evil_auto.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def case(label: str, merged: list[dict[str, Any]], expected: str) -> tuple[str, bool]:
    return (label, merged, expected)


def main() -> int:
    fea = load_find_evil_auto()
    # compute_verdict is an instance method on Investigation but only
    # reads `self` for nothing — pure on `merged`. Call as unbound
    # method passing None for self; Python doesn't care.
    compute_verdict = lambda merged: fea.Investigation.compute_verdict(None, merged)  # noqa: E731
    detect_evidence_type = fea.detect_evidence_type
    build_attack_coverage = fea.build_attack_coverage
    build_evtx_summary = fea.build_evtx_summary
    build_next_actions = fea.build_next_actions
    evtx_rows_to_findings = fea.evtx_rows_to_findings
    process_sets_diverge = fea.process_sets_diverge
    write_timeline_csv = fea.write_timeline_csv
    print("=" * 60)
    print("Find Evil! — verdict + evidence/process policy smoke")
    print("=" * 60)

    cases: list[tuple[str, list[dict[str, Any]], str]] = [
        # ----- empty -----
        case("empty merged list -> NO_EVIL", [], "NO_EVIL"),
        # ----- CONFIRMED tier triggers SUSPICIOUS regardless of MITRE -----
        case(
            "single CONFIRMED finding (no MITRE) -> SUSPICIOUS",
            [{"confidence": "CONFIRMED", "mitre_technique": None}],
            "SUSPICIOUS",
        ),
        case(
            "CONFIRMED with low-severity MITRE -> SUSPICIOUS",
            [{"confidence": "CONFIRMED", "mitre_technique": "T1098"}],
            "SUSPICIOUS",
        ),
        # ----- INFERRED on T1014 / T1055 triggers SUSPICIOUS -----
        case(
            "INFERRED + T1014 (DKOM) -> SUSPICIOUS",
            [{"confidence": "INFERRED", "mitre_technique": "T1014"}],
            "SUSPICIOUS",
        ),
        case(
            "INFERRED + T1055 (Process Injection) -> SUSPICIOUS",
            [{"confidence": "INFERRED", "mitre_technique": "T1055"}],
            "SUSPICIOUS",
        ),
        # ----- INFERRED on a non-severe technique stays INDETERMINATE -----
        case(
            "INFERRED + T1098 (Account Manipulation) -> INDETERMINATE",
            [{"confidence": "INFERRED", "mitre_technique": "T1098"}],
            "INDETERMINATE",
        ),
        # ----- HYPOTHESIS-only -> INDETERMINATE even with severe MITRE -----
        case(
            "HYPOTHESIS + T1014 -> INDETERMINATE (HYPOTHESIS doesn't count)",
            [{"confidence": "HYPOTHESIS", "mitre_technique": "T1014"}],
            "INDETERMINATE",
        ),
        case(
            "HYPOTHESIS + T1055 -> INDETERMINATE",
            [{"confidence": "HYPOTHESIS", "mitre_technique": "T1055"}],
            "INDETERMINATE",
        ),
        # ----- mixed: CONFIRMED dominates -----
        case(
            "mixed CONFIRMED + HYPOTHESIS -> SUSPICIOUS",
            [
                {"confidence": "HYPOTHESIS", "mitre_technique": "T1098"},
                {"confidence": "CONFIRMED", "mitre_technique": None},
            ],
            "SUSPICIOUS",
        ),
        # ----- mixed: INFERRED + non-severe MITRE -> INDETERMINATE
        # unless one of them has T1014/T1055 -----
        case(
            "INFERRED T1098 + INFERRED T1014 -> SUSPICIOUS (T1014 carries it)",
            [
                {"confidence": "INFERRED", "mitre_technique": "T1098"},
                {"confidence": "INFERRED", "mitre_technique": "T1014"},
            ],
            "SUSPICIOUS",
        ),
        # ----- the SRL-2018 base-rd-05 real-world case (commit 94c08dd
        #       end-to-end test): 2 HYPOTHESIS findings, no CONFIRMED,
        #       INFERRED T1055 absent -> INDETERMINATE -----
        case(
            "real base-rd-05 shape (2 HYPOTHESIS, no severe INFERRED) -> INDETERMINATE",
            [
                {"confidence": "HYPOTHESIS", "mitre_technique": "T1055"},
                {"confidence": "HYPOTHESIS", "mitre_technique": None},
            ],
            "INDETERMINATE",
        ),
    ]

    failures = 0
    for label, merged, expected in cases:
        actual = compute_verdict(merged)
        ok = actual == expected
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] verdict: {label}")
        if not ok:
            print(f"         expected: {expected!r}")
            print(f"         actual  : {actual!r}")
            failures += 1

    # ----- detect_evidence_type dispatch -----------------------------
    # Routes the orchestrator to the right per-type playbook (memory
    # → vol_pslist+psscan+malfind; evtx → evtx_query+hayabusa;
    # disk → case_open only). A regression here means evidence
    # silently dispatches to the wrong tool sequence.
    et_cases: list[tuple[str, str, str]] = [
        # memory variants
        ("base-dc-memory.img -> memory", "/mnt/x/base-dc-memory.img", "memory"),
        ("foo.mem -> memory", "foo.mem", "memory"),
        ("foo.raw -> memory", "foo.raw", "memory"),
        ("foo.vmem -> memory", "foo.vmem", "memory"),
        ("foo.dmp -> memory", "foo.dmp", "memory"),
        ("foo.lime -> memory", "foo.lime", "memory"),
        # evtx
        ("Security.evtx -> evtx", "/var/log/Security.evtx", "evtx"),
        # disk variants
        ("foo.E01 -> disk (case-insensitive)", "foo.E01", "disk"),
        ("foo.e01 -> disk", "foo.e01", "disk"),
        ("foo.dd -> disk", "foo.dd", "disk"),
        ("foo.aff -> disk", "foo.aff", "disk"),
        ("foo.aff4 -> disk", "foo.aff4", "disk"),
        ("foo.001 -> disk (split-image)", "foo.001", "disk"),
        # unknown
        ("foo.txt -> unknown", "foo.txt", "unknown"),
        (
            "foo.zip -> unknown (Velociraptor zip needs explicit handling)",
            "foo.zip",
            "unknown",
        ),
        ("no extension -> unknown", "foo", "unknown"),
    ]
    for label, path, expected in et_cases:
        actual = detect_evidence_type(path)
        ok = actual == expected
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] evtype: {label}")
        if not ok:
            print(f"         path    : {path!r}")
            print(f"         expected: {expected!r}")
            print(f"         actual  : {actual!r}")
            failures += 1

    # ----- EVTX parse success is summary/timeline, not suspicion -------
    benign_evtx_rows = [
        {
            "event_id": 4624,
            "ts": "2026-05-04T00:00:00Z",
            "channel": "Security",
            "record_id": 1,
            "data": {"Event": {"System": {"EventID": 4624}}},
        },
        {
            "event_id": 4634,
            "ts": "2026-05-04T00:01:00Z",
            "channel": "Security",
            "record_id": 2,
            "data": {"Event": {"System": {"EventID": 4634}}},
        },
    ]
    benign_summary = build_evtx_summary(benign_evtx_rows, 2, 0)
    benign_findings = evtx_rows_to_findings(
        benign_evtx_rows, "tc-evtx", "case-evtx", "Security.evtx"
    )
    suspicious_rows = [
        {
            "event_id": 1102,
            "ts": "2026-05-04T00:02:00Z",
            "channel": "Security",
            "record_id": 3,
            "data": {"Event": {"System": {"EventID": 1102}}},
        }
    ]
    suspicious_findings = evtx_rows_to_findings(
        suspicious_rows, "tc-evtx", "case-evtx", "Security.evtx"
    )
    evtx_cases = [
        (
            "benign EVTX summary counts records",
            benign_summary.get("records_seen"),
            2,
        ),
        (
            "benign EVTX parse success creates no findings",
            len(benign_findings),
            0,
        ),
        (
            "benign EVTX findings produce NO_EVIL",
            compute_verdict(benign_findings),
            "NO_EVIL",
        ),
        (
            "audit-log clear EVTX creates a finding",
            len(suspicious_findings),
            1,
        ),
        (
            "audit-log clear EVTX can drive SUSPICIOUS",
            compute_verdict(suspicious_findings),
            "SUSPICIOUS",
        ),
    ]
    for label, actual, expected in evtx_cases:
        ok = actual == expected
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] evtx: {label}")
        if not ok:
            print(f"         expected: {expected!r}")
            print(f"         actual  : {actual!r}")
            failures += 1

    # ----- ATT&CK coverage + next-actions process layer -------------
    process_checks = 0
    completeness = {
        "checks": [
            {"artifact_class": "memory", "available": True, "touched": True},
            {"artifact_class": "evtx", "available": False, "touched": False},
            {
                "artifact_class": "disk/filesystem",
                "available": False,
                "touched": False,
            },
            {"artifact_class": "network", "available": False, "touched": False},
        ]
    }
    tool_calls = [
        {"tool": "case_open"},
        {"tool": "vol_pslist"},
        {"tool": "vol_psscan"},
        {"tool": "vol_psxview"},
        {"tool": "vol_malfind"},
    ]
    findings = [
        {"confidence": "INFERRED", "mitre_technique": "T1014"},
        {"confidence": "CONFIRMED", "mitre_technique": "T1055"},
    ]
    coverage = build_attack_coverage(tool_calls, findings, completeness)
    by_tid = {r["technique_id"]: r for r in coverage["targets"]}
    coverage_cases = [
        (
            "T1014 finding is marked finding-level coverage",
            by_tid["T1014"].get("status"),
            "finding",
        ),
        (
            "T1055 preserves best finding confidence",
            by_tid["T1055"].get("finding_confidence"),
            "CONFIRMED",
        ),
        (
            "T1041 exfil remains a blind spot without network telemetry",
            by_tid["T1041"].get("status"),
            "blind_spot",
        ),
        (
            "covered_no_finding caveat uses limited-coverage wording",
            "limited coverage" in by_tid["T1003"].get("gap", ""),
            True,
        ),
    ]
    for label, actual, expected in coverage_cases:
        process_checks += 1
        ok = actual == expected
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] coverage: {label}")
        if not ok:
            print(f"         expected: {expected!r}")
            print(f"         actual  : {actual!r}")
            failures += 1

    # ----- Correlator refined findings drive final verdict input ------

    class FakeReasonClient:
        def __init__(self) -> None:
            self.pre = {
                "case_id": "case-corr",
                "finding_id": "f-corr",
                "tool_call_id": "tc-corr",
                "artifact_path": "Amcache.hve",
                "description": "Binary executed according to Amcache only.",
                "confidence": "CONFIRMED",
                "pool_origin": "A",
                "mitre_technique": None,
            }
            self.refined = [{**self.pre, "confidence": "INFERRED"}]

        def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
            if name == "detect_contradictions":
                return {"contradictions": []}
            if name == "judge_findings":
                return {"merged": [{"finding": self.pre}]}
            if name == "correlate_findings":
                return {
                    "refined": self.refined,
                    "outcomes": [
                        {
                            "finding_id": "f-corr",
                            "action": "downgraded",
                            "reason": "single artifact execution claim",
                        }
                    ],
                }
            raise AssertionError(f"unexpected tool call: {name}")

    fake_py = FakeReasonClient()
    inv = fea.Investigation("Security.evtx", unattended=True, with_report=False)
    inv.handle = {"id": "case-corr"}
    corr_merged, _, corr_kept, corr_downgraded = inv.reason(fake_py)
    corr_cases = [
        (
            "correlator refined confidence is returned",
            corr_merged[0].get("confidence"),
            "INFERRED",
        ),
        ("correlator downgraded count is surfaced", corr_downgraded, 1),
        (
            "downgraded non-severe finding no longer drives SUSPICIOUS",
            compute_verdict(corr_merged),
            "INDETERMINATE",
        ),
        ("correlator kept count remains zero", corr_kept, 0),
    ]
    for label, actual, expected in corr_cases:
        process_checks += 1
        ok = actual == expected
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] correlation: {label}")
        if not ok:
            print(f"         expected: {expected!r}")
            print(f"         actual  : {actual!r}")
            failures += 1

    # ----- Process-view divergence triggers psxview policy -----------
    process_divergence_cases = [
        (
            "count divergence triggers psxview",
            process_sets_diverge(
                [{"pid": 4, "image_name": "System"}],
                [
                    {"pid": 4, "image_name": "System"},
                    {"pid": 100, "image_name": "smss.exe"},
                ],
                1,
                2,
            )[0],
            True,
        ),
        (
            "same-count different PID sets trigger psxview",
            process_sets_diverge(
                [
                    {"pid": 4, "image_name": "System"},
                    {"pid": 100, "image_name": "smss.exe"},
                ],
                [
                    {"pid": 4, "image_name": "System"},
                    {"pid": 200, "image_name": "smss.exe"},
                ],
                2,
                2,
            )[0],
            True,
        ),
        (
            "same-count different process identities trigger psxview",
            process_sets_diverge(
                [{"pid": 100, "image_name": "svchost.exe"}],
                [{"pid": 100, "image_name": "evil.exe"}],
                1,
                1,
            )[0],
            True,
        ),
        (
            "matching process views skip psxview",
            process_sets_diverge(
                [{"pid": 4, "image_name": "System"}],
                [{"pid": 4, "image_name": "System"}],
                1,
                1,
            )[0],
            False,
        ),
    ]
    for label, actual, expected in process_divergence_cases:
        process_checks += 1
        ok = actual == expected
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] psxview: {label}")
        if not ok:
            print(f"         expected: {expected!r}")
            print(f"         actual  : {actual!r}")
            failures += 1

    actions = build_next_actions(findings, coverage, completeness, [])
    action_cases = [
        ("next actions are capped at five", len(actions), 5),
        (
            "DKOM follow-up is prioritized first",
            actions[0].get("based_on"),
            ["T1014"],
        ),
    ]
    for label, actual, expected in action_cases:
        process_checks += 1
        ok = actual == expected
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] action: {label}")
        if not ok:
            print(f"         expected: {expected!r}")
            print(f"         actual  : {actual!r}")
            failures += 1

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "timeline.csv"
        write_timeline_csv(
            [
                {
                    "ts": "2026-05-04T00:00:00Z",
                    "source": "vol_psscan",
                    "artifact_class": "memory",
                    "description": "process start",
                    "tool_call_id": "tc-003",
                    "details": {"pid": 4},
                }
            ],
            csv_path,
        )
        text = csv_path.read_text(encoding="utf-8")
    process_checks += 1
    ok = "details_json" in text and "tc-003" in text and '""pid"":4' in text
    marker = "OK  " if ok else "FAIL"
    print(
        "  [{marker}] timeline: CSV export includes details_json".format(marker=marker)
    )
    if not ok:
        print(f"         csv text: {text!r}")
        failures += 1

    print()
    print("=" * 60)
    total = len(cases) + len(et_cases) + len(evtx_cases) + process_checks
    if failures == 0:
        print(f"OK - all {total} verdict + evidence/process cases pass.")
        print("=" * 60)
        return 0
    print(f"FAIL - {failures} of {total} cases failed.")
    print("If the change is intentional, update both:")
    print("  - scripts/find_evil_auto.py (verdict / evidence / process helpers)")
    print("  - scripts/verdict-policy-smoke.py expected outputs")
    print("  - docs/verdict-semantics.md per-verdict trigger list")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
