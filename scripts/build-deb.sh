#!/usr/bin/env bash
# build-deb.sh — produce find-evil_v<N>_amd64.deb for Ubuntu 22.04.
#
# Glue Spec #4 §4 (release.yml build-deb job). Called with one arg:
# the release version (e.g. `v2`). Packages the compiled Rust binary
# + Python agent wheel + CLI wrapper into a single .deb the judge
# can `sudo dpkg -i` on their SIFT VM.
#
# Pre-Week-2, this is a stub that builds a placeholder .deb with
# only the license + README so release.yml at least exits 0.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

VERSION="${1:-v0.0.0}"
VERSION_NUM="${VERSION#v}"
ARCH="amd64"
OUT_DIR="${OUT_DIR:-dist}"
PKG_NAME="find-evil"
PKG_DIR="$(mktemp -d)"
trap 'rm -rf "${PKG_DIR}"' EXIT

log() { printf '[build-deb] %s\n' "$*" >&2; }

# ---------------------------------------------------------------------
# Layout the deb staging directory.
# ---------------------------------------------------------------------
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/usr/share/${PKG_NAME}"
mkdir -p "${PKG_DIR}/usr/share/doc/${PKG_NAME}"

# 1. Compiled Rust MCP binary — if present.
if [[ -f "target/release/findevil-mcp" ]]; then
  cp target/release/findevil-mcp "${PKG_DIR}/usr/bin/findevil-mcp"
  chmod 0755 "${PKG_DIR}/usr/bin/findevil-mcp"
  log "included services/mcp target/release/findevil-mcp"
fi

# 2. Python agent wheel — if present.
for wheel in services/agent/dist/*.whl; do
  [[ -f "${wheel}" ]] || continue
  cp "${wheel}" "${PKG_DIR}/usr/share/${PKG_NAME}/"
  log "included $(basename "${wheel}")"
done

# 3. CLI wrapper — the `find-evil` entry point users invoke.
cat > "${PKG_DIR}/usr/bin/find-evil" <<'EOF'
#!/usr/bin/env bash
# find-evil CLI wrapper — dispatches to the installed agent package.
set -euo pipefail
if ! command -v python3 >/dev/null 2>&1; then
  echo "find-evil requires python3" >&2; exit 1
fi
exec python3 -m findevil_agent.cli "$@"
EOF
chmod 0755 "${PKG_DIR}/usr/bin/find-evil"

# 4. Docs — LICENSE + README-submission if present.
cp LICENSE "${PKG_DIR}/usr/share/doc/${PKG_NAME}/copyright"
if [[ -f "docs/templates/devpost-readme.md" ]]; then
  cp docs/templates/devpost-readme.md \
    "${PKG_DIR}/usr/share/doc/${PKG_NAME}/README.md"
fi

# 5. Control file.
PKG_SIZE_KB=$(du -sk "${PKG_DIR}" | awk '{print $1}')
cat > "${PKG_DIR}/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION_NUM}
Architecture: ${ARCH}
Maintainer: Find Evil! <noreply@example.invalid>
Installed-Size: ${PKG_SIZE_KB}
Depends: python3 (>= 3.10), sleuthkit, libewf2
Section: utils
Priority: optional
Homepage: https://github.com/
Description: Automated DFIR pipeline for the SANS SIFT Workstation
 Find Evil! investigates Windows host evidence end-to-end and
 produces cryptographically-verifiable findings via sigstore +
 rs_merkle + OpenTimestamps. Submission for the SANS Find Evil!
 hackathon (2026).
EOF

# 6. postinst — no-op for now; placeholder for credential-check
# hook from Amendment A1 if we want to nudge judges.
cat > "${PKG_DIR}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
echo "find-evil installed. Credentials required (any of):"
echo "  (1) export CLAUDE_CODE_OAUTH_TOKEN=<token>  (claude setup-token)"
echo "  (2) claude auth login                       (interactive)"
echo "  (3) export ANTHROPIC_API_KEY=sk-ant-...     (console.anthropic.com)"
echo "Then: find-evil run --case <path.e01> --unattended"
exit 0
EOF
chmod 0755 "${PKG_DIR}/DEBIAN/postinst"

# ---------------------------------------------------------------------
# Build the .deb.
# ---------------------------------------------------------------------
mkdir -p "${OUT_DIR}"
DEB_FILE="${OUT_DIR}/${PKG_NAME}_${VERSION}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "${PKG_DIR}" "${DEB_FILE}"

log "built: ${DEB_FILE}"
sha256sum "${DEB_FILE}"
