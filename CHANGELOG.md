# Changelog

All notable changes to the Find Evil! submission. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once the first `v0.x` is cut on the `v-submit` tag.

> **Pre-submission:** all changes below are on `master`. The first
> tagged release will be `v-submit` cut on or before the SANS Find
> Evil! deadline (2026-06-15 22:45 CDT).

## [Unreleased]

### Added — automation surface

- **`scripts/find-evil-auto`** Tesla-mode single-command orchestrator
  (commit `4b38d27`). Detects evidence type, spawns both MCP servers
  inside the SIFT VM via SSH stdio, runs the per-type playbook,
  synthesizes Pool A/B Findings, runs the full ACH stack
  (detect_contradictions → judge_findings → correlate_findings →
  judge_selfscore → manifest_finalize → ots_stamp), writes
  `verdict.json` + signed manifest + audit chain + PDF report.
  No interactive Claude Code session required.
- **`scripts/fleet_investigate.py` + `scripts/fleet_correlate.py` +
  `scripts/render_fleet_report.py`** — three-script fleet pipeline
  (commits `0de2e53` + `2403188` + `0b87b83`). Walks every `.img` in
  the evidence tree, invokes find-evil-auto per host, persists
  results after each so crashes don't lose progress, then detects
  cross-host patterns (uncommon process names on ≥2 hosts, 60s
  multi-host temporal clusters, MITRE technique density,
  Merkle-root uniqueness) and renders FLEET_REPORT.{md,html,pdf}
  with four matplotlib figures.
- **12th Rust MCP tool: `vol_psscan`** (commit `0de2e53`). Mirror of
  `vol_pslist` but invokes Volatility 3's `windows.psscan` instead.
  Critical for DKOM cross-validation against the active-list
  walker — `pslist=0` + `psscan>0` is the textbook MITRE T1014
  Rootkit signature. Spec #2 §6 enumerated 11; this brings the
  shipped count to 12.
- **`scripts/install.sh`** (commit `291828f`). Pre-flight + build
  script: detects three Claude credential modes per Amendment A1
  §3.2 (`CLAUDE_CODE_OAUTH_TOKEN` / interactive `~/.claude/` /
  `ANTHROPIC_API_KEY`), verifies cargo + uv toolchain, builds
  findevil-mcp release binary, syncs services/agent_mcp uv venv,
  sanity-checks .mcp.json registers both servers.
- **`scripts/agent-mcp-smoke.py --real-evidence` mode** (commit
  `79535e2`). Replays a real find-evil-auto case dir through the
  agent_mcp surface (audit_verify → manifest_verify →
  detect_contradictions → judge_findings → correlate_findings).
  Regression coverage proving the agent_mcp tools still parse
  production output shape after schema changes.

### Added — cryptographic chain-of-custody

- **`kind=judge_selfscore` audit records** wired end-to-end (commits
  `94c08dd` + `7729cfc` + `6f7f55a`). Per `agent-config/JUDGING.md`,
  the supervisor emits 6 audit records (one per SANS rubric
  criterion) BEFORE `manifest_finalize`. The records land in the
  audit chain → Merkle tree → sigstore signature, so the agent's
  self-score is itself part of the cryptographic attestation —
  the agent doesn't get to revise after seeing the score it got.
  Per-case `REPORT.pdf` and fleet `FLEET_REPORT.pdf` both surface
  the selfscore records with explanatory text.

### Added — documentation

- **Repo-root `README.md`** (commit `6813566`) — GitHub front page.
- **`services/agent/README.md` rewrite for A2** (commit `532b1db`).
  The package's README still described the pre-A2 architecture
  ("Hosts the LangGraph ACH graph, FastAPI SSE bus ... and CLI"),
  status table showed ⏳ Week N for components that have shipped
  under A2 (the entire crypto/ stack, mcp_client, verifier, pools,
  judge, contradiction, correlator), and "For swarm workers"
  recommended writing `findevil_agent/specialists/<name>.py` —
  which the L0 amendment-a2-guard explicitly forbids. Rewrote
  the header as "library not service under A2", bumped 15
  components ⏳→✅, added 5 strikethrough rows for the dropped
  pre-A2 modules with explicit "dropped per A2" annotations and
  L0-guard pointers, replaced the swarm-worker specialist bullet
  with explicit DO-NOT-generate guidance.
- **`docs/cryptographic-attestation.md`** (commit `08a9ff5`) — the
  five-link chain narrative (sha256 → audit prev_hash → rs_merkle →
  sigstore → OpenTimestamps Bitcoin) collected in one canonical
  doc, with FRE 902(14) prong-by-prong analysis and the negative
  test (tamper detection) live demonstration.
- **`docs/verdict-semantics.md`** (commit `16616a9`) — analyst
  triage flow for SUSPICIOUS / INDETERMINATE / NO_EVIL. Per-verdict
  triggers (verbatim from `compute_verdict`), per-verdict "what to
  do" guidance, "what the verdict does NOT mean" honesty block,
  triage flow diagram, and "when to override" pointer to the
  25-line policy in `find_evil_auto.py`.
- **`docs/demo-script-a2.md`** (commit `edf56f4`) — 5-minute
  Devpost video script with per-beat seconds, on-screen content,
  spoken narration, rubric-criterion mapping, recording mechanics.
- **`docs/false-positives.md` "Fleet cross-host correlation" entry**
  (commit `88554e1`) — documents the enterprise-AV FP trap and the
  COMMON_WIN_PROCS filter mitigation.
- **`docs/reports/2026-04-26-srl2018-dc-investigation.md` §9.1 fleet
  rollup** (commits `0c1e00b` + `f7df6c4`) — the showcase analyst
  report now references the 22-host fleet result.
- **`agent-config/JUDGING.md`** (commit `7808afd`) and rewritten
  `AGENTS.md` (commit `541e3b2`) + `TOOLS.md` (commit `5469935`).
  All 7 agent-config files now consistent with the shipped 12-tool
  MCP surface and the judge_selfscore wiring.

### Changed — accuracy

- **`fleet_correlate` known-FP filter expanded 21 → 94 entries**
  (commit `ba038c6`) covering the McAfee/Trellix endpoint stack,
  Windows infrastructure, VMware Tools, Microsoft Defender. Fleet
  correlation cross-host names dropped from 119 to 73; the "≥4
  hosts" finding list dropped from 68 to 30. Sysinternals tools
  (Autorunsc, PsExec) deliberately not filtered since cross-host
  runs of those ARE forensic findings worth analyst attention.
- **`fleet_correlate` MITRE density now counts distinct hosts**
  (commit `bf11c4d`), not findings. The earlier code reported
  T1014 = 24 on a 21-host fleet; the actual answer is T1014 = 11
  (each host can emit T1014 from both Pool A and Pool B; the
  per-host metric is what the analyst wants).

### Fixed

- **MCP tool timeout 120s → 600s with clean queue.Empty handling**
  (commit `d0f7fd5`). 120s was too tight for vol3 plugins on 5GB+
  memory images — vol_pslist alone takes 60-90s and the next call
  inherited the same budget. `vol_malfind` gets a 30-minute budget
  at the call site since it routinely exceeds 600s. Re-investigated
  base-admin (5GB DC RAM) successfully after this fix.
- **`COMMON_WIN_PROCS` drift between orchestrator and correlator**
  (commit `8638fa4`). The orchestrator's per-host filter and the
  fleet correlator's cross-host filter had separate hard-coded
  copies. Replaced the orchestrator's class attribute with a
  runtime import of `fleet_correlate.COMMON_WIN_PROCS` via
  `importlib.util` — single source of truth, no manual sync.
- **PDF render survives viewer-locked target** (commit `3170202`).
  Both render_report.py and render_fleet_report.py now Chrome-print
  to a sibling `<name>.new.pdf` and atomic-rename to the target.
  Previously, if the operator had REPORT.pdf open in Acrobat
  during a re-render, Chrome failed with "Access is denied" and the
  PDF render silently dropped. New flow leaves the .new.pdf in
  place and prints a clear warning naming both paths if the rename
  fails.
- **Demo-script Beat 6 on-screen command** (commit `102c59e`).
  The fleet-pipeline beat showed `bash scripts/find-evil-auto && …`
  but `find-evil-auto` is the single-host orchestrator and errors
  out without an evidence-path arg. Replaced with the actual fleet
  pipeline command (`fleet_investigate.py && fleet_correlate.py
  && render_fleet_report.py`) so a future re-recording doesn't
  fail mid-take. demo-script-smoke (4ddb04a) parses the beat-map
  structure not the prose, so this passed CI before — caught by
  fresh-eyes read of Beat 6.
- **Swarm invocation strings in CLAUDE.md + services/swarm/README.md**
  (commit `ec85639`). Both said `uv run python -m services.swarm.main
  --week 4 --dry-run-gate` (and `--resume` variant), but the shipped
  package is `findevil_swarm` (matches `findevil_agent` /
  `findevil_agent_mcp` / `findevil-mcp`), the CLI grew a `run`
  subcommand so bare `--week 4` no longer parses, and uv needs
  `--directory services/swarm` (or `cd` first) to find the right
  pyproject. Fixed both files to match the canonical
  `scripts/swarm-start.sh:105` invocation
  (`cd services/swarm && exec uv run python -m findevil_swarm.main
  run "$@"`); verified with `--help`. Added a 6th entry to CLAUDE.md
  "Spec/code divergences" so the next session doesn't re-litigate
  the build-swarm-plan's `services.swarm.*` import paths (~50
  references in the historical TDD plan, code shipped under
  `findevil_swarm.*` for naming consistency).
- **Cryptographic-attestation third-party verification recipe**
  (commit `43cdbdd`). `docs/cryptographic-attestation.md` "How a
  third party verifies offline" said `uv run --directory
  services/agent_mcp python -m findevil_agent_mcp.server &` followed
  by "then over MCP stdio, call manifest_verify" — backgrounding a
  stdio server with `&` disconnects it from the launching shell, so
  there's nothing to call from. Replaced with a working two-path
  recipe: (1) direct Python library call —
  `from findevil_agent.crypto.manifest import verify_manifest` —
  smoke-tested against a real case dir (overall=True, all four
  sub-checks True); (2) `scripts/agent-mcp-smoke.py --real-evidence`
  as the fuller alternative that exercises audit_verify +
  detect_contradictions + judge_findings + correlate_findings through
  the actual MCP wire. Same prose-vs-code drift shape as the Beat 6
  + swarm-invocation fixes — this one was a recipe that looked
  plausible but couldn't be executed.
- **`find_evil_auto.py` argparse prog name** (commit `6f22382`).
  `bash scripts/find-evil-auto --help` printed
  `usage: find_evil_auto.py ...` — but every doc invokes the script
  as `find-evil-auto` (the bash wrapper). One-line fix passing
  `prog="find-evil-auto"` to ArgumentParser. Usage line now matches.
  Lower impact than the previous four prose-vs-code fixes (cosmetic
  rather than executable bug) but same drift shape — doc name vs
  self-reported name. The other four argparse scripts in scripts/
  (fleet_investigate, fleet_correlate, render_report,
  render_fleet_report) are invoked directly as
  `python scripts/<name>.py` so their default prog matches; left
  alone.
- **`11 → 12` Rust MCP tool count downstream sweep**
  (commit `e6ddc2d`). Same divergence-sweep procedure as 782f364,
  applied to CLAUDE.md "Spec/code divergences" §4. The earlier
  11→12 sweep (6cba0cd) had hit the architecture diagram +
  QUICKSTART + PLAYBOOK but missed four more downstream usages:
  docs/architecture.md:263 (pre-A2-vs-A2 comparison table),
  docs/reports/2026-04-26-srl2018-dc-investigation.md:231
  (§8.1 in the showcase analyst report — a SANS judge would have
  seen "11" there and "12" in CLAUDE.md and wondered which is
  correct), docs/templates/devpost-readme.md:35 (Devpost
  submission template, envsubst'd at v-submit), and
  scripts/sift-vm-setup.sh:6 (the script header). Re-rendered
  the showcase report's HTML+PDF since judges read the PDF
  artifact, not the markdown source. Same pandoc + chrome
  --headless recipe as f7df6c4. PDF grew from 1325101 to 1594607
  bytes (different Chrome build embeds fonts more aggressively;
  content delta is one sentence + one parenthetical). Process
  win: documenting a divergence + applying the sweep is now a
  repeatable two-step workflow.
- **`find-evil verify` / `find-evil run` downstream sweep**
  (commit `782f364`). Last iteration's lesson said "when a
  divergence is documented, sweep for downstream usages." Applied
  to the A2/cli.py drop in §3, found 5 more broken references:
  scripts/l3-run-goldens.sh:153 SSH'd `find-evil run` into the
  SIFT VM (replaced with `bash scripts/find-evil-auto` — the
  surviving A2 orchestrator); services/agent/findevil_agent/crypto/
  audit_log.py + merkle.py + __init__.py docstrings all referenced
  `find-evil verify` as the offline-verification path (replaced
  with pointers to `verify_manifest` + the `manifest_verify` MCP
  tool); docs/DATASET.md:177 used `find-evil verify <manifest>` as
  the reproducibility recipe (replaced with a pointer to
  docs/cryptographic-attestation.md). Also extended CLAUDE.md
  "Spec/code divergences" §3 to flag a sixth broken reference:
  `scripts/build-deb.sh:57` inlines the same dropped
  `findevil_agent.cli` wrapper into the .deb postinst, and line 96
  tells the user to run `find-evil run` — both broken under A2.
  Did NOT unilaterally fix build-deb.sh; same hard-blocker class as
  the Dockerfile (architectural decision pending). Verified:
  6/6 smokes pass; 156/156 agent tests pass.
- **CLAUDE.md "Python agent + swarm" Commands section drift**
  (commit `93a9def`). Five drifts caught by attempting the
  documented commands literally: `uv sync` from repo root claimed
  "root pyproject.toml is a uv workspace" but there is none (verified
  errors "No pyproject.toml found"); `uv run pytest -xvs --cov` from
  repo root collects 156 tests but errors on swarm imports without
  the service-specific deps; `tests/swarm/test_package_imports.py`
  doesn't exist (the actual tree is `services/swarm/tests/`);
  `tests/agent/test_graph_smoke.py::test_kill_resume_restores_state`
  doesn't exist either (was part of the pre-A2 graph.py the L0
  amendment-a2-guard now forbids); the "Run the agent graph
  directly (dev)" entry pointed at
  `python -m findevil_agent.cli run --case ...` — but A2 dropped
  `findevil_agent/cli.py`. Fixed all five with commands that
  actually execute (`uv run --directory services/agent pytest
  tests/test_crypto_audit_log.py::TestCanonicalize::test_sorted_keys
  -v` verified runs + passes). Also brought the line-99
  Repo-layout footer's Dockerfile reference in line with the
  "Spec/code divergences" §3 caveat already in the same file.
  Same drift shape as the previous seven prose-vs-code fixes;
  internally-consistent because the A2 caveat that flagged this
  was *already* in CLAUDE.md - just the dev-command examples
  hadn't been rewritten to match.
- **`scripts/find-evil-sift` `claude-code` remnant** (commit
  `cc4e93e`). The earlier `claude-code → claude` sweep (c167aec)
  used grep filters `--include="*.sh"`, which missed
  `scripts/find-evil-sift` (no extension). The script's launch path
  ran `command -v claude-code` first, then fell back to `claude .` —
  both passing `.` as a positional arg, which `claude` treats as a
  prompt not a directory. Simplified to a single `claude` check
  with no positional arg (script already cd's to repo root).
  Logged the lesson in the autonomous-queue: extension-less shell
  scripts (the `find-evil` family deliberately drops `.sh` to read
  like CLI tools) need to be in the audit grep too.
- **`claude-code` → `claude` across the Product entry path**
  (commit `c167aec`). The Anthropic Claude Code CLI binary is
  `claude`, not `claude-code`. The repo had `claude-code` everywhere
  including in the **actual executable** `scripts/find-evil` (the
  Product entry point judges run): `command -v claude-code` +
  `exec claude-code . "$@"`. Verified — `which claude-code` returns
  non-zero on this system, `which claude` resolves to
  ~/.local/bin/claude. Following the documented recipe verbatim
  (`bash scripts/find-evil` OR `claude-code .`) would have errored
  "command not found". Also: `claude` doesn't take a positional path
  arg (per `claude --help`); it uses cwd. The trailing `.` was
  wrong in either form. Surgical sweep across 8 active files:
  scripts/find-evil (3 spots), scripts/install.sh (stdout instruction),
  README.md, QUICKSTART.md, CLAUDE.md (3 refs), docs/architecture.md
  (4 refs), docs/demo-script-a2.md (recording playbook),
  docs/templates/devpost-readme.md. Deliberately untouched: filenames
  with `claude-code` (amendment doc names like
  `claude-code-mode.md`), the third-party `claude-code-scheduler`
  project name, the `docs.anthropic.com/.../claude-code/install` URL
  path, the test-fixture string in test_session_guard.py (tests a
  regex that matches "rate limit exceeded" globally; CLI-name prefix
  is illustrative not load-bearing). Highest-impact prose-vs-code
  drift caught this session — previous three fixes were doc-only;
  this one broke the Product's actual entry-point script. Caught by
  attempting `which claude-code` after auditing the doc references.

### Operator UX

- **find_evil_auto pre-flight SSH/VM check** (commits `9816585` +
  `244f5e7`). A judge running `bash scripts/find-evil-auto <path>`
  without a configured SIFT VM previously got a Python stack trace
  deep in the SSH stdio reader thread. Now `preflight_check()` runs
  at the top of `main()`: verifies SSH key exists, SSHes into the
  VM with a 10s ConnectTimeout, and probes all three MCP server
  prerequisites in one round-trip — Rust binary + agent_mcp dir +
  uv binary. Failure → exit 2 with the exact ssh command attempted,
  exit code, stderr tail, an enumeration of the three required
  paths so the operator spots which one is wrong, and a three-line
  remediation playbook (first time / VM down / alt host) pointing
  at scripts/sift-vm-bootstrap.sh and the
  FIND_EVIL_GUEST_IP/USER/REPO env vars. `--skip-preflight` flag
  added so fleet_investigate.py doesn't re-check the same VM 22
  times per fleet run.

### Documentation

- **Rust toolchain pin alignment** (commits `f61860d` + `6902bd0`
  + `f429894`). Cargo.toml line-13 comment said "Pinned toolchain
  is Rust 1.83" right next to a [workspace.package] block
  correctly stating "Rust 1.88". Subsequent grep audit found the
  same staleness in four more places: Dockerfile FROM line
  (`rust:1.83-bookworm` → would have failed `docker build` once
  rust-toolchain.toml's 1.88.0 took effect via rustup pull),
  sandbox-plan §Task 2 scope text + planned commit-message
  template, product-plan Tech Stack line + Task 31 instruction.
  All five places now read 1.88 with pointers to CLAUDE.md
  "Spec/code divergences" §1; only the historical CHANGELOG
  reference describing what the OLD Cargo.toml said remains as
  audit-trail.
- **`rmcp` hand-rolled divergence flagged in CLAUDE.md** (commit
  `e89848d`). Spec #2 §4.1 lists `rmcp 0.16.x` as the MCP server
  framework; we ship a hand-rolled stdio JSON-RPC 2.0
  implementation in `services/mcp/src/server.rs` instead (chosen
  for wire-format stability across rmcp churn + dispatch-shape
  parity with the Python `findevil-agent-mcp`). The deliberate
  omission was visible only in `services/mcp/Cargo.toml` line 27
  (commented-out rmcp line) and `services/mcp/README.md`'s NB
  note — neither was guaranteed reading. CLAUDE.md "Spec/code
  divergences" now has a 5th entry making the architectural
  choice load-bearing across the codebase: a future contributor
  cleaning up commented code can no longer silently re-introduce
  the dep.

### Hard blockers discovered

- **Dockerfile A2 cli.py mismatch** (commit `47f67b0`). The
  shipped `Dockerfile`'s `find-evil` wrapper invokes
  `python3 -m findevil_agent.cli` — but Amendment A2 dropped
  `services/agent/findevil_agent/cli.py` (the L0
  `amendment-a2-guard` job fails CI if it reappears). The .deb
  package would error at first invocation. Two architectural paths
  forward: (a) rewrite the wrapper to invoke
  `scripts/find-evil-auto` in Tesla mode against the SIFT VM, or
  (b) cut the `find-evil` wrapper entirely since A2's "Claude
  Code IS the orchestrator" makes the in-container CLI redundant
  (the .deb becomes documentation + CI artifacts only).
  Architectural choice; flagged as a hard blocker pending user
  resolution before the `v-submit` tag is cut.
- **QUICKSTART.md inbound links** (commit `e3677c4`) to the two
  analyst-facing canonical docs (`verdict-semantics.md` +
  `cryptographic-attestation.md`). Step 5/6 of the find-evil-auto
  walkthrough now point at the verdict triage flow and the
  offline-verification recipe; the "Recommended reading order"
  table gains two new rows for "what do the verdicts mean?" and
  "how does the chain-of-custody work?". Both docs now reachable
  from all three top-level entry points (README + QUICKSTART +
  CLAUDE.md).

### CI

- **L1 now runs both MCP smoke harnesses end-to-end** (commit
  `ed3c35c`). `docker/l1-compose.yml`'s command sequence gained
  steps that run `scripts/rust-mcp-smoke.py` (12-tool dispatch +
  error-path checks) and `scripts/agent-mcp-smoke.py` (synthetic-
  Findings flow through the full demo path). Catches a class of
  integration drift unit tests miss — dispatcher/registry mismatch,
  ToolAnnotations bool flip, etc. Estimated CI cost ~20s, well
  within L1's 2-5min budget.
- **L0 amendment-A2 guard already in place** from earlier session
  (commit `ad4a36e`). Fails CI if any of the dropped pre-A2
  modules (graph.py / api.py / cli.py / supervisor.py /
  specialists/) reappear under any filename.
- **Policy-lock smokes for compute_verdict + fleet_correlate +
  detect_evidence_type** (commits `b0a9a2e` + `395e2b6` +
  `62b3fdf`). Two CI assertions covering load-bearing policy that
  was previously documented but unverified.
  `scripts/verdict-policy-smoke.py` (27 cases) asserts: the
  SUSPICIOUS / INDETERMINATE / NO_EVIL triggers in
  `compute_verdict` match `docs/verdict-semantics.md` (11 cases
  including a regression anchor for the real SRL-2018 base-rd-05
  finding shape — 2 HYPOTHESIS → INDETERMINATE), AND the
  `detect_evidence_type` dispatch (16 cases covering all 6
  memory extensions, evtx, 6 disk variants including .E01
  case-insensitivity and .001 split-image, and 3 unknown
  including the deliberate non-routing of .zip Velociraptor
  bundles).
  `scripts/fleet-policy-smoke.py` (46 cases — commits `925725e` +
  `31a03f3` + `682a5bd` + this iteration each added 4-7 cases on
  top of the original 28) asserts: `normalize_image_name` 14-char
  Volatility-truncation behavior; `COMMON_WIN_PROCS` filter
  coverage of the McAfee/Trellix + VMware Tools + Windows
  infrastructure stack with deliberate Sysinternals exclusions
  per `docs/false-positives.md`; `cross_host_processes` end-to-end
  filter+threshold behavior; `temporal_clusters` 60s-window
  multi-host detection (anchored against the SRL-2018 Autorunsc-
  on-multiple-hosts pattern that headlines `FLEET_REPORT.pdf`);
  `mitre_density` distinct-host counting (regression anchor for
  bug fix in commit `bf11c4d` that prevented counting Pool A +
  Pool B as 2 hosts); `merkle_uniqueness` duplicate-root detection
  (anchor for the fleet.json patch mistake earlier this session
  that pointed two hosts at the same case_dir); `selfscore_aggregate`
  modal-answer + distinct-answers logic. Both smokes load the
  target functions via `importlib` so they assert against shipped
  logic — no copy-paste of policy. ~150ms wall-clock combined;
  wired into `docker/l1-compose.yml` after the agent-mcp-smoke
  step.
- **`scripts/demo-script-smoke.py` locks the 5:00 demo timing**
  (commit `4ddb04a`). `docs/demo-script-a2.md` encodes the Devpost
  video plan as 9 beats with explicit start/end timestamps in a
  markdown table; a future contributor editing one beat without
  adjusting adjacent ones could silently break the timing. The
  smoke parses the `## Beat map` table (handles U+2013 em-dash
  separator), asserts 9 contiguous beats numbered 1-9 starting at
  0:00 and ending at 5:00, length-column = end-start, sum of
  lengths = 300s. ~30ms wall-clock; wired into
  `docker/l1-compose.yml` after fleet-policy-smoke. CI now runs
  three policy-lock smokes per L1 build (~180ms total).
- **`scripts/run-all-smokes.sh` — local-iteration smoke runner**
  (commits `cecef5d` + `f7ff81f` for TTY detection). Single
  command for the 5 L1 smokes outside docker, in the same order
  docker/l1-compose.yml runs them. Per-smoke ✓/✗/SKIP status with
  prereq checks (clean SKIP if `target/release/findevil-mcp`
  missing or `services/agent_mcp/` absent rather than confusing
  failure), final tally, and remediation footer naming `cargo
  build --release -p findevil-mcp` and `uv sync --extra dev` if
  anything fails. ANSI color codes are gated on `[ -t 1 ]` so
  CI-captured logs and Windows-cmd-without-VT output stays plain
  ASCII. ~25s wall-clock combined (dominated by the two MCP-server
  spawn smokes). Closes the local-iteration friction gap for a
  developer changing `compute_verdict`, fleet_correlate logic,
  or the demo script.
- **`scripts/launcher-smoke.py` locks the 6-iteration prose-vs-code
  audit findings** (commit `0155503`). Six bugs across three shapes
  were caught by ad-hoc audit (102c59e Beat 6, ec85639 swarm
  invocations, 43cdbdd crypto recipe, c167aec claude-code → claude
  the catastrophic one, 6f22382 argparse prog, cc4e93e extension-
  less remnant). The smoke now locks all three shapes: bash -n on
  every shell launcher in scripts/ (extension-less + *.sh — the
  find-evil family deliberately drops .sh, so the glob is explicit);
  no bare or `command -v` `claude-code` invocations (catches the
  c167aec class); no `claude .` positional-arg invocations (catches
  the cc4e93e class). 22 launchers x 3 checks = 66 assertions;
  ~50ms. Negative-tested with synthetic fixtures - both bad-binary
  and bad-invocation patterns fire. Wired into docker/l1-compose.yml
  as the 6th L1 smoke and scripts/run-all-smokes.sh as the 6th
  run-all entry. QUICKSTART table updated 5 → 6 smokes. First lock
  protecting against doc/code drift in shell scripts (the prior
  five locks all protected Python data-shape policy).

### Real-evidence runs

- **22-host SRL-2018 fleet investigation completed** (artifact:
  `tmp/fleet-runs/fleet-20260426T055440Z/`). 12 SUSPICIOUS, 10
  INDETERMINATE, 0 NO_EVIL. 22/22 unique Merkle roots — chain
  integrity intact across the fleet. 11/22 hosts show T1014
  (DKOM/Rootkit), 9/22 show T1055 (Process Injection). Headline
  cross-host patterns: 6 hosts ran `Autorunsc.exe` at the *exact
  same second* (cluster 1 in `temporal_clusters.png` — automated
  recon sweep fingerprint), `rubyw.exe` on 13 hosts and `ruby.exe`
  on 12 (Ruby for Windows is not standard enterprise tooling),
  `msadvapi2_32.e` and `msadvapi2_64.e` on 8 hosts each
  (name-spoofing the legitimate `advapi32.dll`).

---

*This changelog is updated as commits land on `master`. The
`v-submit` tag will be cut by `package-devpost.sh` on or before
2026-06-15 22:45 CDT and will template-substitute the demo video
URL, accuracy benchmark score, and final commit SHA into
`docs/templates/devpost-readme.md`.*
