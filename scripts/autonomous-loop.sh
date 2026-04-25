#!/usr/bin/env bash
# autonomous-loop.sh — drive `claude --print` in a loop as a subprocess.
#
# Runs unattended for up to 24h, picking the next critical-path item
# from the autonomous queue each iteration. Mirrors the build swarm's
# worker pattern (services/swarm/findevil_swarm/workers/base_worker.py)
# — same headless `claude --print` invocation, same session_guard
# rate-limit detection, same fail-fast posture.
#
# Why bash and not the swarm directly: the swarm regenerates A2-deleted
# modules from its plans, which we don't want. This loop just says
# "Claude, read the queue file, do the next thing". No plan reconciliation.
#
# Usage:
#   bash scripts/autonomous-loop.sh                     # run with defaults (24h watchdog)
#   WATCHDOG_HOURS=8 bash scripts/autonomous-loop.sh    # shorter watchdog
#   MAX_TURNS=120 bash scripts/autonomous-loop.sh       # bigger per-iteration budget
#   bash scripts/autonomous-loop.sh --dry-run           # echo prompts, don't invoke claude
#
# Stop:
#   bash scripts/autonomous-loop-stop.sh                # graceful (SIGTERM)
#   kill -9 $(cat tmp/autonomous-loop.pid)              # forceful
#
# Outputs:
#   tmp/autonomous-loop.log      — full timestamped log
#   tmp/autonomous-loop.pid      — current PID (deleted on clean exit)
#   tmp/autonomous-loop/iter-N/  — per-iteration stdout + stderr capture
#
# Env knobs:
#   WATCHDOG_HOURS    default 24 — max wall-clock before forced stop
#   MAX_TURNS         default 80 — claude --max-turns per iteration
#   ITER_SLEEP_SEC    default 60 — pause between iterations
#   BACKOFF_SEC       default 300 — pause after a non-rate-limit failure
#   MODEL             default "claude-opus-4-7" — model for headless runs
#   CLAUDE_CMD        default "claude" — override binary path

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

WATCHDOG_HOURS="${WATCHDOG_HOURS:-24}"
MAX_TURNS="${MAX_TURNS:-80}"
ITER_SLEEP_SEC="${ITER_SLEEP_SEC:-60}"
BACKOFF_SEC="${BACKOFF_SEC:-300}"
MODEL="${MODEL:-claude-opus-4-7}"
CLAUDE_CMD="${CLAUDE_CMD:-claude}"

DRY_RUN=0
for arg in "$@"; do
  case "${arg}" in
    --dry-run) DRY_RUN=1 ;;
    -h | --help)
      sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "unknown arg: ${arg}" >&2
      exit 2
      ;;
  esac
done

WORKDIR="${REPO}/tmp"
LOG="${WORKDIR}/autonomous-loop.log"
PIDFILE="${WORKDIR}/autonomous-loop.pid"
ITER_DIR="${WORKDIR}/autonomous-loop"
QUEUE_FILE="${HOME}/.claude/projects/C--Users-newbi-Desktop-PUG-Projects-SANS-Hackathon/memory/project_autonomous_queue.md"

mkdir -p "${ITER_DIR}"

# Single-instance guard.
if [[ -f "${PIDFILE}" ]] && kill -0 "$(cat "${PIDFILE}")" 2>/dev/null; then
  echo "ERROR: another autonomous-loop is already running (pid $(cat "${PIDFILE}"))" >&2
  echo "       stop it first: bash scripts/autonomous-loop-stop.sh" >&2
  exit 1
fi
echo $$ > "${PIDFILE}"

# Clean up pidfile on exit. Keep the log + iter dirs for forensics.
cleanup() {
  rm -f "${PIDFILE}"
}
trap cleanup EXIT

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "${LOG}"
}

log "autonomous-loop starting"
log "  repo=${REPO}"
log "  watchdog=${WATCHDOG_HOURS}h, max_turns=${MAX_TURNS}, model=${MODEL}"
log "  iter_sleep=${ITER_SLEEP_SEC}s, backoff=${BACKOFF_SEC}s"
log "  queue=${QUEUE_FILE}"
log "  dry_run=${DRY_RUN}"

if [[ ! -f "${QUEUE_FILE}" ]]; then
  log "ERROR: queue file not found: ${QUEUE_FILE}"
  exit 1
fi

if [[ ${DRY_RUN} -eq 0 ]] && ! command -v "${CLAUDE_CMD}" >/dev/null 2>&1; then
  log "ERROR: ${CLAUDE_CMD} not on PATH (set CLAUDE_CMD or install Claude Code)"
  exit 127
fi

# Rate-limit patterns mirror services/swarm/findevil_swarm/session_guard.py
# _RATE_LIMIT_PATTERNS. Tracked verbatim so a real-incident stderr halts
# us cleanly the same way the swarm halts.
RATE_LIMIT_RE='[Yy]ou.?re out of extra usage|usage[[:space:]]+limit[[:space:]]+reached|reached[[:space:]]+(your[[:space:]]+)?usage[[:space:]]+limit|quota[[:space:]]+exceeded|http[[:space:]]*429|status[[:space:]]+code[[:space:]]+429|returned[[:space:]]+429|429[[:space:]]*:[[:space:]]*too[[:space:]]+many[[:space:]]+requests|rate[[:space:]\-]?limit(ed[[:space:]]+by|[[:space:]]+exceeded)|too[[:space:]]+many[[:space:]]+requests'

PROMPT='You are running iteration of an autonomous /loop for the SANS Find Evil hackathon submission.

Read the queue file: C:/Users/newbi/.claude/projects/C--Users-newbi-Desktop-PUG-Projects-SANS-Hackathon/memory/project_autonomous_queue.md

Pick the highest-priority unblocked item that is NOT already marked [x]. Complete it end-to-end:
  1. Implement following the established pattern (see prior commits for reference)
  2. Write integration tests
  3. Verify: cargo test --workspace --locked, cargo clippy --workspace --all-targets --locked -- -D warnings, cargo fmt --all --check, ruff check ., ruff format --check . — all must be green
  4. Commit locally with a conventional commit message
  5. Update the queue file: change [ ] to [x] and append the commit SHA + outcome
  6. Print a one-line summary of what you shipped

DO NOT push to remote. DO NOT touch the dropped graph.py / api.py / cli.py / supervisor.py / specialists/ paths. Karpathy 4 principles in CLAUDE.md apply (think-before-coding, simplicity, surgical changes, goal-driven execution).

If you hit a rate limit, write "RATE_LIMIT_HIT" on its own line and exit. If a task takes more than 2x its estimate or would require destructive action, write "PAUSE_AND_ASK: <reason>" on its own line and exit.

If the queue has no unblocked items remaining (only Hard blockers left), write "QUEUE_EXHAUSTED" on its own line and exit.

Otherwise just do the work and report.'

START_EPOCH=$(date +%s)
ITERATION=0
WATCHDOG_SECS=$((WATCHDOG_HOURS * 3600))

while true; do
  NOW=$(date +%s)
  ELAPSED=$((NOW - START_EPOCH))
  if [[ ${ELAPSED} -gt ${WATCHDOG_SECS} ]]; then
    log "watchdog: ${WATCHDOG_HOURS}h elapsed (${ELAPSED}s) — stopping"
    break
  fi

  ITERATION=$((ITERATION + 1))
  ITER_DIR_N="${ITER_DIR}/iter-${ITERATION}"
  mkdir -p "${ITER_DIR_N}"

  log "iter ${ITERATION} starting (elapsed=${ELAPSED}s of ${WATCHDOG_SECS}s)"

  if [[ ${DRY_RUN} -eq 1 ]]; then
    log "  [dry-run] would invoke: ${CLAUDE_CMD} --print --max-turns ${MAX_TURNS} --model ${MODEL}"
    log "  [dry-run] sleeping ${ITER_SLEEP_SEC}s and looping"
    sleep "${ITER_SLEEP_SEC}"
    continue
  fi

  STDOUT="${ITER_DIR_N}/stdout"
  STDERR="${ITER_DIR_N}/stderr"

  # Headless invocation. CLAUDE_CODE_OAUTH_TOKEN (if set) is inherited
  # from the parent env; otherwise falls back to ~/.claude/ session.
  set +e
  printf '%s' "${PROMPT}" \
    | "${CLAUDE_CMD}" --print --max-turns "${MAX_TURNS}" --model "${MODEL}" \
        >"${STDOUT}" 2>"${STDERR}"
  EXIT_CODE=$?
  set -e

  log "iter ${ITERATION} exited ${EXIT_CODE}"

  # Rate-limit detection — checks both stdout and stderr because some
  # claude versions surface limits on stdout.
  if grep -qiE "${RATE_LIMIT_RE}" "${STDERR}" "${STDOUT}" 2>/dev/null \
     || grep -q "RATE_LIMIT_HIT" "${STDOUT}" 2>/dev/null; then
    log "RATE LIMIT detected — halting (resume tomorrow)"
    log "  stderr tail: $(tail -3 "${STDERR}" 2>/dev/null | tr '\n' ' ')"
    exit 1
  fi

  # Queue-exhausted signal from the model.
  if grep -q "QUEUE_EXHAUSTED" "${STDOUT}" 2>/dev/null; then
    log "queue exhausted — only hard blockers remain (GitHub remote / demo video)"
    log "  these need user input; stopping cleanly"
    break
  fi

  # Pause-and-ask signal from the model.
  if grep -q "PAUSE_AND_ASK" "${STDOUT}" 2>/dev/null; then
    REASON=$(grep -m1 "PAUSE_AND_ASK" "${STDOUT}" | sed 's/PAUSE_AND_ASK://')
    log "model paused for user input: ${REASON}"
    log "  stopping; resume manually after addressing the question"
    break
  fi

  if [[ ${EXIT_CODE} -ne 0 ]]; then
    log "non-zero exit (${EXIT_CODE}); backing off ${BACKOFF_SEC}s before retry"
    log "  stderr tail: $(tail -3 "${STDERR}" 2>/dev/null | tr '\n' ' ')"
    sleep "${BACKOFF_SEC}"
    continue
  fi

  # Last line of stdout is typically the model's summary.
  SUMMARY=$(tail -1 "${STDOUT}" 2>/dev/null | head -c 200)
  log "iter ${ITERATION} ok: ${SUMMARY}"

  # Brief pause between iterations — keeps the prompt cache window
  # warm + gives the user a chance to SIGTERM if they're watching.
  sleep "${ITER_SLEEP_SEC}"
done

log "autonomous-loop finished cleanly after ${ITERATION} iterations"
