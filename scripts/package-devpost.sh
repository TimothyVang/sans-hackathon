#!/usr/bin/env bash
# package-devpost.sh — assemble the Devpost submission zip.
#
# Glue Spec #4 §9. Runs inside .github/workflows/devpost-submit.yml
# after release.yml is green. Expects:
#
#   - DEMO_VIDEO_URL env var set (checked)
#   - RELEASE_TAG env var (defaults to 'v-submit')
#   - release-assets/ containing .deb + report.html (from
#     `gh release download`)
#   - benchmark-results.csv at cwd (produced by json-to-benchmark-csv.py)
#   - LICENSE + SUBMISSION_NOTES.md + docs/templates/devpost-readme.md
#     from the repo

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT_ZIP="${OUT_ZIP:-find-evil-submission.zip}"
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "${STAGE_DIR}"' EXIT

log() { printf '[package-devpost] %s\n' "$*" >&2; }

# ---------------------------------------------------------------------
# Pre-flight.
# ---------------------------------------------------------------------
: "${DEMO_VIDEO_URL:?DEMO_VIDEO_URL not set — run: gh variable set DEMO_VIDEO_URL --body '<url>'}"

RELEASE_TAG="${RELEASE_TAG:-v-submit}"
ACCURACY="${ACCURACY:-0}"
DATE="${DATE:-$(date -u +%Y-%m-%d)}"

# ---------------------------------------------------------------------
# 1. README-submission.md via envsubst.
# ---------------------------------------------------------------------
if [[ ! -f docs/templates/devpost-readme.md ]]; then
  log "ERROR: docs/templates/devpost-readme.md missing"; exit 1
fi
export DEMO_VIDEO_URL RELEASE_TAG ACCURACY DATE
envsubst '$DEMO_VIDEO_URL $RELEASE_TAG $ACCURACY $DATE' \
  < docs/templates/devpost-readme.md \
  > "${STAGE_DIR}/README-submission.md"

# Sanity: no unsubstituted placeholders.
if grep -qE '\$\{[A-Z_]+\}' "${STAGE_DIR}/README-submission.md"; then
  log "ERROR: unsubstituted \${...} in README-submission.md"
  grep -nE '\$\{[A-Z_]+\}' "${STAGE_DIR}/README-submission.md" | head -5
  exit 1
fi

# ---------------------------------------------------------------------
# 2. demo-video-link.txt — plaintext URL.
# ---------------------------------------------------------------------
echo "${DEMO_VIDEO_URL}" > "${STAGE_DIR}/demo-video-link.txt"

# ---------------------------------------------------------------------
# 3. LICENSE — canonical Apache-2.0.
# ---------------------------------------------------------------------
if [[ ! -f LICENSE ]]; then
  log "ERROR: LICENSE missing at repo root"; exit 1
fi
cp LICENSE "${STAGE_DIR}/LICENSE"

# ---------------------------------------------------------------------
# 4. .deb — from release-assets/.
# ---------------------------------------------------------------------
deb=$(ls release-assets/*.deb 2>/dev/null | head -n1 || true)
if [[ -z "${deb}" ]]; then
  log "WARN: no .deb in release-assets/; submission zip will omit it"
else
  cp "${deb}" "${STAGE_DIR}/"
fi

# ---------------------------------------------------------------------
# 5. report.html — from release-assets/.
# ---------------------------------------------------------------------
if [[ -f release-assets/report.html ]]; then
  cp release-assets/report.html "${STAGE_DIR}/"
else
  log "WARN: no report.html in release-assets/"
fi

# ---------------------------------------------------------------------
# 6. benchmark-results.csv.
# ---------------------------------------------------------------------
if [[ -f benchmark-results.csv ]]; then
  cp benchmark-results.csv "${STAGE_DIR}/"
else
  log "WARN: no benchmark-results.csv; creating stub"
  echo 'fixture,findings_matched' > "${STAGE_DIR}/benchmark-results.csv"
fi

# ---------------------------------------------------------------------
# 7. SUBMISSION_NOTES.md (may be the stub; that's fine).
# ---------------------------------------------------------------------
cp SUBMISSION_NOTES.md "${STAGE_DIR}/SUBMISSION_NOTES.md"

# ---------------------------------------------------------------------
# Integrity check per Spec #4 §9 step 6.
# ---------------------------------------------------------------------
required=(
  "README-submission.md"
  "benchmark-results.csv"
  "demo-video-link.txt"
  "LICENSE"
  "report.html"
  "SUBMISSION_NOTES.md"
)
# .deb is conditional — only required when release-assets had one.
if [[ -n "${deb:-}" ]]; then
  required+=("$(basename "${deb}")")
fi

missing=0
for f in "${required[@]}"; do
  if [[ ! -f "${STAGE_DIR}/${f}" ]]; then
    log "ERROR: missing from stage dir: ${f}"
    missing=$((missing + 1))
  fi
done
if [[ "${missing}" -gt 0 ]]; then
  log "aborting — ${missing} required file(s) missing"
  exit 1
fi

# ---------------------------------------------------------------------
# Zip.
# ---------------------------------------------------------------------
(cd "${STAGE_DIR}" && zip -q -r "${REPO_ROOT}/${OUT_ZIP}" .)
ls -lh "${REPO_ROOT}/${OUT_ZIP}"
log "done: ${OUT_ZIP}"
