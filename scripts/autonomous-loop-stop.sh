#!/usr/bin/env bash
# Graceful stop for autonomous-loop.sh. Sends SIGTERM; the running
# iteration finishes its claude invocation before exiting.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="${REPO}/tmp/autonomous-loop.pid"

if [[ ! -f "${PIDFILE}" ]]; then
  echo "no pidfile at ${PIDFILE} — is the loop running?" >&2
  exit 1
fi
PID=$(cat "${PIDFILE}")
if ! kill -0 "${PID}" 2>/dev/null; then
  echo "stale pidfile (pid ${PID} not running); cleaning up" >&2
  rm -f "${PIDFILE}"
  exit 0
fi
echo "sending SIGTERM to autonomous-loop pid ${PID}..."
kill -TERM "${PID}"
echo "  the running iteration will finish its current claude invocation, then exit"
echo "  watch progress with: tail -f ${REPO}/tmp/autonomous-loop.log"
