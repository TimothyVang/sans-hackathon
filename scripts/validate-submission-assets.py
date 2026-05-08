#!/usr/bin/env python3
"""Validate Devpost/release artifacts for final submission.

Strict validation is the default. Smoke packages may be generated for workflow
rehearsal, but final ``v-submit`` assets must pass these checks with no stubs,
placeholders, or header-only benchmark files.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import io
import re
from pathlib import Path
from urllib.parse import urlparse
import zipfile

REQUIRED_ZIP_FILES = {
    "README-submission.md",
    "benchmark-results.csv",
    "demo-video-link.txt",
    "LICENSE",
    "report.html",
}

PLACEHOLDER_PATTERNS = (
    "placeholder",
    "stub",
    "pre-release",
    "pre-week",
    "pending-record",
    "<your",
    "<id>",
    "todo",
    "changeme",
)


@dataclass
class CheckResult:
    ok: bool
    message: str


def is_placeholder_text(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in PLACEHOLDER_PATTERNS)


def validate_demo_url(url: str | None) -> CheckResult:
    if not url:
        return CheckResult(False, "DEMO_VIDEO_URL is empty")
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return CheckResult(False, f"demo URL is not an absolute http(s) URL: {url!r}")
    if is_placeholder_text(url) or parsed.netloc in {
        "example.com",
        "example.invalid",
        "localhost",
    }:
        return CheckResult(False, f"demo URL looks like a placeholder: {url!r}")
    return CheckResult(True, "demo URL is real-looking")


def parse_positive_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(str(value).strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def validate_benchmark(path: Path) -> CheckResult:
    if not path.is_file():
        return CheckResult(False, f"benchmark CSV missing: {path}")
    rows = read_csv_rows(path)
    if not rows:
        return CheckResult(False, "benchmark CSV has no data rows")
    if "fixture" not in rows[0] or "findings_matched" not in rows[0]:
        return CheckResult(
            False, "benchmark CSV missing fixture/findings_matched columns"
        )
    for row in rows:
        if row_is_positive_nist(row):
            return CheckResult(
                True,
                "benchmark CSV contains nist-hacking-case with findings_matched > 0",
            )
    return CheckResult(
        False, "benchmark CSV lacks nist-hacking-case row with findings_matched > 0"
    )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            with path.open(newline="", encoding=encoding) as fh:
                return list(csv.DictReader(fh))
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return []


def validate_report(path: Path) -> CheckResult:
    if not path.is_file():
        return CheckResult(False, f"report.html missing: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) < 1500:
        return CheckResult(False, "report.html is too small to be substantive")
    lowered = text.lower()
    required = (
        "<html",
        "</html>",
        "find evil",
        "verdict card",
        "cryptographic attestation",
    )
    missing = [token for token in required if token not in lowered]
    if missing:
        return CheckResult(
            False, f"report.html missing required marker(s): {', '.join(missing)}"
        )
    if is_placeholder_text(text):
        return CheckResult(False, "report.html contains placeholder/stub text")
    return CheckResult(True, "report.html is substantive and offline-looking")


def validate_stage_dir(path: Path) -> CheckResult:
    missing = sorted(name for name in REQUIRED_ZIP_FILES if not (path / name).is_file())
    if missing:
        return CheckResult(
            False, f"stage dir missing required file(s): {', '.join(missing)}"
        )
    readme = path / "README-submission.md"
    if re.search(
        r"\$\{[A-Z_]+\}", readme.read_text(encoding="utf-8", errors="replace")
    ):
        return CheckResult(
            False, "README-submission.md contains unsubstituted ${...} placeholder"
        )
    return CheckResult(True, "stage dir contains required files")


def validate_zip(path: Path) -> CheckResult:
    if not path.is_file():
        return CheckResult(False, f"submission zip missing: {path}")
    with zipfile.ZipFile(path) as zf:
        names = {name.rstrip("/") for name in zf.namelist()}
        missing = sorted(REQUIRED_ZIP_FILES - names)
        if missing:
            return CheckResult(
                False, f"zip missing required file(s): {', '.join(missing)}"
            )
        demo_url = (
            zf.read("demo-video-link.txt").decode("utf-8", errors="replace").strip()
        )
        demo_result = validate_demo_url(demo_url)
        if not demo_result.ok:
            return CheckResult(
                False, f"zip demo-video-link.txt invalid: {demo_result.message}"
            )
        with zf.open("benchmark-results.csv") as fh:
            rows = list(csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig")))
        if not rows:
            return CheckResult(False, "zip benchmark-results.csv has no data rows")
        if not any(row_is_positive_nist(row) for row in rows):
            return CheckResult(
                False, "zip benchmark-results.csv lacks positive nist-hacking-case row"
            )
        report = zf.read("report.html").decode("utf-8", errors="replace")
        if is_placeholder_text(report) or "verdict card" not in report.lower():
            return CheckResult(
                False, "zip report.html is placeholder or lacks verdict card marker"
            )
    return CheckResult(True, "submission zip contains required non-placeholder assets")


def row_is_positive_nist(row: dict[str, str]) -> bool:
    source_name = Path(row.get("source_file") or "").name
    fixture = row.get("fixture") or ""
    is_nist = (
        fixture == "nist-hacking-case"
        or source_name == "nist-hacking-case-verdict.json"
    )
    return is_nist and bool(parse_positive_int(row.get("findings_matched")))


def report_result(name: str, result: CheckResult) -> bool:
    marker = "PASS" if result.ok else "FAIL"
    print(f"[{marker}] {name}: {result.message}")
    return result.ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate final submission artifacts")
    parser.add_argument("--demo-url", help="demo video URL to validate")
    parser.add_argument("--benchmark", type=Path, help="benchmark-results.csv path")
    parser.add_argument("--report", type=Path, help="report.html path")
    parser.add_argument("--stage-dir", type=Path, help="package staging directory")
    parser.add_argument(
        "--zip", dest="zip_path", type=Path, help="find-evil-submission.zip path"
    )
    args = parser.parse_args()

    checks: list[tuple[str, CheckResult]] = []
    if args.demo_url is not None:
        checks.append(("demo-url", validate_demo_url(args.demo_url)))
    if args.benchmark is not None:
        checks.append(("benchmark", validate_benchmark(args.benchmark)))
    if args.report is not None:
        checks.append(("report", validate_report(args.report)))
    if args.stage_dir is not None:
        checks.append(("stage-dir", validate_stage_dir(args.stage_dir)))
    if args.zip_path is not None:
        checks.append(("zip", validate_zip(args.zip_path)))
    if not checks:
        parser.error("provide at least one artifact to validate")

    ok = True
    for name, result in checks:
        ok = report_result(name, result) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
