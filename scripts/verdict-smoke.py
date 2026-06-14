#!/usr/bin/env python3
"""Smoke test: scripts/verdict — the one-command entry point.

Verifies via bash -n (syntax) and grep-asserts that the single workflow wires
each stage (preflight → build → investigate → dashboard). --dry-run is
exercised without running any investigation.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "verdict"


def test_script_exists_and_executable() -> None:
    assert SCRIPT.exists(), f"Missing: {SCRIPT}"


def test_bash_syntax_clean() -> None:
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, f"bash -n failed: {result.stderr}"


def test_chains_doctor() -> None:
    assert "doctor.sh" in SCRIPT.read_text(
        encoding="utf-8"
    ), "verdict does not reference doctor.sh"


def test_chains_build() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert (
        "cargo build" in text or "findevil-mcp" in text
    ), "verdict does not reference cargo build / findevil-mcp"


def test_chains_engine() -> None:
    assert "find_evil_auto" in SCRIPT.read_text(
        encoding="utf-8"
    ), "verdict does not chain the find_evil_auto engine"


def test_has_sift_and_dashboard_flags() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--sift" in text, "verdict missing --sift flag"
    assert "--no-dashboard" in text, "verdict missing --no-dashboard flag"


def test_sift_staging_rejects_unsafe_remote_names() -> None:
    test_sift_staging_sanitizer_selftest()
    text = SCRIPT.read_text(encoding="utf-8")
    assert "safe_guest_basename" in text, "verdict lacks SIFT basename sanitizer"
    assert (
        "unsafe evidence filename for --sift staging" in text
    ), "verdict does not reject shell-unsafe SIFT evidence filenames"
    assert (
        "unsafe SIFT guest evidence dir" in text
    ), "verdict does not reject shell-unsafe SIFT guest evidence directories"


def test_n8n_status_wording_does_not_overclaim_actions() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert (
        "n8n fired" not in text
    ), "verdict overclaims n8n reachability as fired action"
    assert (
        "n8n reachable; automation sidecar recorded" in text
    ), "verdict should distinguish n8n reachability from action creation"


def test_sift_staging_sanitizer_selftest() -> None:
    env = {**os.environ, "FINDEVIL_VERDICT_SELFTEST": "sift-sanitizers"}
    result = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, timeout=10, env=env
    )
    assert (
        result.returncode == 0
    ), f"SIFT sanitizer selftest failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    assert (
        "sift sanitizer selftest OK" in result.stdout
    ), f"SIFT sanitizer selftest did not confirm success: {result.stdout!r}"


def test_sift_mounted_evidence_selftest() -> None:
    env = {**os.environ, "FINDEVIL_VERDICT_SELFTEST": "sift-mounted-evidence"}
    result = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, timeout=10, env=env
    )
    assert (
        result.returncode == 0
    ), f"SIFT mounted evidence selftest failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    assert (
        "sift mounted evidence selftest OK" in result.stdout
    ), f"SIFT mounted evidence selftest did not confirm success: {result.stdout!r}"


def test_sift_mounted_evidence_env_contract_present() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert (
        "FINDEVIL_SIFT_HOST_EVIDENCE_ROOT" in text
    ), "verdict should expose a host evidence root env for SIFT mount mapping"
    assert (
        "FINDEVIL_SIFT_GUEST_EVIDENCE_ROOT" in text
    ), "verdict should expose a guest evidence root env for SIFT mount mapping"
    assert (
        "map_sift_mounted_evidence" in text
    ), "verdict should map host evidence paths to read-only guest mount paths"


def test_sift_mapped_paths_verify_guest_and_skip_scp() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    mapped_branch = 'mounted_remote="$(map_sift_mounted_evidence "${EVIDENCE}" 2>&1)"'
    assert (
        "verify_sift_guest_evidence_readable" in text
    ), "verdict should verify mapped guest evidence paths before running tools"
    assert (
        mapped_branch in text
    ), "verdict should try mount mapping in the SIFT host-path branch"
    assert (
        'case "${mounted_status}" in' in text
    ), "verdict should handle mounted evidence mapping statuses in the parent shell"
    assert (
        'verify_sift_guest_evidence_readable "${mounted_remote}" 1' in text
    ), "mapped SIFT evidence paths should require read-only guest mount verification"
    assert (
        'verify_sift_guest_evidence_identity "${EVIDENCE}" "${mounted_remote}"' in text
    ), "mapped SIFT evidence paths should verify guest identity before skipping SCP"
    assert (
        "using mounted SIFT evidence" in text
    ), "verdict should log when it uses a mounted SIFT evidence path"
    assert text.index(mapped_branch) < text.index(
        "staging ${rbase} into the VM"
    ), "verdict should try mount mapping before scp staging"


def test_sift_directory_identity_uses_file_manifest_not_directory_bytes() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    identity_fn = text.split("verify_sift_guest_evidence_identity() {", 1)[1].split(
        "\n}", 1
    )[0]
    local_helper = text.split("sift_local_evidence_identity() {", 1)[1].split("\n}", 1)[
        0
    ]
    remote_helper = text.split("sift_remote_evidence_identity() {", 1)[1].split(
        "\n}", 1
    )[0]
    assert (
        "sift_local_evidence_identity" in text
    ), "verdict should compute host identity through a dedicated file manifest helper"
    assert (
        "sift_remote_evidence_identity" in text
    ), "verdict should compute guest identity through the same file manifest semantics"
    assert (
        "du -sb" not in identity_fn
    ), "directory identity should not depend on filesystem-specific directory entry sizes"
    assert (
        "_evidence_size" not in identity_fn
    ), "directory identity should not reuse debounce-size totals for evidence comparison"
    for helper in (local_helper, remote_helper):
        assert (
            "du -sb" not in helper
        ), "manifest helpers should not use raw directory allocation size"
        assert "hash_file(" in helper, "manifest helpers should hash file contents"
        assert (
            "onerror=fail_walk" in helper
        ), "manifest helpers should fail on traversal errors"
        assert (
            "digest.update" in helper
        ), "manifest helpers should hash relative path/size entries"
        assert (
            "relative_to(path).as_posix()" in helper
        ), "manifest helpers should use relative paths, not absolute host or guest paths"
        assert "lstat()" in helper, "manifest helpers should avoid following symlinks"
        assert "S_ISLNK" in helper, "manifest helpers should reject symlinks"


def test_sift_fallback_staging_does_not_reuse_size_only_remote_files() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    fallback_branch = text.split("1)\n      if ! host_identity_output=", 1)[1].split(
        '      EVIDENCE="${remote}"', 1
    )[0]
    assert (
        "evidence already staged" not in fallback_branch
    ), "SIFT fallback staging must not skip SCP based on an existing remote basename"
    assert (
        "rsize" not in fallback_branch
    ), "SIFT fallback staging must not compare only remote and host byte counts"
    assert (
        "mktemp -d" in fallback_branch
    ), "SIFT fallback staging should copy into a fresh guest staging directory"
    assert (
        ".verdict-staging" in fallback_branch
    ), "SIFT fallback staging should isolate copied evidence under a verdict staging prefix"
    assert (
        'sift_local_evidence_identity "${EVIDENCE}"' in fallback_branch
    ), "SIFT fallback staging should reject host evidence symlinks before scp"
    assert (
        'remote_identity_output="$(sift_remote_evidence_identity "${remote}")"'
        in fallback_branch
    ), "SIFT fallback staging should verify guest identity after scp"
    assert (
        '"${remote_identity_output}" == "${host_identity_output}"' in fallback_branch
    ), "SIFT fallback staging should compare staged guest identity to host identity"


def test_sift_direct_guest_paths_are_verified() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    guest_branch = "treating it as an in-VM path"
    assert guest_branch in text, "verdict should keep direct in-VM path support"
    assert (
        'verify_sift_guest_evidence_readable "${EVIDENCE}" 1' in text
    ), "direct in-VM SIFT evidence paths should require read-only guest mount verification"
    assert (
        'sift_remote_evidence_identity "${EVIDENCE}" >/dev/null' in text
    ), "direct in-VM SIFT directories should run nested symlink/non-regular validation"
    assert text.index(
        'verify_sift_guest_evidence_readable "${EVIDENCE}" 1'
    ) < text.index(
        guest_branch
    ), "verdict should verify direct in-VM paths before continuing"
    assert text.index(
        'sift_remote_evidence_identity "${EVIDENCE}" >/dev/null'
    ) < text.index(
        guest_branch
    ), "verdict should validate direct in-VM tree contents before continuing"


def test_dry_run_produces_no_investigation() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run"], capture_output=True, text=True, timeout=10
    )
    assert (
        result.returncode == 0
    ), f"--dry-run exited {result.returncode}: {result.stderr}"
    combined = result.stdout + result.stderr
    assert (
        "DRY-RUN" in combined
    ), f"--dry-run did not emit DRY-RUN markers: {combined[:300]}"
    assert "4/4" in combined, "verdict --dry-run did not reach the final stage (4/4)"


def test_dry_run_with_skip_build() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--skip-build"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"--skip-build failed: {result.stderr}"


def test_run_summary_rejects_evidence_contamination() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp) / "evidence"
        evidence_dir.mkdir()
        evidence = evidence_dir / "sample.evtx"
        evidence.write_text("sample", encoding="utf-8")
        result = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                str(evidence),
                "--run-summary",
                str(evidence_dir / "summary.json"),
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    assert result.returncode != 0, "verdict should reject run summaries inside evidence"
    assert "--run-summary" in result.stderr, result.stderr
    assert "evidence" in result.stderr, result.stderr


def main() -> int:
    tests = [
        ("script_exists_and_executable", test_script_exists_and_executable),
        ("bash_syntax_clean", test_bash_syntax_clean),
        ("chains_doctor", test_chains_doctor),
        ("chains_build", test_chains_build),
        ("chains_engine", test_chains_engine),
        ("has_sift_and_dashboard_flags", test_has_sift_and_dashboard_flags),
        (
            "sift_staging_rejects_unsafe_remote_names",
            test_sift_staging_rejects_unsafe_remote_names,
        ),
        (
            "n8n_status_wording_does_not_overclaim_actions",
            test_n8n_status_wording_does_not_overclaim_actions,
        ),
        ("sift_mounted_evidence_selftest", test_sift_mounted_evidence_selftest),
        (
            "sift_mounted_evidence_env_contract_present",
            test_sift_mounted_evidence_env_contract_present,
        ),
        (
            "sift_mapped_paths_verify_guest_and_skip_scp",
            test_sift_mapped_paths_verify_guest_and_skip_scp,
        ),
        (
            "sift_directory_identity_uses_file_manifest_not_directory_bytes",
            test_sift_directory_identity_uses_file_manifest_not_directory_bytes,
        ),
        (
            "sift_fallback_staging_does_not_reuse_size_only_remote_files",
            test_sift_fallback_staging_does_not_reuse_size_only_remote_files,
        ),
        (
            "sift_direct_guest_paths_are_verified",
            test_sift_direct_guest_paths_are_verified,
        ),
        ("dry_run_produces_no_investigation", test_dry_run_produces_no_investigation),
        ("dry_run_with_skip_build", test_dry_run_with_skip_build),
        (
            "run_summary_rejects_evidence_contamination",
            test_run_summary_rejects_evidence_contamination,
        ),
    ]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {name}: {exc}")
            failed += 1
    print(f"\nverdict-smoke: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
