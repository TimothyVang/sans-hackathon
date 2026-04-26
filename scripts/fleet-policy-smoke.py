#!/usr/bin/env python3
"""fleet-policy-smoke — lock in fleet_correlate's filter + aggregation logic.

`docs/false-positives.md` "Fleet cross-host correlation" entry
documents the COMMON_WIN_PROCS filter as the load-bearing
mitigation against enterprise-AV/system-binary false positives.
The 14-character Volatility-truncation matcher (commit `ba038c6`)
is the second-load-bearing layer — without it, "VGAuthService."
(truncated by Volatility's 16-byte ImageFileName field) would not
match the canonical "VGAuthService.exe" entry. Same hazard as the
verdict policy: a future contributor could change either piece
and the docs would silently disagree.

This smoke locks in five behaviors:

  1. `normalize_image_name` does the right thing (lowercase + trim +
     14-char truncation).
  2. Truncated and untruncated forms compare equal under the
     normalizer.
  3. `cross_host_processes` end-to-end: filter applies to canonical
     and Volatility-truncated forms, suspicious binaries on ≥2 hosts
     surface, single-host names are excluded by the threshold.
  4. `temporal_clusters` window detection: multi-host process
     creations within 60s cluster, single-host bursts and
     past-window events stay isolated. Anchors the SRL-2018
     "Autorunsc on 6 hosts at the exact same second" pattern that
     headlines `FLEET_REPORT.pdf`.
  5. `selfscore_aggregate` produces a stable shape against a
     small synthetic fleet of 3 hosts × 6 selfscore records.

Loaded via importlib like verdict-policy-smoke.py, so the test
runs against the actual shipped fleet_correlate.py without
duplicating the policy.

Exit code: 0 on full pass, 1 on first assertion failure.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent


def load_fleet_correlate():
    spec = importlib.util.spec_from_file_location(
        "fleet_correlate_under_test",
        REPO / "scripts" / "fleet_correlate.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not build spec for fleet_correlate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    fc = load_fleet_correlate()
    print("=" * 60)
    print("Find Evil! - fleet policy smoke")
    print("=" * 60)

    failures = 0

    # ---- normalize_image_name behavior -----------------------------------
    norm = fc.normalize_image_name
    cases_norm: list[tuple[str, str, str]] = [
        ("lowercase + trim + truncate to 14", "VGAuthService.exe", "vgauthservice."),
        ("already-lowercase passthrough", "csrss.exe", "csrss.exe"),
        ("strips leading/trailing whitespace", "  svchost.exe  ", "svchost.exe"),
        (
            "Volatility-style trailing dot truncation matches",
            "VGAuthService.",
            "vgauthservice.",
        ),
        ("longer-than-14 gets cut at 14", "ManagementAgentHost.exe", "managementagen"),
        ("empty string normalizes to empty", "", ""),
    ]
    for label, inp, expected in cases_norm:
        actual = norm(inp)
        ok = actual == expected
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] norm: {label}")
        if not ok:
            print(f"         input   : {inp!r}")
            print(f"         expected: {expected!r}")
            print(f"         actual  : {actual!r}")
            failures += 1

    # ---- COMMON_WIN_PROCS contains the filtered enterprise stack ---------
    must_be_filtered = [
        "vgauthservice.",  # truncated form Volatility emits
        "vgauthservice.exe",  # canonical
        "masvc.exe",
        "macmnsvc.exe",
        "mfemactl.exe",
        "firesvc.exe",
        "msdtc.exe",
        "memcompression",
        "userinit.exe",
        "tabtip.exe",
    ]
    for name in must_be_filtered:
        ok = norm(name) in fc._COMMON_TRUNCATED
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] _COMMON_TRUNCATED contains norm({name!r})")
        if not ok:
            failures += 1

    # ---- COMMON_WIN_PROCS deliberately does NOT contain Sysinternals -----
    must_not_be_filtered = [
        "autorunsc.exe",  # Sysinternals — cross-host runs ARE suspicious
        "psexec.exe",
        "procdump.exe",
        "rubyw.exe",  # genuinely unusual on enterprise Windows
        "cmd.exe",  # interactive shell — flag for analyst
        "powershell.exe",
    ]
    for name in must_not_be_filtered:
        ok = norm(name) not in fc._COMMON_TRUNCATED
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] _COMMON_TRUNCATED does NOT contain norm({name!r})")
        if not ok:
            failures += 1

    # ---- selfscore_aggregate against a synthetic 3-host fleet ------------
    synthetic = [
        {
            "_host": "h1",
            "_selfscores": [
                {"criterion": 1, "answer": "failures=0 corrections=0"},
                {"criterion": 5, "answer": "cited=2/2"},
            ],
        },
        {
            "_host": "h2",
            "_selfscores": [
                {"criterion": 1, "answer": "failures=0 corrections=0"},
                {"criterion": 5, "answer": "cited=3/3"},  # different from h1
            ],
        },
        {
            "_host": "h3",
            "_selfscores": [],  # no records
        },
    ]
    agg = fc.selfscore_aggregate(synthetic)

    # ---- cross_host_processes: end-to-end FP filter behavior -----------
    # Synthesize 3 hosts seeing a mix of:
    #   - Filtered binaries (svchost.exe, masvc.exe) on all hosts
    #   - Truncated-form filtered binary ("VGAuthService.") on all hosts
    #   - Suspicious binary (rubyw.exe) on 2 hosts -> should surface
    #   - Single-host name (legit-only.exe) -> should NOT surface
    #     (function only returns names appearing on ≥2 hosts)
    chp_synthetic = [
        {
            "_host": h,
            "_psscan": [
                {
                    "ImageFileName": "svchost.exe",
                    "PID": 100 + i,
                    "PPID": 4,
                    "CreateTime": "2024-01-01T00:00:00Z",
                },
                {
                    "ImageFileName": "masvc.exe",
                    "PID": 200 + i,
                    "PPID": 4,
                    "CreateTime": "2024-01-01T00:00:00Z",
                },
                {
                    "ImageFileName": "VGAuthService.",
                    "PID": 300 + i,
                    "PPID": 4,
                    "CreateTime": "2024-01-01T00:00:00Z",
                },
                {
                    "ImageFileName": "rubyw.exe" if h in ("h1", "h2") else "other.exe",
                    "PID": 400 + i,
                    "PPID": 1000,
                    "CreateTime": "2024-01-01T00:00:00Z",
                },
            ],
        }
        for i, h in enumerate(("h1", "h2", "h3"))
    ]
    # Add a single-host-only name so we verify the ≥2 threshold
    chp_synthetic[0]["_psscan"].append(
        {
            "ImageFileName": "legit-only.exe",
            "PID": 999,
            "PPID": 1,
            "CreateTime": "2024-01-01T00:00:00Z",
        }
    )

    chp = fc.cross_host_processes(chp_synthetic)
    chp_checks: list[tuple[str, Any, Any]] = [
        ("svchost.exe filtered (in COMMON_WIN_PROCS)", "svchost.exe" in chp, False),
        ("masvc.exe filtered (McAfee)", "masvc.exe" in chp, False),
        (
            "VGAuthService. filtered via 14-char truncation",
            "VGAuthService." in chp,
            False,
        ),
        ("rubyw.exe surfaces (uncommon, on 2 hosts)", "rubyw.exe" in chp, True),
        (
            "rubyw.exe has 2 distinct hosts",
            len({h["host"] for h in chp.get("rubyw.exe", [])}),
            2,
        ),
        (
            "legit-only.exe excluded (1 host only, threshold is 2)",
            "legit-only.exe" in chp,
            False,
        ),
        ("other.exe excluded (1 host only)", "other.exe" in chp, False),
    ]
    for label, actual, expected in chp_checks:
        ok = actual == expected
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] cross_host_processes: {label}")
        if not ok:
            print(f"         expected: {expected!r}")
            print(f"         actual  : {actual!r}")
            failures += 1

    # ---- temporal_clusters: multi-host within-window detection ---------
    # The headline fleet visual in FLEET_REPORT.pdf. Asserts:
    #   - Two hosts with creations within 60s -> one cluster
    #   - Same time but only one host -> no cluster (single-host
    #     bursts aren't lateral-movement signal)
    #   - Two events 90s apart -> two separate cluster boundaries
    #     (default window is 60s)
    tc_synthetic = [
        {
            "_host": "h1",
            "_psscan": [
                # The Autorunsc-on-multiple-hosts-same-second pattern from
                # the SRL-2018 fleet (cluster 1 in FLEET_REPORT.pdf):
                {
                    "ImageFileName": "Autorunsc.exe",
                    "PID": 100,
                    "CreateTime": "2018-08-15T17:10:32+00:00",
                },
                # An unrelated, much later event:
                {
                    "ImageFileName": "cmd.exe",
                    "PID": 200,
                    "CreateTime": "2018-08-15T17:15:00+00:00",
                },
            ],
        },
        {
            "_host": "h2",
            "_psscan": [
                # Same second as h1's Autorunsc — the lateral-movement
                # fingerprint. Should cluster with h1's record.
                {
                    "ImageFileName": "Autorunsc.exe",
                    "PID": 101,
                    "CreateTime": "2018-08-15T17:10:32+00:00",
                },
            ],
        },
        {
            "_host": "h3",
            "_psscan": [
                # 30 seconds after the h1+h2 cluster — should still
                # join because each pairwise gap is ≤ 60s.
                {
                    "ImageFileName": "powershell.exe",
                    "PID": 102,
                    "CreateTime": "2018-08-15T17:11:02+00:00",
                },
            ],
        },
        # h4 is 90s+ after h3 -> should NOT join any earlier cluster
        {
            "_host": "h4",
            "_psscan": [
                {
                    "ImageFileName": "isolated.exe",
                    "PID": 103,
                    "CreateTime": "2018-08-15T17:13:00+00:00",
                },
            ],
        },
    ]
    tc = fc.temporal_clusters(tc_synthetic)
    tc_checks: list[tuple[str, Any, Any]] = [
        # The h1+h2+h3 cluster forms (3 distinct hosts, all within 60s
        # pairwise). h4 is alone past the window so it doesn't form
        # its own cluster (need ≥2 hosts).
        ("exactly 1 multi-host cluster forms", len(tc), 1),
        ("cluster spans 3 distinct hosts", tc[0]["host_count"] if tc else 0, 3),
        (
            "h4 isolated event excluded (single host, past window)",
            "h4" in {ev["host"] for ev in (tc[0]["events"] if tc else [])},
            False,
        ),
    ]
    for label, actual, expected in tc_checks:
        ok = actual == expected
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] temporal_clusters: {label}")
        if not ok:
            print(f"         expected: {expected!r}")
            print(f"         actual  : {actual!r}")
            failures += 1

    sa_checks: list[tuple[str, Any, Any]] = [
        ("hosts_total counts everything", agg["hosts_total"], 3),
        ("hosts_with_selfscore counts non-empty", agg["hosts_with_selfscore"], 2),
        (
            "criterion 1 modal answer when all agree",
            agg["by_criterion"]["1"]["modal_answer"],
            "failures=0 corrections=0",
        ),
        (
            "criterion 1 modal_share equals host_count when unanimous",
            agg["by_criterion"]["1"]["modal_share"],
            agg["by_criterion"]["1"]["host_count"],
        ),
        (
            "criterion 1 distinct_answers=1 when unanimous",
            agg["by_criterion"]["1"]["distinct_answers"],
            1,
        ),
        (
            "criterion 5 distinct_answers=2 when h1 and h2 disagree",
            agg["by_criterion"]["5"]["distinct_answers"],
            2,
        ),
    ]
    for label, actual, expected in sa_checks:
        ok = actual == expected
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] selfscore_aggregate: {label}")
        if not ok:
            print(f"         expected: {expected!r}")
            print(f"         actual  : {actual!r}")
            failures += 1

    print()
    print("=" * 60)
    total = (
        len(cases_norm)
        + len(must_be_filtered)
        + len(must_not_be_filtered)
        + len(chp_checks)
        + len(tc_checks)
        + len(sa_checks)
    )
    if failures == 0:
        print(f"OK - all {total} fleet-policy assertions pass.")
        print("=" * 60)
        return 0
    print(f"FAIL - {failures} of {total} fleet-policy assertions failed.")
    print("If the change is intentional, update both:")
    print("  - scripts/fleet_correlate.py")
    print("  - scripts/fleet-policy-smoke.py expected outputs")
    print("  - docs/false-positives.md if filter coverage shifted")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
