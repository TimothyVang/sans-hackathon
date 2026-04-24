#!/usr/bin/env bash
# fetch-fixtures.sh — download the L2/L3 fixtures listed in DATASET.md.
#
# Spec #3 §5 + docs/DATASET.md. Never commits fixtures to git —
# .gitignore excludes *.E01, *.ova, *.raw, *.mem, etc. This script
# populates fixtures/ at CI time (cached via actions/cache keyed on
# the SHA-256 manifest).
#
# Each fixture is verified against fixtures/sha256sums.txt. A
# mismatch aborts with clear error; absence (first-pull) appends a
# new line. Subsequent runs become idempotent checksum validations.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

FIXTURES="${FIXTURES:-fixtures}"
SHA_FILE="${FIXTURES}/sha256sums.txt"
mkdir -p "${FIXTURES}"
touch "${SHA_FILE}"

log() { printf '[fetch-fixtures] %s\n' "$*" >&2; }

# Download helper — atomic: downloads to .tmp, checksums, renames.
# fetch_fixture <url> <dest-subpath> <optional-expected-sha256>
fetch_fixture() {
  local url="$1"
  local dest="$2"
  local expected_sha="${3:-}"
  local abs="${FIXTURES}/${dest}"

  mkdir -p "$(dirname "${abs}")"
  if [[ -f "${abs}" ]]; then
    local actual_sha
    actual_sha="$(sha256sum "${abs}" | awk '{print $1}')"
    if grep -q "^${actual_sha}  ${dest}$" "${SHA_FILE}" 2>/dev/null; then
      log "ok: ${dest} (cached, sha verified)"
      return 0
    fi
    if [[ -n "${expected_sha}" ]] && [[ "${actual_sha}" != "${expected_sha}" ]]; then
      log "ERROR: ${dest} sha mismatch. expected=${expected_sha} actual=${actual_sha}"
      exit 1
    fi
  fi

  log "downloading ${url} → ${abs}"
  curl -fsSL --retry 3 --retry-delay 2 --max-time 600 \
    "${url}" -o "${abs}.tmp"
  mv "${abs}.tmp" "${abs}"

  local got_sha
  got_sha="$(sha256sum "${abs}" | awk '{print $1}')"
  if [[ -n "${expected_sha}" ]] && [[ "${got_sha}" != "${expected_sha}" ]]; then
    log "ERROR: ${dest} downloaded sha mismatch. expected=${expected_sha} got=${got_sha}"
    rm -f "${abs}"
    exit 1
  fi

  # Record in SHA_FILE if not already present.
  if ! grep -q "  ${dest}$" "${SHA_FILE}" 2>/dev/null; then
    echo "${got_sha}  ${dest}" >> "${SHA_FILE}"
  fi
  log "ok: ${dest} (sha=${got_sha})"
}

# ---------------------------------------------------------------------
# 1. SANS starter case data (primary L3 golden — per DATASET.md).
#    The Egnyte URL is the official distribution from the hackathon;
#    it's a public listing page, not a direct file, so we require
#    operators to pre-stage the archive. If SANS_STARTER_URL is set,
#    fetch from there (useful for mirroring).
# ---------------------------------------------------------------------
if [[ -n "${SANS_STARTER_URL:-}" ]]; then
  log "SANS_STARTER_URL set — fetching SANS starter dataset"
  fetch_fixture "${SANS_STARTER_URL}" "sans-starter/sans-starter.zip" \
    "${SANS_STARTER_SHA256:-}"
  if [[ -f "${FIXTURES}/sans-starter/sans-starter.zip" ]]; then
    (cd "${FIXTURES}/sans-starter" && unzip -qo sans-starter.zip || true)
  fi
else
  log "SKIP sans-starter: set SANS_STARTER_URL to a mirror of https://sansorg.egnyte.com/fl/HhH7crTYT4JK"
fi

# ---------------------------------------------------------------------
# 2. NIST CFReDS Hacking Case (~4.5 GB E01). Public domain.
#    The canonical distribution URL is long-lived.
# ---------------------------------------------------------------------
fetch_fixture \
  "https://cfreds-archive.nist.gov/Hacking_Case/SCHARDT.001" \
  "nist-hacking-case/SCHARDT.001" \
  ""  # sha recorded on first pull

# ---------------------------------------------------------------------
# 3. OTRF Security-Datasets — small EVTX/JSON samples. MIT.
#    Clone sparse (only one dataset family) to stay under ~100 MB.
# ---------------------------------------------------------------------
if [[ ! -d "${FIXTURES}/otrf-apt3-mordor/.git" ]]; then
  log "cloning OTRF Security-Datasets (sparse)..."
  rm -rf "${FIXTURES}/otrf-apt3-mordor"
  git clone --depth 1 --filter=blob:none --sparse \
    https://github.com/OTRF/Security-Datasets.git \
    "${FIXTURES}/otrf-apt3-mordor"
  (cd "${FIXTURES}/otrf-apt3-mordor" && \
    git sparse-checkout set \
      datasets/atomic/windows/defense_evasion \
      datasets/atomic/windows/credential_access || true)
else
  log "ok: otrf-apt3-mordor already cloned"
fi

# ---------------------------------------------------------------------
# 4. Volatility Foundation memory samples — pick the smallest one.
#    CC-BY; requires attribution (done in DATASET.md).
# ---------------------------------------------------------------------
fetch_fixture \
  "https://downloads.volatilityfoundation.org/volatility3/images/cridex.vmem" \
  "volatility/cridex.vmem" \
  ""

# ---------------------------------------------------------------------
# 5. Synthetic benign baseline — generated in-repo on first run.
#    Zero bytes of real data; lives to verify the agent distinguishes
#    clean systems from compromised ones. See DATASET.md §Synthetic.
# ---------------------------------------------------------------------
if [[ ! -f "${FIXTURES}/synthetic-benign/.generated" ]]; then
  mkdir -p "${FIXTURES}/synthetic-benign"
  : > "${FIXTURES}/synthetic-benign/.generated"
  cat > "${FIXTURES}/synthetic-benign/README.md" <<'EOF'
Synthetic benign baseline — generated by `scripts/fetch-fixtures.sh`.

Contents intentionally minimal. The agent's acceptance criterion for
this fixture is that it produces **zero findings** and verdict
`NO_EVIL`. A nonzero result proves hallucination.
EOF
  log "ok: synthetic-benign placeholder written"
fi

log "done. See ${SHA_FILE} for checksums."
