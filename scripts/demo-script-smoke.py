#!/usr/bin/env python3
"""demo-script-smoke — lock in the docs/demo-script-a2.md structure.

The Devpost video has a hard 5:00 cap. The demo script encodes the
plan as 9 beats with explicit start/end timestamps and per-beat
length. A future contributor adjusting one beat's length without
adjusting adjacent ones produces a script that overruns the cap or
has gaps — both of which the recorder doesn't catch until they're
already mid-take.

This smoke parses the "## Beat map" markdown table and asserts:

  - Exactly 9 beats (matches the script's 9 numbered sections).
  - Each beat has well-formed `H:MM-H:MM` (or M:SS-M:SS) timestamps
    in the time column AND a length column matching end-start.
  - Beat 1 starts at 0:00.
  - Beat 9 ends at 5:00.
  - Beats are contiguous (each beat starts where the previous one
    ended).
  - Total length of the lengths column sums to 5:00 (300 seconds).

Cheap (~50ms). If the script's timing breaks, this fails the L1
build with the exact beat number and the discrepancy in seconds.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "docs" / "demo-script-a2.md"


def to_seconds(timestr: str) -> int:
    """Parse 'M:SS' (e.g. '4:50') or 'H:MM:SS' to integer seconds."""
    parts = [int(p) for p in timestr.strip().split(":")]
    if len(parts) == 2:
        m, s = parts
        return m * 60 + s
    if len(parts) == 3:
        h, m, s = parts
        return h * 3600 + m * 60 + s
    raise ValueError(f"unparseable timestamp: {timestr!r}")


def main() -> int:
    print("=" * 60)
    print("Find Evil! - demo-script-a2.md structural smoke")
    print("=" * 60)

    if not DEMO.is_file():
        print(f"FAIL - demo script missing: {DEMO}")
        return 1

    text = DEMO.read_text(encoding="utf-8")

    # Find the Beat map table — it has rows like:
    #   | 1 | 0:00–0:25 | 0:25   | Cold open ... |
    # Em-dash is U+2013 ("–") between start and end.
    beat_row = re.compile(
        r"^\|\s*(\d+)\s*\|\s*(\d+:\d+)[–-]+(\d+:\d+)\s*\|\s*(\d+:\d+)\s*\|"
    )
    beats: list[tuple[int, int, int, int]] = []
    for line in text.splitlines():
        m = beat_row.match(line)
        if m:
            n = int(m.group(1))
            start = to_seconds(m.group(2))
            end = to_seconds(m.group(3))
            length = to_seconds(m.group(4))
            beats.append((n, start, end, length))

    failures = 0

    if len(beats) != 9:
        print(f"  [FAIL] expected 9 beats, found {len(beats)}")
        failures += 1
    else:
        print("  [OK  ] 9 beats parsed from beat map table")

    # Beat numbers must be 1..9 in order.
    for i, (n, _, _, _) in enumerate(beats, 1):
        if n != i:
            print(f"  [FAIL] beat #{i} numbered {n}")
            failures += 1

    if beats:
        # Beat 1 starts at 0:00.
        if beats[0][1] != 0:
            print(f"  [FAIL] beat 1 starts at {beats[0][1]}s (expected 0)")
            failures += 1
        else:
            print("  [OK  ] beat 1 starts at 0:00")

        # Beat 9 ends at 5:00 (300s).
        if beats[-1][2] != 300:
            print(f"  [FAIL] beat 9 ends at {beats[-1][2]}s (expected 300)")
            failures += 1
        else:
            print("  [OK  ] beat 9 ends at 5:00 (Devpost cap)")

        # Beats are contiguous: each beat starts where the previous ended.
        for i in range(1, len(beats)):
            prev_end = beats[i - 1][2]
            cur_start = beats[i][1]
            if cur_start != prev_end:
                print(
                    f"  [FAIL] beat {beats[i][0]} starts at {cur_start}s "
                    f"but beat {beats[i - 1][0]} ended at {prev_end}s "
                    f"(gap or overlap)"
                )
                failures += 1
        if failures == 0 or all(
            beats[i][1] == beats[i - 1][2] for i in range(1, len(beats))
        ):
            print("  [OK  ] beats are contiguous (no gaps or overlaps)")

        # Each beat's length column matches end - start.
        for n, start, end, length in beats:
            calc = end - start
            if calc != length:
                print(
                    f"  [FAIL] beat {n} length column says {length}s "
                    f"but {start}->{end} = {calc}s"
                )
                failures += 1

        # Sum of lengths = 300.
        total = sum(length for _, _, _, length in beats)
        if total != 300:
            print(f"  [FAIL] sum of beat lengths = {total}s (expected 300)")
            failures += 1
        else:
            print("  [OK  ] beat lengths sum to 300s (5:00 flat)")

    print()
    print("=" * 60)
    if failures == 0:
        print(
            f"OK - demo script structural smoke passes ({len(beats)} beats verified)."
        )
        print("=" * 60)
        return 0
    print(f"FAIL - {failures} structural issue(s) in docs/demo-script-a2.md.")
    print("If the change is intentional, ensure:")
    print("  - 9 beats exist with consecutive numbers 1-9")
    print("  - first beat starts at 0:00, last ends at 5:00")
    print("  - each beat's length = end - start")
    print("  - beats are contiguous (no gaps or overlaps)")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
