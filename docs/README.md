# docs/

Index of project documentation. The authoritative *precedence* hierarchy lives in `CLAUDE.md` "Document hierarchy" — this file just makes the per-file purposes scannable for both humans and future Claude Code sessions navigating the tree.

## Top-level docs (in `docs/`)

| File | Purpose |
|---|---|
| `architecture.md` | Devpost Required Component #3. Trust-boundary diagram + runtime architecture under Amendment A2. The single page judges reach first. |
| `cryptographic-attestation.md` | The five-link chain-of-custody story (rubric criterion #5). How `manifest_verify` + `ots_verify` produce FRE 902(14) self-authenticating evidence. |
| `DATASET.md` | Devpost Required Component #5. Every fixture the agent was tested against, with SHA-256 + license + expected findings. |
| `demo-script-a2.md` | 5-minute Devpost demo video script (A2 flow). Pre-flight checklist + per-beat narration + rubric mapping. Supersedes the pre-A2 demo flow in `BUILD_PLAN_v2.md §9`. |
| `false-positives.md` | Operator's guide. Three architectural FP layers + four operational habits + per-tool FP risk table. |
| `verdict-semantics.md` | Analyst-facing meaning of `SUSPICIOUS` / `INDETERMINATE` / `NO_EVIL`; mirrors `compute_verdict` in `scripts/find_evil_auto.py`. |

## Subfolders

- **`superpowers/specs/`** — 7 specs: master design + Amendment A1 + Amendment A2 + 4 numbered subsystem specs (sandbox, build-swarm, product, glue). Read `CLAUDE.md` "Document hierarchy" for precedence; later amendments override earlier specs only where explicitly noted.
- **`superpowers/plans/`** — 4 TDD plans, one per subsystem spec. Each task is a checkbox with the failing-test → implement → commit sequence.
- **`runbooks/`** — three procedural runbooks:
  - `ci-smoke-checklist.md` — end-to-end pipeline verification before submission
  - `dockerfile-a2-decision.md` — open hard blocker (Dockerfile `find-evil` wrapper references the dropped `findevil_agent.cli` module)
  - `github-remote-bootstrap.md` — open hard blocker (Devpost requires a public GitHub repo URL)
- **`templates/`** — `devpost-readme.md` (the README template that ships in the v-submit bundle, populated by release CI).
- **`references/`** — `protocol-sift-integration-reference.md` (external Protocol SIFT material; not authoritative — see `CLAUDE.md` "External 'Protocol SIFT' reference" for the reconciled contradictions). Embedded screenshots live in `references/figures/`.
- **`reports/`** — investigation reports + figures. Currently: `2026-04-26-srl2018-dc-investigation` (22-host fleet investigation, embedded `figures-2026-04-26/` set, .md + .html + .pdf renderings).

## Related docs outside `docs/`

- `CLAUDE.md` (repo root) — agent instructions, document hierarchy, non-negotiable invariants, spec/code divergences. Always loaded.
- `README.md` (repo root) — public-facing project landing page.
- `QUICKSTART.md` (repo root) — three-step quickstart for impatient users.
- `BUILD_PLAN_v2.md` (repo root) — 9-week roadmap; partially superseded by Amendment A2 (see the prominent "Superseded sections" warning at top).
- `CHANGELOG.md` (repo root) — chronological project changelog.
- `SUBMISSION_NOTES.md` (repo root) — stub; edit before cutting `v-submit` tag.
- `Find_Evil_Research_and_Build_Plan.docx` (repo root) — v1 research doc; authoritative only for what v2 doesn't contradict.
- `agent-config/` (repo root) — runtime DFIR agent identity files (SOUL, AGENTS, TOOLS, MEMORY, HEARTBEAT, JUDGING, PLAYBOOK). Read by the agent at investigation start.
