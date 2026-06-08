---
date: 2026-06-08
description: VERDICT repo commands + the obsidian-mind memory-curation commands (trimmed to DFIR-memory-only — no perf/HR/Slack modules).
tags: [brain, index]
---

# Skills

This vault is trimmed to **DFIR project memory** — the upstream obsidian-mind perf-review,
org/people, 1:1, and Slack modules were removed. What remains: the VERDICT repo commands, the
generic memory-curation commands, and the QMD search machinery.

## VERDICT repo commands (the project this vault remembers)

Run these from the repo root (`/home/assessor/Desktop/PUG-Projects/sans-hackathon`):

| Command | Purpose |
|---------|---------|
| `scripts/verdict <evidence>` | THE entry point — preflight → investigate → dashboard → signed verdict + report. Flags: `--sift`, `--watch`, `--no-dashboard`, `--unattended`, `--run-summary`. |
| `claude` then `investigate <path>` | Interactive investigation (same tools). |
| `bash scripts/setup` / `bash scripts/install.sh` | First-run onboarding / build (Rust MCP + Python venv + DFIR tools). |
| `bash scripts/doctor.sh [--json]` | Dependency readiness gate. |
| `bash scripts/install-dfir-tools.sh` | Install the 8 external DFIR binaries into `~/.local/bin`. |
| `SKIP_SLOW_RUST=1 bash scripts/run-all-smokes.sh` | Local CI predictor (not a live test). |
| `python scripts/fleet_investigate.py` → `fleet_correlate.py` → `render_fleet_report.py` | 3-stage fleet pipeline. |
| `bash scripts/make-demo-video.sh` | Render the Devpost demo video (Remotion + Piper TTS). |

Full catalog: `docs/using/running-verdict.md`, `docs/live-test-matrix.md`. Tool/MCP/dependency
inventory: `docs/reference/`. Memory boundary: never run repo investigation tools "to remember" —
memory and evidence are separate ([[Key Decisions#Memory is never evidence]]).

## obsidian-mind curation commands (`.claude/commands/`)

| Command | Purpose |
|---------|---------|
| `/om-standup` | Morning kickoff — load context (North Star, active work, recent git), surface priorities |
| `/om-dump` | Freeform capture — dump anything, auto-routed to the right `brain/`/`work/` note |
| `/om-wrap-up` | Full session review — verify notes, indexes, links; reindex. Auto-triggered on "wrap up" |
| `/om-weekly` | Weekly synthesis — cross-session patterns, North Star alignment |
| `/om-humanize` | Voice-calibrated editing — make Claude-drafted notes read naturally |
| `/om-vault-audit` | Structural audit — indexes, frontmatter, links, orphans, stale context |
| `/om-vault-upgrade` | Import content from another vault (detect version, transform frontmatter, rebuild indexes) |
| `/om-project-archive` | Move a completed project from `work/active/` to `work/archive/YYYY/`, update indexes |

## Subagents (`.claude/agents/`)

| Agent | Purpose | Invoked by |
|-------|---------|------------|
| `context-loader` | Load all vault context about a project or concept | Direct — "load context on X" |
| `cross-linker` | Find missing wikilinks, orphans, broken backlinks | `/om-vault-audit` |
| `vault-librarian` | Deep vault maintenance — orphans, broken links, frontmatter, stale notes | `/om-vault-audit` |
| `vault-migrator` | Classify/transform/migrate content from a source vault | `/om-vault-upgrade` |

## Hooks (`.claude/settings.json`, vault-native sessions)

| Hook | When | What |
|------|------|------|
| SessionStart | On startup/resume | QMD re-index, inject North Star + brain-topic index + active work + recent changes |
| UserPromptSubmit | Every message | Classify content (decision, gotcha, pattern, project update) and inject routing hints |
| PostToolUse | After writing `.md` | Validate frontmatter, check for wikilinks |
| PreCompact | Before context compaction | Back up session transcript to `thinking/session-logs/` |
| Stop | End of session | Checklist: update indexes, check orphans |

## Semantic Search (QMD)

QMD (`npm install -g @tobilu/qmd`, under Node 22) gives the vault semantic search. The index is
`verdict-memory` (`vault-manifest.json` → `qmd_index`):

- `qmd --index verdict-memory query "..."` — hybrid BM25 + vector + LLM reranking (best, slow)
- `qmd --index verdict-memory search "..."` — fast BM25 keyword search
- `qmd --index verdict-memory vsearch "..."` — semantic vector search (no rerank)

In a session the same store is exposed as `mcp__qmd__query` / `get` / `multi_get` (registered at
local scope). First-time/refresh: `node --experimental-strip-types scripts/qmd-bootstrap.ts`. See
[[Memories]] for the topics QMD is most often asked to find.

Related: [[North Star]] · [[Memories]] · [[Patterns]]
