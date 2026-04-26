#!/usr/bin/env bash
# scripts/run-all-smokes.sh — run every smoke that L1 runs, outside docker.
#
# A developer iterating locally on the typed MCP surface, find-evil-auto's
# verdict policy, fleet_correlate's filter logic, or the demo script's
# timing should not have to wait for a docker compose build to find out
# they broke something. This script runs the same 5 smokes that
# docker/l1-compose.yml runs, in the same order, with a one-line
# status per smoke and a final tally.
#
# Usage:
#   bash scripts/run-all-smokes.sh
#
# Exits 0 if every smoke passed; non-zero if any failed.
#
# Pre-flight: requires `cargo build --release -p findevil-mcp` (the Rust
# smoke spawns target/release/findevil-mcp) and `uv sync` in
# services/agent_mcp (the agent_mcp smoke spawns the Python MCP server).

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

# Skip ANSI color codes when stdout isn't a TTY (CI logs, file
# redirects, Windows cmd.exe without ENABLE_VIRTUAL_TERMINAL_
# PROCESSING). Colors are nice-to-have for interactive terminals;
# raw escape sequences in a CI log file are noise.
if [ -t 1 ]; then
    c_red=$'\033[0;31m'
    c_grn=$'\033[0;32m'
    c_yel=$'\033[0;33m'
    c_blu=$'\033[0;34m'
    c_off=$'\033[0m'
else
    c_red=""
    c_grn=""
    c_yel=""
    c_blu=""
    c_off=""
fi

passed=0
failed=0
skipped=0

run_smoke() {
    local label="$1"
    local cmd="$2"
    local prereq="${3:-}"
    echo
    echo "${c_blu}━━━ ${label} ━━━${c_off}"

    if [ -n "${prereq}" ] && ! eval "${prereq}" >/dev/null 2>&1; then
        echo "${c_yel}  SKIP: prerequisite not met (${prereq})${c_off}"
        skipped=$((skipped + 1))
        return 0
    fi

    if eval "${cmd}"; then
        echo "${c_grn}  ✓ ${label} passed${c_off}"
        passed=$((passed + 1))
    else
        echo "${c_red}  ✗ ${label} FAILED${c_off}"
        failed=$((failed + 1))
    fi
}

echo "=========================================="
echo "Find Evil! - run all L1 smokes locally"
echo "=========================================="

# 1. Rust MCP server end-to-end.
run_smoke \
    "rust-mcp-smoke (12-tool dispatch + error paths)" \
    "python3 scripts/rust-mcp-smoke.py" \
    "[ -x target/release/findevil-mcp ] || [ -x target/release/findevil-mcp.exe ]"

# 2. Python agent_mcp end-to-end (synthetic).
run_smoke \
    "agent-mcp-smoke (synthetic Findings + crypto chain)" \
    "uv run --directory services/agent_mcp python ../../scripts/agent-mcp-smoke.py" \
    "[ -d services/agent_mcp ]"

# 3. compute_verdict + detect_evidence_type policy lock.
run_smoke \
    "verdict-policy-smoke (compute_verdict + detect_evidence_type)" \
    "python3 scripts/verdict-policy-smoke.py"

# 4. fleet_correlate pure-function lock.
run_smoke \
    "fleet-policy-smoke (7 functions across normalize/filter/cluster/density/uniqueness/aggregate)" \
    "python3 scripts/fleet-policy-smoke.py"

# 5. demo-script-a2.md structural lock.
run_smoke \
    "demo-script-smoke (9 contiguous beats summing to 5:00)" \
    "python3 scripts/demo-script-smoke.py" \
    "[ -f docs/demo-script-a2.md ]"

# 6. Launcher invariants lock.
run_smoke \
    "launcher-smoke (bash -n + claude binary + no positional .)" \
    "python3 scripts/launcher-smoke.py"

# 7. Spec/code divergence lock — asserts no doc has re-introduced a bad-half pattern.
run_smoke \
    "divergence-smoke (5 active divergences from CLAUDE.md downstream-clean)" \
    "python3 scripts/divergence-smoke.py"

total=$((passed + failed + skipped))
echo
echo "=========================================="
if [ "${failed}" -eq 0 ]; then
    echo "${c_grn}OK${c_off} - ${passed} passed, ${skipped} skipped, 0 failed (of ${total})"
    echo "=========================================="
    exit 0
fi
echo "${c_red}FAIL${c_off} - ${passed} passed, ${skipped} skipped, ${failed} failed (of ${total})"
echo "Same smoke set runs in CI via docker/l1-compose.yml. If a smoke"
echo "fails locally and passes in CI, check toolchain versions:"
echo "  cargo build --release -p findevil-mcp  (Rust 1.88 per rust-toolchain.toml)"
echo "  uv sync --extra dev (Python 3.11 in services/agent_mcp)"
echo "=========================================="
exit 1
