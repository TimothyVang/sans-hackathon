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
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent


def load_compute_verdict():
    """Load Investigation.compute_verdict from scripts/find_evil_auto.py
    without spinning up the orchestrator's main()."""
    spec = importlib.util.spec_from_file_location(
        "find_evil_auto_under_test",
        REPO / "scripts" / "find_evil_auto.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not build spec for find_evil_auto.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # `compute_verdict` is an instance method on Investigation but
    # only reads `self` for nothing — it's pure on `merged`. We can
    # call it as an unbound method by passing None for self. Python
    # doesn't care.
    def call(merged: list[dict[str, Any]]) -> str:
        return mod.Investigation.compute_verdict(None, merged)

    return call


def case(label: str, merged: list[dict[str, Any]], expected: str) -> tuple[str, bool]:
    return (label, merged, expected)


def main() -> int:
    compute_verdict = load_compute_verdict()
    print("=" * 60)
    print("Find Evil! — verdict policy smoke (compute_verdict)")
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
        print(f"  [{marker}] {label}")
        if not ok:
            print(f"         expected: {expected!r}")
            print(f"         actual  : {actual!r}")
            failures += 1

    print()
    print("=" * 60)
    if failures == 0:
        print(f"OK - all {len(cases)} compute_verdict cases pass.")
        print("=" * 60)
        return 0
    print(f"FAIL - {failures} of {len(cases)} compute_verdict cases failed.")
    print("If the change is intentional, update both:")
    print("  - scripts/find_evil_auto.py::compute_verdict")
    print("  - scripts/verdict-policy-smoke.py expected outputs")
    print("  - docs/verdict-semantics.md per-verdict trigger list")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
