#!/usr/bin/env bash
# swarm-status.sh — morning triage dashboard.
#
# Spec #1 §10.3. Prints:
#   1. gh pr list --label swarm-generated --state open  (last night's PRs)
#   2. Latest summary JSON from logs/swarm/
#   3. Tail of the latest event log
#   4. Postgres DAG state (row counts by thread_id)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

hr() { printf '\n--- %s ---\n' "$*"; }

hr "swarm-generated PRs (open, draft)"
gh pr list --label swarm-generated --state open --limit 20 \
  --json number,title,headRefName,isDraft,createdAt \
  --template '{{range .}}#{{.number}} {{.title}} [{{.headRefName}}] draft={{.isDraft}} ({{timeago .createdAt}}){{"\n"}}{{end}}' \
  2>/dev/null \
  || echo "  (gh pr list failed — check auth)"

LOGS_DIR="logs/swarm"
if [[ -d "${LOGS_DIR}" ]]; then
  hr "latest summary"
  latest_summary=$(ls -t "${LOGS_DIR}"/*-summary.json 2>/dev/null | head -n1 || true)
  if [[ -n "${latest_summary}" ]]; then
    echo "file: ${latest_summary}"
    cat "${latest_summary}"
  else
    echo "  (no summary files yet)"
  fi

  hr "latest event log (last 20 lines)"
  latest_log=$(ls -t "${LOGS_DIR}"/*.jsonl 2>/dev/null | head -n1 || true)
  if [[ -n "${latest_log}" ]]; then
    echo "file: ${latest_log}"
    tail -n 20 "${latest_log}"
  else
    echo "  (no event logs yet)"
  fi
else
  hr "logs"
  echo "  ${LOGS_DIR} does not exist yet — run swarm-start.sh first."
fi

hr "postgres DAG threads"
if docker compose -f docker/swarm-postgres.yml ps --status=running 2>/dev/null | grep -q postgres; then
  docker compose -f docker/swarm-postgres.yml exec -T postgres \
    psql -U swarm -d swarm -c \
    "SELECT thread_id, COUNT(*) AS checkpoints FROM checkpoints GROUP BY thread_id ORDER BY thread_id DESC LIMIT 10;" \
    2>/dev/null \
    || echo "  (checkpoints table may not exist yet — swarm hasn't checkpointed)"
else
  echo "  postgres not running"
fi
