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

This smoke locks in three behaviors:

  1. `normalize_image_name` does the right thing (lowercase + trim +
     14-char truncation).
  2. Truncated and untruncated forms compare equal under the
     normalizer.
  3. `selfscore_aggregate` produces a stable shape against a
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
