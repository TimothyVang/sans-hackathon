# findevil-swarm

Autonomous build swarm that drives Claude Code subagents to execute `BUILD_PLAN_v2.md` week by week.

**Read first:**
- `docs/superpowers/specs/2026-04-24-autonomous-build-swarm-design.md` — authoritative design (Spec #1)
- `docs/superpowers/specs/2026-04-23-amendment-option-b-claude-code-mode.md` — **Amendment A1, active** — overrides Spec #1's LiteLLM / USD-budget sections. Workers use the user's Claude Code subscription via local `claude` CLI; `session_guard.py` halts cleanly on rate-limit signals.
- `docs/superpowers/specs/2026-04-25-amendment-a2-claude-code-primary-interface.md` — **Amendment A2, active** — affects the *build target*, not the swarm itself. The swarm should NOT generate `services/agent/findevil_agent/graph.py`, `api.py`, `cli.py`, `supervisor.py`, or `specialists/` — Claude Code IS the orchestrator. Generate `services/agent_mcp/` tool wrappers instead when extending the M2/M4 surfaces.
- `docs/superpowers/plans/2026-04-23-build-swarm-plan.md` — 21 TDD tasks, execute in order.

**One-sentence summary:** a nightly-cron LangGraph supervisor forks per-language Claude Code subagents into git worktrees, each subagent writes one PR-sized chunk of code, a critic subagent gates every output, and draft PRs open against `main` for morning human triage.

## Required runtime services

1. **Postgres 16** (`docker compose -f docker/swarm-postgres.yml up -d`) — `PostgresSaver` stores the StateGraph DAG between turns and across laptop sleep.
2. **`claude` CLI on `$PATH`** — with either `CLAUDE_CODE_OAUTH_TOKEN` exported or `claude auth login` completed interactively.
3. **`gh` CLI on `$PATH`** — workers call `gh pr create --draft` to ship their output for human review.

## Entry points

Documented in `CLAUDE.md` (repo root) and generated from `services/swarm/main.py`:

```
bash scripts/swarm-start.sh                    # pre-flight + nightly supervisor run
uv run python -m services.swarm.main --week 4 --dry-run-gate
uv run python -m services.swarm.main --resume  # after laptop sleep
bash scripts/swarm-status.sh                   # morning triage dashboard
```

## Invariants (Amendment A1)

- No LiteLLM. No USD budget. No `ANTHROPIC_API_KEY` in the swarm's runtime path.
- Workers invoke `claude` CLI subprocess with `CLAUDE_CODE_FORK_SUBAGENT=1`.
- `services/swarm/session_guard.py` detects rate limits and halts — no retry. Postgres checkpoint carries forward.
- Per-subagent `--max-turns=40` + no-progress detector (3 zero-diff tool calls → kill) + 8-hour wall-clock watchdog.
- One git worktree per PR. Never two workers on the same branch. Never auto-merge.
