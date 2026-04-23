# Spec #1 — Autonomous Build Swarm

**Date:** 2026-04-24
**Status:** Design — awaiting user approval
**Depends on:** `2026-04-23-layered-test-sandbox-design.md` (Spec #3 must be approved first)
**Enables:** `2026-04-25-the-product-design.md` (Spec #2), `2026-04-26-orchestration-glue-design.md` (Spec #4)
**Parent:** `2026-04-23-find-evil-automation-master-design.md`
**Deadline:** 2026-06-15 22:45 CDT
**Reference architecture:** `C:/Users/newbi/.claude/projects/C--Users-newbi-Desktop-PUG-Projects-SANS-Hackathon/memory/project_swarm_architecture.md`

---

## 1. Problem statement

The `BUILD_PLAN_v2.md` roadmap covers 9 weeks of work: Rust MCP server, LangGraph graph, three-layer memory, Next.js UI, benchmark harness, moonshots M1-M4, and demo polish. A single human developer working evenings cannot complete that scope before 2026-06-15 without autonomous code generation running overnight every night.

The swarm must satisfy five constraints simultaneously:

1. **Correct output.** Every PR it opens must pass L1 (unit/build) before a human sees it. The human's morning review budget is one hour — triage time only, not debugging time.
2. **Bounded spend.** The $47k November 2025 LangChain incident (Analyzer/Verifier ping-pong, 11 days, unlimited budget) is the failure mode to prevent. Hard USD caps, not soft alerts, are the only reliable control. (Source: `project_swarm_architecture.md` — Anti-patterns.)
3. **Resume safety.** The swarm runs on a laptop that sleeps. SQLite WAL corruption on sleep/wake is a documented failure mode for overnight runs; PostgresSaver on a local Docker Postgres avoids it. (Source: `project_swarm_architecture.md` — Key primitives.)
4. **No stomping.** Rust, Python, and TypeScript workers must not conflict on file edits. Git worktrees are the isolation primitive; one worktree per PR is non-negotiable.
5. **Human stays in control.** Every PR opens as a draft. The human merges. The swarm never force-pushes `main` and never auto-merges.

The swarm is invisible to judges — it builds the Product (Spec #2), which is the submission. The swarm's quality is measured entirely by what it ships.

---

## 2. Component diagram (ASCII)

```
┌─────────────────────────────────────────────────────────────────────┐
│  SCHEDULER LAYER                                                      │
│  jshchnz/claude-code-scheduler  cron: "0 23 * * *"  (11 PM nightly) │
│  Calls: python services/swarm/main.py --week <N> --dry-run-gate      │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ spawns
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SUPERVISOR  (services/swarm/supervisor.py)                          │
│  LangGraph StateGraph  +  PostgresSaver (docker: postgres:16-alpine) │
│  Holds: week→PR DAG parsed from BUILD_PLAN_v2.md                     │
│  Thread ID: "swarm-week-{N}-{date}"                                  │
│                                                                       │
│  ┌──────────────┐    ┌────────────────┐    ┌────────────────────┐   │
│  │  plan_node   │───▶│  dispatch_node │───▶│  collect_node      │   │
│  │  Parse plan  │    │  Fork workers  │    │  Await PRs + CI    │   │
│  │  emit PRSpec │    │  per language  │    │  Emit night report │   │
│  └──────────────┘    └────────┬───────┘    └────────────────────┘   │
└────────────────────────────────┼────────────────────────────────────┘
                                 │  CLAUDE_CODE_FORK_SUBAGENT=1
                        ┌────────┼────────┐
                        ▼        ▼        ▼
         ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
         │  RUST WORKER     │  │  PYTHON WORKER   │  │  TS WORKER       │
         │  rust_worker.py  │  │  python_worker.py│  │  ts_worker.py    │
         │                  │  │                  │  │                  │
         │  git worktree:   │  │  git worktree:   │  │  git worktree:   │
         │  .wt/wt-rust-NN  │  │  .wt/wt-py-NN    │  │  .wt/wt-ts-NN    │
         │                  │  │                  │  │                  │
         │  Aider arch pass │  │  Aider arch pass │  │  Aider arch pass │
         │  (claude-opus-4) │  │  (claude-opus-4) │  │  (claude-opus-4) │
         │  Aider edit pass │  │  Aider edit pass │  │  Aider edit pass │
         │  (sonnet-4-5)    │  │  (sonnet-4-5)    │  │  (sonnet-4-5)    │
         │                  │  │                  │  │                  │
         │  L1 sandbox run  │  │  L1 sandbox run  │  │  L1 sandbox run  │
         └────────┬─────────┘  └────────┬─────────┘  └────────┬────────┘
                  │                     │                      │
                  └─────────────────────┼──────────────────────┘
                                        │ diff + test output
                                        ▼
                         ┌─────────────────────────┐
                         │  CRITIC SUBAGENT         │
                         │  critic.py               │
                         │  model: claude-sonnet-4-5│
                         │                          │
                         │  Checks:                 │
                         │  - diff sanity           │
                         │  - L1 exit code          │
                         │  - no-progress flag      │
                         │  - token ceiling         │
                         │                          │
                         │  APPROVE → gh pr create  │
                         │  REJECT  → kill + log    │
                         └────────────┬────────────┘
                                      │ if APPROVE
                                      ▼
                         ┌─────────────────────────┐
                         │  gh pr create --draft    │
                         │  branch: swarm/week-N-*  │
                         │  Human reviews AM        │
                         └─────────────────────────┘

  ───────────────────── CROSS-CUTTING INFRASTRUCTURE ─────────────────
  LiteLLM Proxy (localhost:4000)     — hard $50/night cap, model router
  Postgres (localhost:5432)          — PostgresSaver DAG checkpoints
  Watchdog (watchdog.py)             — 8-hour wall-clock kill switch
  No-progress detector (in workers)  — 3 tool calls w/o new diff → kill
  JSONL sidecar (tool_calls.jsonl)   — OpenHands-style replay log
```

---

## 3. Module list with file paths

All paths are relative to the repository root `C:\Users\newbi\Desktop\PUG Projects\SANS-Hackathon`.

### 3.1 Core swarm services

| File | Role |
|---|---|
| `services/swarm/__init__.py` | Package init; exports `SwarmState`, `PRSpec` |
| `services/swarm/supervisor.py` | LangGraph `StateGraph` definition; `plan_node`, `dispatch_node`, `collect_node`; `PostgresSaver` wiring |
| `services/swarm/state.py` | `SwarmState` TypedDict + all reducer annotations; `PRSpec` Pydantic model |
| `services/swarm/plan_parser.py` | Reads `BUILD_PLAN_v2.md`, emits ordered list of `PRSpec` objects for the current week |
| `services/swarm/dispatch.py` | Forks workers via `claude` CLI subprocess; sets `CLAUDE_CODE_FORK_SUBAGENT=1` |
| `services/swarm/workers/__init__.py` | Package init |
| `services/swarm/workers/base_worker.py` | Abstract base: worktree create/commit/push/cleanup; L1 invocation; no-progress detector; JSONL sidecar writer |
| `services/swarm/workers/rust_worker.py` | Rust-specific system prompt fragments; `cargo test` L1 invocation |
| `services/swarm/workers/python_worker.py` | Python-specific system prompt fragments; `pytest` L1 invocation |
| `services/swarm/workers/ts_worker.py` | TypeScript-specific system prompt fragments; `pnpm test` L1 invocation |
| `services/swarm/critic.py` | Critic subagent: consumes diff + L1 exit code + JSONL sidecar; emits `CriticVerdict` |
| `services/swarm/watchdog.py` | Wall-clock 8-hour process group killer; arms on supervisor startup |
| `services/swarm/budget.py` | LiteLLM spend query helper; raises `BudgetExhaustedError` if > $50 |
| `services/swarm/worktree.py` | `git worktree add/remove` wrappers; naming convention enforcer |
| `services/swarm/pr_gate.py` | Dry-run gate logic: first PR, observe CI result, release or pause |
| `services/swarm/night_report.py` | Structured JSONL nightly report emitter |
| `services/swarm/main.py` | CLI entry: `--week N`, `--dry-run-gate`, `--resume`; spawns supervisor |

### 3.2 Configuration

| File | Role |
|---|---|
| `services/swarm/config/litellm_config.yaml` | LiteLLM proxy config: model routing, $50 hard cap, per-key spend tracking |
| `services/swarm/config/scheduler_config.yaml` | `jshchnz/claude-code-scheduler` task definition (cron, task prompt, env) |
| `services/swarm/config/postgres.env` | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` for local Docker Postgres |

### 3.3 Infrastructure

| File | Role |
|---|---|
| `docker/swarm-postgres.yml` | Docker Compose: `postgres:16-alpine`, named volume `swarm_pg_data`, port 5432 |
| `scripts/swarm-start.sh` | Pre-flight: verify Postgres up, LiteLLM proxy up, git clean; then call `main.py` |
| `scripts/swarm-status.sh` | Morning status: `gh pr list`, last night_report.jsonl tail, LiteLLM spend |

### 3.4 Tests

| File | Role |
|---|---|
| `tests/swarm/test_plan_parser.py` | Unit: `plan_parser.py` emits correct `PRSpec` list for each week |
| `tests/swarm/test_worktree.py` | Unit: worktree create/cleanup; no leaked worktrees on exception |
| `tests/swarm/test_critic.py` | Unit: critic returns APPROVE on green diff, REJECT on empty diff |
| `tests/swarm/test_budget.py` | Unit: `BudgetExhaustedError` raised when mock spend > $50 |
| `tests/swarm/test_no_progress.py` | Unit: worker killed after 3 tool calls with no new file diff |
| `tests/swarm/test_resume.py` | Integration: supervisor resumes from Postgres checkpoint after simulated sleep |
| `tests/swarm/test_dry_run_gate.py` | Integration: gate pauses swarm when first PR's CI fails |

---

## 4. LangGraph state schema

`services/swarm/state.py` defines the canonical shared state type.

```python
# services/swarm/state.py  (schema only — no implementation in this spec)

from __future__ import annotations
from typing import Annotated, Optional
from typing_extensions import TypedDict
import operator
from pydantic import BaseModel

# ------------------------------------------------------------------
# PRSpec — the atomic unit of work the supervisor dispatches
# ------------------------------------------------------------------
class PRSpec(BaseModel):
    pr_id: str                    # "week-2-rust-case-open-tool"
    week: int                     # 1–8
    language: str                 # "rust" | "python" | "typescript"
    title: str                    # Git PR title
    description: str              # Full task description sourced from BUILD_PLAN_v2.md
    files_expected: list[str]     # Paths the worker must touch (sanity check)
    l1_command: str               # Exact shell command to validate (e.g. "cargo test --workspace")
    token_ceiling: int            # Per-PR input token ceiling (default: 500_000)
    max_turns: int                # Per-subagent turn cap (default: 40)
    depends_on: list[str]         # Other pr_ids that must be merged first

# ------------------------------------------------------------------
# CriticVerdict — what the critic subagent returns
# ------------------------------------------------------------------
class CriticVerdict(BaseModel):
    pr_id: str
    decision: str                 # "APPROVE" | "REJECT"
    reason: str
    token_count_input: int
    token_count_output: int
    l1_exit_code: int
    diff_line_count: int

# ------------------------------------------------------------------
# NightlyReport — emitted once per supervisor run
# ------------------------------------------------------------------
class NightlyReport(BaseModel):
    date: str                     # ISO-8601
    week: int
    prs_opened: list[str]
    prs_rejected: list[str]
    total_spend_usd: float
    wall_clock_seconds: int
    budget_remaining_usd: float

# ------------------------------------------------------------------
# SwarmState — the DAG state object persisted by PostgresSaver
# ------------------------------------------------------------------
class SwarmState(TypedDict):
    # Immutable plan for the night (set once in plan_node)
    week: int
    pr_specs: list[PRSpec]

    # Mutable dispatch tracking
    # operator.add = append-only (new items accumulate, no overwrite)
    dispatched_pr_ids:  Annotated[list[str],          operator.add]
    completed_pr_ids:   Annotated[list[str],          operator.add]
    rejected_pr_ids:    Annotated[list[str],          operator.add]
    critic_verdicts:    Annotated[list[CriticVerdict], operator.add]

    # Budget tracking (latest value wins — last-write reducer)
    spend_usd_cumulative: float
    budget_exhausted: bool

    # Dry-run gate
    dry_run_gate_passed: bool
    dry_run_gate_pr_id: Optional[str]

    # Watchdog
    wall_clock_start_ts: int      # Unix epoch seconds

    # Night report (written once in collect_node)
    nightly_report: Optional[NightlyReport]
```

**Reducer rules:**
- `dispatched_pr_ids`, `completed_pr_ids`, `rejected_pr_ids`, `critic_verdicts` use `operator.add` — items only accumulate; nothing is overwritten. This is safe across parallel workers writing simultaneously.
- `spend_usd_cumulative`, `budget_exhausted`, `dry_run_gate_passed`, `nightly_report` use last-write (no annotation) — only the supervisor nodes write these; no parallel write risk.
- `pr_specs` and `week` are written once in `plan_node` and treated as immutable thereafter.

---

## 5. Worker contract

Each worker (`rust_worker.py`, `python_worker.py`, `ts_worker.py`) inherits from `base_worker.py`. The contract is: receive a `PRSpec`, return a `WorkerResult`.

### 5.1 Input: what a worker receives

```python
# Passed from dispatch_node to each worker process
@dataclass
class WorkerInput:
    pr_spec: PRSpec
    worktree_path: str        # Absolute path: "<repo>/.wt/wt-{lang}-{pr_id}"
    branch_name: str          # "swarm/week-{N}-{pr_id}"
    litellm_api_base: str     # "http://localhost:4000"
    litellm_api_key: str      # Scoped key with per-PR spend ceiling
    postgres_conn_string: str # For sub-state (not the main DAG checkpoint)
    jsonl_sidecar_path: str   # Path to write tool-call JSONL sidecar
    env_overrides: dict       # CLAUDE_CODE_FORK_SUBAGENT=1, autocompact=false
```

### 5.2 Execution sequence inside base_worker.py

1. Create worktree via `worktree.py` (`git worktree add .wt/wt-{lang}-{pr_id} -b swarm/week-{N}-{pr_id}`).
2. Set environment: `CLAUDE_CODE_FORK_SUBAGENT=1`, `ANTHROPIC_BASE_URL=http://localhost:4000`, autocompact disabled.
3. Invoke Claude Code subprocess via `claude` CLI:
   - `--max-turns {pr_spec.max_turns}` (default 40)
   - `--model claude-opus-4` for architect pass
   - System prompt includes `PRSpec.description` + relevant section of `BUILD_PLAN_v2.md`
   - Working directory: `worktree_path`
4. Aider architect/editor split (3-5x cost reduction per `project_swarm_architecture.md`):
   - Pass 1 (architect): model = `claude-opus-4` — plan the diff, emit plan as JSONL
   - Pass 2 (editor): model = `claude-sonnet-4-5` — apply the plan
5. No-progress detector runs as a sidecar thread:
   - After each tool call, inspect diff of `worktree_path` vs. branch HEAD
   - If 3 consecutive tool calls produce zero new lines in diff → kill subprocess, emit `NoProgressEvent`
6. On subprocess completion (or kill):
   - Run L1 command: `pr_spec.l1_command` inside worktree
   - Capture exit code + stdout/stderr
7. If L1 passes: `git add -A && git commit -m "swarm: {pr_spec.title}" && git push origin {branch_name}`
   - Pre-commit hook failures result in a new commit (never `--amend`), per Claude Code standard
8. Return `WorkerResult` to dispatch_node.

### 5.3 Output: what a worker returns

```python
@dataclass
class WorkerResult:
    pr_id: str
    branch_name: str
    worktree_path: str
    l1_exit_code: int
    l1_stdout: str            # Truncated to 10k chars
    l1_stderr: str            # Truncated to 10k chars
    diff_line_count: int
    token_count_input: int    # From LiteLLM spend log
    token_count_output: int
    no_progress_killed: bool
    wall_clock_seconds: int
    jsonl_sidecar_path: str   # Path to tool-call JSONL for critic + replay
```

### 5.4 Worker environment constraints

| Constraint | Value | Source |
|---|---|---|
| `--max-turns` | 40 | `project_swarm_architecture.md` — Budget controls |
| Input token ceiling per PR | 500,000 | `project_swarm_architecture.md` — Budget controls |
| `CLAUDE_CODE_FORK_SUBAGENT` | `1` | `project_swarm_architecture.md` — Key primitives |
| autocompact | disabled | Claude Code issue #9579 |
| `npm install` / `cargo build` | cached; install commands whitelisted only | `project_swarm_architecture.md` — Anti-patterns |
| Plan-mode | NOT used as safety rail | Claude Code issue #43777 (subagents bypass plan-mode) |
| Model — architect pass | `claude-opus-4` | `project_swarm_architecture.md` — Model tiering |
| Model — editor pass | `claude-sonnet-4-5` | `project_swarm_architecture.md` — Model tiering |

---

## 6. Critic contract

`services/swarm/critic.py` runs as a separate Claude Code subagent invocation (not a thread inside the worker). It executes after every `WorkerResult` is returned, before `gh pr create` is called.

### 6.1 Input: what the critic receives

```python
@dataclass
class CriticInput:
    worker_result: WorkerResult
    pr_spec: PRSpec
    diff_text: str            # Full output of git diff HEAD origin/main in worktree
    l1_log: str               # Combined stdout + stderr from L1 run
    jsonl_sidecar: list[dict] # Full tool-call JSONL sidecar from worker
```

### 6.2 Critic evaluation checklist

The critic subagent is prompted to verify all of the following. Failure on any item triggers REJECT:

| Check | Pass condition |
|---|---|
| L1 exit code | `== 0` |
| Diff non-empty | `diff_line_count > 0` |
| Expected files touched | All paths in `pr_spec.files_expected` appear in diff |
| No fabricated tool output | No tool call result in sidecar is marked `fabricated: true` |
| No infinite pattern | No single tool call repeated > 5 times in sidecar |
| Token ceiling not exceeded | `worker_result.token_count_input <= pr_spec.token_ceiling` |
| No-progress kill | If `no_progress_killed == True` → REJECT regardless of L1 |
| Diff sanity | No deletions of entire existing modules (line deletions > 50% of module → REJECT) |

### 6.3 Critic model

Model: `claude-sonnet-4-5` (not Opus — cost control). The critic receives structured input; its task is classification, not generation. Sonnet is sufficient.

### 6.4 Output: CriticVerdict

Defined in `state.py` (section 4). The critic MUST emit a `CriticVerdict` in structured JSON output (via `--output-format json` flag). Unstructured critic output is treated as REJECT.

### 6.5 Post-critic actions

- **APPROVE:** `gh pr create --draft --title "{pr_spec.title}" --body "{pr_spec.description + critic verdict summary}" --base main --head {branch_name}`. Worktree is kept until PR is merged or closed.
- **REJECT:** Log `CriticVerdict` to `night_report.jsonl`. Remove worktree (`git worktree remove --force`). Delete remote branch. `pr_id` added to `rejected_pr_ids` in `SwarmState`.

The critic alone is not sufficient for merge. Per `project_swarm_architecture.md`: "Gate on critic AND green CI." The human is the final merge authority. CI (L0 + L1 via GHA) runs automatically when the draft PR is created; the human's morning review sees both the critic verdict and the CI result.

---

## 7. Budget enforcement mechanics

### 7.1 LiteLLM proxy configuration

`services/swarm/config/litellm_config.yaml`:

```yaml
# LiteLLM proxy — local daemon, MIT license
# Start with: litellm --config services/swarm/config/litellm_config.yaml --port 4000

model_list:
  - model_name: claude-opus-4
    litellm_params:
      model: anthropic/claude-opus-4
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: claude-sonnet-4-5
    litellm_params:
      model: anthropic/claude-sonnet-4-5
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: claude-haiku-3-5
    litellm_params:
      model: anthropic/claude-haiku-3-5
      api_key: os.environ/ANTHROPIC_API_KEY

litellm_settings:
  # Hard cap: reject ALL calls once cumulative nightly spend >= $50
  # budget_duration resets at midnight; hard_budget refuses calls (not warns)
  max_budget: 50.0
  budget_duration: 1d

  success_callback: ["langfuse"]   # optional spend visibility
  failure_callback: ["langfuse"]

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/LITELLM_DATABASE_URL  # postgres for spend tracking

# Per-virtual-key budget (issued per PR by dispatch.py)
# Each PR gets a scoped key with ceiling = $5 (10 PRs/night max before global cap)
# Keys created via LiteLLM /key/generate endpoint at PR dispatch time
```

**Critical design decision:** alerts are not enforcement. When `max_budget` is exceeded, LiteLLM returns HTTP 429 to the Claude Code subprocess. The subprocess terminates. The watchdog records the budget-exhausted event to `SwarmState.budget_exhausted = True`. No further worker dispatches occur until the next night's run (budget resets via `budget_duration: 1d`). This is the only reliable control; email/Slack alerts fire on best-effort and have failed in documented incidents.

### 7.2 Per-PR token ceiling enforcement

The Claude Code `--max-turns 40` flag terminates the subprocess at 40 turns regardless of token count. The 500k input token ceiling is enforced by the per-PR LiteLLM virtual key's `max_budget` ($5 at ~$15/M input tokens for Opus ≈ ~333k tokens before editor pass savings). The no-progress detector provides a third cut: 3 tool calls without a diff kills the process before token burn compounds.

### 7.3 Dry-run gate

`services/swarm/pr_gate.py` enforces the following logic before the main dispatch loop:

1. Dispatch only `pr_specs[0]` (sorted by dependency order).
2. Poll GHA CI status on the resulting PR every 60 seconds for up to 30 minutes.
3. If CI green and critic APPROVE: set `SwarmState.dry_run_gate_passed = True`, release remaining PRs.
4. If CI red or critic REJECT: set `SwarmState.dry_run_gate_passed = False`, log to night report, exit supervisor. Human investigates in the morning.

The gate exists because a misconfigured swarm can open 10 broken PRs in 20 minutes. One wrong PR is recoverable; ten are not.

---

## 8. Git worktree lifecycle

All worktrees live under `{repo_root}/.wt/`. This directory is gitignored.

### 8.1 Create

```
git worktree add .wt/wt-{lang}-{pr_id} -b swarm/week-{N}-{pr_id}
```

- Branch is created from current `main` HEAD.
- `lang` is one of: `rust`, `py`, `ts`.
- `pr_id` is slugified from `PRSpec.pr_id` (lowercase, hyphens only).
- If the worktree directory already exists (resume scenario): check if the branch is clean vs. Postgres checkpoint. Critic decides replay vs. skip (see section 9.3).

### 8.2 Worker execution

Worker subprocess `cwd` is set to the worktree path. All file edits are scoped to the worktree. No worker ever references `{repo_root}` directly after worktree creation.

### 8.3 Commit

After L1 passes:

```bash
cd .wt/wt-{lang}-{pr_id}
git add -A
git commit -m "swarm: {pr_spec.title}

Week {N}, PR {pr_id}
L1: exit 0
Tokens: {input}/{output}"
git push origin swarm/week-{N}-{pr_id}
```

Pre-commit hook failures do not block; they result in an additional commit (never `--amend`). This preserves history for the morning reviewer.

### 8.4 PR creation (if critic approves)

```bash
gh pr create \
  --draft \
  --title "swarm: {pr_spec.title}" \
  --body "$(cat services/swarm/templates/pr_body.md.jinja2 | render)" \
  --base main \
  --head swarm/week-{N}-{pr_id} \
  --label "swarm-generated"
```

The PR body template (`services/swarm/templates/pr_body.md.jinja2`) includes:
- Link to `PRSpec.description`
- Critic verdict summary (JSON block)
- L1 exit code + truncated log
- Token count
- JSONL sidecar path for human inspection

### 8.5 Cleanup

Worktrees are cleaned up in two scenarios:

- **Critic REJECT:** `git worktree remove --force .wt/wt-{lang}-{pr_id} && git push origin --delete swarm/week-{N}-{pr_id}` immediately after REJECT verdict.
- **PR merged:** Cleanup script `scripts/swarm-cleanup-merged.sh` runs on a cron (`0 8 * * *` — 8 AM, before human review session). It runs `gh pr list --state merged --label swarm-generated` and removes corresponding worktrees + remote branches.

Leaked worktrees (process killed mid-run) are detected by `scripts/swarm-start.sh` pre-flight: any `.wt/wt-*` directory without a corresponding open PR is removed.

### 8.6 Naming conventions

| Component | Pattern | Example |
|---|---|---|
| Worktree directory | `.wt/wt-{lang}-{pr_id}` | `.wt/wt-rust-week2-case-open-tool` |
| Branch name | `swarm/week-{N}-{pr_id}` | `swarm/week-2-week2-case-open-tool` |
| Commit prefix | `swarm: ` | `swarm: Add case_open MCP tool` |
| PR label | `swarm-generated` | — |

---

## 9. Scheduler configuration

### 9.1 Nightly kickoff

`services/swarm/config/scheduler_config.yaml` (consumed by `jshchnz/claude-code-scheduler`):

```yaml
tasks:
  - name: "Find Evil nightly build swarm"
    schedule: "0 23 * * *"          # 11 PM local time, every night
    command: "bash scripts/swarm-start.sh --week auto"
    working_directory: "C:/Users/newbi/Desktop/PUG Projects/SANS-Hackathon"
    timeout_minutes: 480            # 8 hours — matches watchdog
    environment:
      ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
      LITELLM_MASTER_KEY: "${LITELLM_MASTER_KEY}"
      POSTGRES_CONN_STRING: "postgresql://swarm:swarm@localhost:5432/swarm"
      CLAUDE_CODE_FORK_SUBAGENT: "1"
    on_failure: "log"               # Do not retry — human investigates
    on_timeout: "kill"              # Hard kill; watchdog.py provides belt-and-suspenders
```

`--week auto` resolves to the current ISO week number mapped to the build plan (week 1 = Apr 22–28, ..., week 8 = Jun 10–15).

### 9.2 Pre-flight checks in swarm-start.sh

Before calling `main.py`, `scripts/swarm-start.sh` verifies:
1. Docker Compose `swarm-postgres` service is running (start if not).
2. LiteLLM proxy on port 4000 is responsive (start if not).
3. `gh auth status` exits 0.
4. `git status --porcelain` on `main` is clean (no uncommitted human edits).
5. Tonight's LiteLLM spend is $0 (budget reset confirmed — otherwise abort).
6. No `.wt/wt-*` leaked worktrees from a prior crashed run (clean them up).

### 9.3 Resume-on-restart logic

If the laptop sleeps mid-run and wakes before the next night's scheduler fires:

1. `scripts/swarm-start.sh` is called manually with `--resume`.
2. `main.py` opens the existing Postgres thread by `thread_id = "swarm-week-{N}-{date}"`.
3. `SwarmState` is loaded from checkpoint. `dispatched_pr_ids` shows what was in flight.
4. For each `pr_id` in `dispatched_pr_ids` but not in `completed_pr_ids` or `rejected_pr_ids`:
   a. `git fetch --all` to get latest remote branch state.
   b. Compare branch HEAD commit hash to the hash stored in the JSONL sidecar.
   c. If branch is ahead of checkpoint (worker committed something before sleep): critic reviews the diff as if it just completed. Skip re-running the worker.
   d. If branch matches checkpoint (worker was mid-run when sleep hit): re-dispatch the worker from scratch on the same worktree (branch is reset to main HEAD first).
5. Dry-run gate: if `dry_run_gate_passed` is already `True` in checkpoint, skip the gate and proceed with remaining PRs.

This resume protocol is sourced directly from `project_swarm_architecture.md` — Durability story, point 3.

### 9.4 Week boundary

The `--week auto` resolver in `plan_parser.py` computes: `current_week = max(1, min(8, ceil((today - date(2026, 4, 21)).days / 7)))`. If the build plan week is already fully merged (all `pr_ids` in `completed_pr_ids`), the supervisor emits a no-op night report and exits cleanly. It does not advance to the next week's PRs without an explicit `--week N+1` flag — week advancement is a human decision.

---

## 10. Monitoring

### 10.1 Structured log format

All supervisor, worker, and critic processes write structured JSON lines to `logs/swarm/{date}-{run_id}.jsonl`. One line per event. Schema:

```jsonl
{"ts": "2026-04-24T23:01:44.123Z", "run_id": "swarm-2026-04-24-w2", "component": "supervisor", "event": "plan_parsed", "week": 2, "pr_count": 3}
{"ts": "2026-04-24T23:02:10.456Z", "run_id": "swarm-2026-04-24-w2", "component": "rust_worker", "pr_id": "week2-case-open-tool", "event": "worktree_created", "path": ".wt/wt-rust-week2-case-open-tool"}
{"ts": "2026-04-24T23:14:22.789Z", "run_id": "swarm-2026-04-24-w2", "component": "rust_worker", "pr_id": "week2-case-open-tool", "event": "l1_complete", "exit_code": 0, "duration_s": 142}
{"ts": "2026-04-24T23:15:01.012Z", "run_id": "swarm-2026-04-24-w2", "component": "critic", "pr_id": "week2-case-open-tool", "event": "verdict", "decision": "APPROVE", "diff_lines": 347, "tokens_in": 18422, "tokens_out": 891}
{"ts": "2026-04-24T23:15:44.345Z", "run_id": "swarm-2026-04-24-w2", "component": "supervisor", "event": "pr_opened", "pr_id": "week2-case-open-tool", "gh_pr_number": 12, "branch": "swarm/week-2-week2-case-open-tool"}
{"ts": "2026-04-24T23:59:00.000Z", "run_id": "swarm-2026-04-24-w2", "component": "supervisor", "event": "night_complete", "prs_opened": 2, "prs_rejected": 1, "spend_usd": 11.43, "wall_clock_s": 3436}
```

Standard fields on every line: `ts` (ISO-8601 UTC), `run_id`, `component`, `event`. Additional fields are event-specific.

### 10.2 JSONL tool-call sidecar (OpenHands-style replay)

Each worker writes a separate sidecar file at `logs/swarm/sidecars/{pr_id}-tool-calls.jsonl`. One line per tool call. Schema:

```jsonl
{"ts": "2026-04-24T23:03:01.123Z", "pr_id": "week2-case-open-tool", "turn": 1, "tool": "write_file", "args": {"path": "services/mcp/src/tools/case_open.rs", "content_hash": "sha256:abc123"}, "result_summary": "wrote 87 lines", "diff_lines_delta": 87}
{"ts": "2026-04-24T23:03:44.456Z", "pr_id": "week2-case-open-tool", "turn": 2, "tool": "bash", "args": {"command": "cargo test --workspace 2>&1 | tail -20"}, "result_summary": "exit 1: error[E0502]...", "diff_lines_delta": 0}
{"ts": "2026-04-24T23:04:10.789Z", "pr_id": "week2-case-open-tool", "turn": 3, "tool": "write_file", "args": {"path": "services/mcp/src/tools/case_open.rs", "content_hash": "sha256:def456"}, "result_summary": "fixed borrow conflict, wrote 91 lines", "diff_lines_delta": 4}
```

The `diff_lines_delta` field feeds the no-progress detector: three consecutive `0` values → kill. The sidecar is the critic's primary evidence for the "no infinite pattern" check.

The sidecar format mirrors the OpenHands event-sourced replay pattern, enabling full replay of any worker run for debugging.

### 10.3 Morning status command

```bash
bash scripts/swarm-status.sh
```

Output:
- `gh pr list --label swarm-generated --state open` (shows last night's PRs)
- Last 20 lines of tonight's structured log
- LiteLLM spend query (cumulative USD for today)
- Postgres checkpoint summary (which PRs are in which state)

### 10.4 Heartbeat

The supervisor emits a heartbeat log line every 10 minutes:

```jsonl
{"ts": "...", "run_id": "...", "component": "supervisor", "event": "heartbeat", "active_workers": 2, "completed": 1, "spend_usd": 8.22, "wall_clock_s": 1200}
```

If no heartbeat appears within 15 minutes, the scheduler's `on_timeout: kill` fires. The 8-hour watchdog in `watchdog.py` provides a secondary kill path independent of the scheduler.

---

## 11. Acceptance criteria

Each criterion is testable and specific. Criteria marked **[Gate 3]** must pass before implementation of Spec #2 begins.

### Unit tests (must pass in L1 — `pytest tests/swarm/`)

- [ ] **[Gate 3]** `test_plan_parser.py`: `plan_parser.parse_week(2)` returns exactly 3 `PRSpec` objects matching the week-2 section of `BUILD_PLAN_v2.md`. `PRSpec.language` values are `["rust", "rust", "python"]`. `PRSpec.depends_on` lists are non-empty for the third item.
- [ ] **[Gate 3]** `test_worktree.py`: `worktree.create("rust", "test-pr-001")` creates `.wt/wt-rust-test-pr-001/` containing a valid git repo. `worktree.remove("rust", "test-pr-001")` removes it and leaves no orphaned git worktree reference.
- [ ] **[Gate 3]** `test_critic.py`: critic returns `CriticVerdict(decision="APPROVE")` when `WorkerResult(l1_exit_code=0, diff_line_count=150, no_progress_killed=False)` is provided. Critic returns `CriticVerdict(decision="REJECT")` when `WorkerResult(l1_exit_code=1)` or `WorkerResult(no_progress_killed=True)` is provided.
- [ ] **[Gate 3]** `test_budget.py`: mock LiteLLM spend at $51.00, call `budget.check_spend()`, assert `BudgetExhaustedError` is raised. Mock at $49.99, assert no exception.
- [ ] **[Gate 3]** `test_no_progress.py`: worker kills subprocess when `diff_lines_delta == 0` for 3 consecutive turns in sidecar. Worker does NOT kill when turn 1 is 0, turn 2 is 0, turn 3 is 5.

### Integration tests (must pass in L1 with local Postgres + mock Claude)

- [ ] **[Gate 3]** `test_resume.py`: start supervisor for `week=2`, checkpoint after dispatching first PR (simulated), kill process, restart with `--resume`, verify `SwarmState.dispatched_pr_ids` contains the first PR (loaded from Postgres) and supervisor continues without re-dispatching it.
- [ ] **[Gate 3]** `test_dry_run_gate.py`: set mock CI status to "failure" for first PR. Assert `SwarmState.dry_run_gate_passed == False` and `len(SwarmState.dispatched_pr_ids) == 1` (gate blocked remaining dispatches).

### End-to-end smoke test (manual, week 1)

- [ ] **[Gate 3]** Run `bash scripts/swarm-start.sh --week 1 --dry-run-gate --mock-workers` against the real Postgres + real LiteLLM proxy (with a $1 hard cap for the test). Verify: structured log emitted to `logs/swarm/`, sidecar created at `logs/swarm/sidecars/`, `gh pr list` shows one draft PR opened (or no PR if mock worker returns an empty diff), no worktree leaks.
- [ ] Run `bash scripts/swarm-start.sh --week 2 --dry-run-gate` with real Claude workers (not mock) against a test branch. Verify first PR opens, L1 passes on GHA, critic approves. Budget consumed < $10 for the test run.

### Operational criteria

- [ ] `docker compose -f docker/swarm-postgres.yml up -d` starts Postgres cleanly. `services/swarm/supervisor.py` calls `checkpointer.setup()` on first run without error.
- [ ] LiteLLM proxy blocks requests after $50 spend within the same `budget_duration` window (verified by setting `max_budget: 0.01` in a test config and asserting HTTP 429 on the second call).
- [ ] `scripts/swarm-status.sh` runs in under 5 seconds and outputs structured summary.
- [ ] `scripts/swarm-cleanup-merged.sh` removes all `.wt/wt-*` directories for merged PRs without affecting open or draft PRs.
- [ ] 8-hour watchdog (`watchdog.py`) kills all `claude` processes after a simulated timeout (verified with a 10-second wall-clock test config).

---

## 12. Risks and mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| W1 | **$47k ping-pong loop** (Nov 2025 LangChain incident: Analyzer/Verifier bounced for 11 days, no hard cap) | Medium | Critical | LiteLLM `max_budget: 50.0` with `budget_duration: 1d` hard-refuses calls. No-progress detector kills workers after 3 zero-diff tool calls. `--max-turns 40` terminates subagents regardless. Three independent kill paths. |
| W2 | **`cargo build`/`npm install` death spiral** (documented: 300+ `npm install` calls = 27M tokens) | Medium | High | Package manager cache layer in worker system prompt: "do not run `npm install` or `cargo build` more than once; if packages are missing, report and exit". Install commands whitelisted; worker has no privilege to bypass. |
| W3 | **Claude Code issue #43777**: subagents spawned from plan mode bypass plan-mode constraints and edit files outside scope | High | Medium | Plan mode is never used as a safety rail. Worker scope is enforced by system prompt + worktree isolation (worker cannot reach files outside worktree root). Worktree-level filesystem isolation is the real boundary. |
| W4 | **Claude Code issue #9579**: autocompact spikes tokens on long runs | High | Medium | `autocompact` disabled on all worker invocations via environment variable. `--max-turns 40` provides a hard stop regardless. |
| W5 | **PostgresSaver corruption on laptop sleep** (SQLite single-writer WAL issue on sleep/wake, documented for overnight runs) | High | High | PostgresSaver on local Docker Postgres (not SqliteSaver). Docker volume `swarm_pg_data` persists across laptop reboots. Postgres handles concurrent WAL safely. |
| W6 | **Non-deterministic parallel merges** (two workers edit the same file on the same branch) | High | Critical | One worktree per PR, one branch per PR. Workers never share a worktree. Supervisor never dispatches two workers to the same file set simultaneously. |
| W7 | **Critic false negatives** (SWE-bench data shows critics miss ~20% of bugs) | Medium | Medium | Gate requires critic AND green CI (L1 on GHA), not critic alone. Human reviews draft PR before merge. |
| W8 | **Mid-task requirement drift** (Cognition 2025: Devin fails on mid-task changes to spec) | Low | High | Week spec is locked in `PRSpec` before dispatch. No mid-run spec changes. Human edits to `BUILD_PLAN_v2.md` during a run are detected by pre-flight `git status` check; run aborted if dirty. |
| W9 | **LiteLLM proxy not running at 11 PM** (laptop restarted, Docker not auto-started) | Medium | High | `scripts/swarm-start.sh` pre-flight starts Docker Compose if not running; starts LiteLLM proxy if not responding on port 4000. Scheduler task fails loudly if pre-flight fails (logged). |
| W10 | **Week-boundary overrun** (swarm finishes week 2 PRs but opens week 3 without human approval) | Low | High | `--week auto` never advances past the current week automatically. Week N+1 requires explicit `--week N+1` flag. Human controls advancement. |

---

## 13. Budget estimate

This section covers swarm infrastructure and LLM API costs only. Product-level costs are in Spec #2.

| Line item | Calculation | Estimate |
|---|---|---|
| Claude API — nightly build (hard cap $50/night × 53 nights) | Max exposure = 53 × $50 | $2,650 worst case |
| Claude API — actual (estimate: ~$15/night on average with cache savings) | 53 × $15 | ~$795 expected |
| Postgres Docker (local, no cloud) | $0 | $0 |
| LiteLLM proxy (MIT, local daemon) | $0 | $0 |
| `jshchnz/claude-code-scheduler` | Open source, self-hosted | $0 |
| Disk (worktrees, logs, sidecars) | ~2GB per night of logs; rotate after 7 days | $0 |
| **Total swarm budget ceiling** | | **$2,650** |
| **Total swarm budget expected** | | **~$800–1,000** |

Prompt cache via `CLAUDE_CODE_FORK_SUBAGENT=1` is the primary cost lever. Workers 2 and 3 in a parallel dispatch share the parent's cache prefix, yielding ~90% reduction on children 2–N input tokens. The architect/editor model split (Opus for planning, Sonnet for editing) provides 3-5x additional cost reduction per PR.

---

## 14. Out of scope

The following are explicitly not part of this spec and will not be implemented in the swarm services:

- **Automatic merge to `main`.** The swarm opens draft PRs. Human merges. The swarm never calls `gh pr merge`.
- **L2 and L3 sandbox integration.** The swarm validates against L1 only before opening a PR. L2 (Sysbox) and L3 (QEMU) run via GHA as configured in Spec #3; the swarm does not orchestrate them.
- **Multi-repo support.** The swarm operates on a single repository: this one. No cross-repo PRs.
- **Windows-native supervisor process.** The supervisor runs inside WSL2 (or a Linux shell on the dev laptop). Windows Task Scheduler integration is handled by `jshchnz/claude-code-scheduler` which abstracts the platform.
- **Self-modifying swarm code.** Workers are never dispatched to modify `services/swarm/` itself. The `PRSpec.files_expected` field never includes files under `services/swarm/`. This is enforced by a pre-dispatch check in `dispatch.py`.
- **Slack/email alerts as primary enforcement.** Alerts may be added later as observability, but they are not a control mechanism. LiteLLM `max_budget` is enforcement; everything else is observability.
- **Cloud-hosted Postgres.** Postgres runs locally on Docker. Cloud Postgres (RDS, Supabase, Neon) is not used for the build swarm — this stays local and offline.
- **Recursive subagent spawning.** Workers are one level deep only (supervisor → worker). Workers cannot spawn sub-workers. The Claude Agent SDK limitation of one level deep is a constraint, not a workaround.
- **Concurrent workers across multiple nights.** Each night is one supervisor run, one set of PRs. No carryover dispatch to the next night within the same Postgres thread.

---

*Spec #1 is complete. Implementation begins after Gate 3 approval. Next: `2026-04-25-the-product-design.md`.*
