#!/usr/bin/env bash
# swarm-start.sh — pre-flight checks + launch the swarm.
#
# Spec #1 §9.2 + Amendment A1. Checks:
#   1. Docker Compose swarm-postgres is running (starts if not).
#   2. 'gh' CLI is authenticated (no way to open PRs without it).
#   3. 'claude' CLI is on PATH unless --mock-workers is used.
#   4. 'git status --porcelain' on main is clean (no human edits).
#   5. No leaked .wt/wt-* worktrees from a prior crashed run.
#
# Under Option B, no Anthropic API key is required. Credentials come
# from the user's Claude Code session — either ~/.claude/ (after
# 'claude auth login') or CLAUDE_CODE_OAUTH_TOKEN env var.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

# Arg forwarding to findevil-swarm run.
ARGS=("$@")
MOCK_WORKERS=0
for a in "${ARGS[@]}"; do
  if [[ "${a}" == "--mock-workers" ]]; then
    MOCK_WORKERS=1
  fi
done

log() { printf '[swarm-start] %s\n' "$*" >&2; }

# 1. Postgres.
log "checking docker compose postgres..."
if ! docker compose -f docker/swarm-postgres.yml ps --status=running | grep -q postgres; then
  log "postgres not running; starting..."
  docker compose -f docker/swarm-postgres.yml up -d
  # Wait for healthy.
  for i in {1..30}; do
    if docker compose -f docker/swarm-postgres.yml exec -T postgres pg_isready -U swarm >/dev/null 2>&1; then
      log "postgres healthy"
      break
    fi
    sleep 1
    if [[ $i -eq 30 ]]; then
      log "ERROR: postgres did not become healthy in 30s"
      exit 1
    fi
  done
fi

# 2. gh CLI auth.
log "checking gh CLI auth..."
if ! gh auth status >/dev/null 2>&1; then
  log "ERROR: gh CLI not authenticated. Run: gh auth login"
  exit 1
fi

# 3. claude CLI (only required when not mocking).
if [[ "${MOCK_WORKERS}" -eq 0 ]]; then
  log "checking claude CLI..."
  if ! command -v claude >/dev/null 2>&1; then
    log "ERROR: 'claude' CLI not on PATH and --mock-workers not set"
    exit 1
  fi
  # If no OAuth token and no interactive session on disk, bail.
  if [[ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]] && [[ ! -d "${HOME}/.claude" ]]; then
    log "ERROR: no Claude Code credentials found. Either:"
    log "       1) export CLAUDE_CODE_OAUTH_TOKEN=<token> (run 'claude setup-token')"
    log "       2) run 'claude auth login' to populate ~/.claude/"
    exit 1
  fi
fi

# 4. Git clean.
log "checking git tree is clean on main..."
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "${BRANCH}" != "main" ]] && [[ "${BRANCH}" != "master" ]]; then
  log "WARN: currently on branch '${BRANCH}', not main/master. Continuing."
fi
if [[ -n "$(git status --porcelain)" ]]; then
  log "ERROR: working tree is dirty. Stash or commit before swarm runs."
  git status --short >&2
  exit 1
fi

# 5. Leaked worktrees.
log "checking for leaked worktrees..."
# Delegate to swarm code — it knows the semantics.
python3 -c "
import sys
sys.path.insert(0, 'services/swarm')
from pathlib import Path
from findevil_swarm.worktree import iter_leaked
leaks = list(iter_leaked(Path('.')))
if leaks:
    print(f'[swarm-start] found {len(leaks)} leaked worktree(s); cleaning...', file=sys.stderr)
    for leak in leaks:
        print(f'  {leak.path} ({leak.branch})', file=sys.stderr)
import subprocess
subprocess.run(['git', 'worktree', 'prune'], check=False)
"

# Launch.
log "invoking findevil-swarm run ..."
cd services/swarm
exec uv run python -m findevil_swarm.main run "${ARGS[@]}"
