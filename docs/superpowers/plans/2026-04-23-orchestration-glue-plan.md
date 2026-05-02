# Orchestration Glue Implementation Plan

> **Status: RETIRED.** The work this plan tracked shipped in `.github/workflows/` (l0/l1/l2/l3 + release + competitor-watch + devpost-submit + budget-guard) plus `scripts/package-devpost.sh`. The `scripts/build-deb.sh` task was cut by Amendment A2 (PR #4). Kept for git-log archaeology. **Do not execute as a TDD plan.** If extending CI, work against the live workflow YAMLs and the spec at `docs/superpowers/specs/2026-04-26-orchestration-glue-design.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the thin CI pipeline that ties the build swarm, the Product, and the test sandbox together — nightly L3 golden runs, weekly releases, competitor monitoring, Devpost submission automation.

**Architecture:** Nine GitHub Actions workflow files + supporting scripts. Release workflow gates on L3 green. Leaderboard pushes to findevil-bench.dev. Weekly competitor-watch + daily budget-guard dead-man's switch. Devpost zip auto-packaged on v-submit tag cut by 2026-06-14.

**Tech Stack:** GitHub Actions, gh CLI, bash, Python (for json-to-csv script), curl. No new language runtimes.

---

## Preamble: Source Specs (Read First)

Before starting any task, read these in order:

1. `docs/superpowers/specs/2026-04-26-orchestration-glue-design.md` — Spec #4 (authoritative for this plan)
2. `docs/superpowers/specs/2026-04-23-amendment-option-b-claude-code-mode.md` — Amendment A1 §5 governs Task 10 (budget-guard is no-op unless `ANTHROPIC_API_KEY` repo secret is set)
3. `docs/superpowers/specs/2026-04-23-layered-test-sandbox-design.md` — Spec #3 §4.4 is the contract for `scripts/l3-run-goldens.sh` consumed by Task 2

**Option-B invariants for this plan:**
- Task 10 (`budget-guard.yml`) MUST short-circuit to exit 0 with message `"Option B mode — no metered API in use"` when the `ANTHROPIC_API_KEY` repo secret is absent.
- All other workflows pass `ANTHROPIC_API_KEY` through from secrets if present (L3 needs it for judge-parity mode per Amendment §4); no workflow hard-fails solely on its absence except `budget-guard.yml`'s metered branch, which is only reached when the secret exists.
- No LiteLLM `/spend` endpoint is queried anywhere — that path from the original Spec #4 §10 is replaced.

**Conventions used below:**
- All paths absolute from repo root (`C:\Users\newbi\Desktop\PUG Projects\SANS-Hackathon\...`) in commands; in-repo file references use POSIX repo-relative paths.
- Every task is TDD: write failing test → run test and capture RED output → implement → run test and capture GREEN output → commit.
- Workflow tests use `actionlint` (static) and `act` (local run) for pre-push verification; end-to-end integration is covered by Task 17.
- Commit messages follow `<type>(<scope>): <subject>` with Conventional Commits prefixes (`feat`, `test`, `chore`, `docs`, `fix`).

---

## Task 1: Repository LICENSE file (Apache-2.0)

**Files touched:** `LICENSE` (new)

**Why first:** Required by Spec #4 §9 Devpost zip contents AND AC "LICENSE contains the full Apache-2.0 text". Blocks Task 12.

- [ ] **1.1 Write failing test.** Create `tests/orchestration/test_license.sh`:
    - Assert file `LICENSE` exists at repo root.
    - Assert `grep -q "Apache License" LICENSE` succeeds.
    - Assert `grep -q "Version 2.0, January 2004" LICENSE` succeeds.
    - Assert `wc -l < LICENSE` returns ≥ 200 (full text is 202 lines).
    - Assert `sha256sum LICENSE | awk '{print $1}'` equals `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` (canonical Apache-2.0 SHA-256).
- [ ] **1.2 Run test — expect RED.** Command: `bash tests/orchestration/test_license.sh`. Expected stderr ending: `FAIL: LICENSE file not found`. Exit code: `1`.
- [ ] **1.3 Implement.** Download the canonical Apache-2.0 text:
    ```
    curl -fsSL https://www.apache.org/licenses/LICENSE-2.0.txt -o LICENSE
    ```
    Verify with `sha256sum LICENSE` — expect `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`.
- [ ] **1.4 Run test — expect GREEN.** Command: `bash tests/orchestration/test_license.sh`. Expected stdout final line: `PASS: LICENSE ok (202 lines, sha256 matches)`. Exit code: `0`.
- [ ] **1.5 Commit.** `git add LICENSE tests/orchestration/test_license.sh && git commit -m "chore(repo): add Apache-2.0 LICENSE at repo root"`.

---

## Task 2: `.github/workflows/l3-nightly.yml`

**Files touched:** `.github/workflows/l3-nightly.yml` (new), `tests/orchestration/test_l3_nightly_workflow.sh` (new)

**Depends on:** Spec #3 §4.4 `scripts/l3-run-goldens.sh` contract (external — assumed present from Spec #3 plan output). Task 3 provides `scripts/push-leaderboard-score.sh`; this workflow calls it but testing is isolated via `actionlint` static checks only.

- [ ] **2.1 Write failing test.** `tests/orchestration/test_l3_nightly_workflow.sh` asserts:
    - File `.github/workflows/l3-nightly.yml` exists.
    - `actionlint .github/workflows/l3-nightly.yml` exits 0.
    - `yq '.on.schedule[0].cron' .github/workflows/l3-nightly.yml` returns `30 2 * * *`.
    - `yq '.on.push.branches[0]' .github/workflows/l3-nightly.yml` returns `main`.
    - `yq '.jobs.goldens.runs-on' .github/workflows/l3-nightly.yml` returns `ubuntu-latest-4-core-kvm`.
    - `grep -q "scripts/l3-run-goldens.sh" .github/workflows/l3-nightly.yml` succeeds.
    - `grep -q "scripts/push-leaderboard-score.sh" .github/workflows/l3-nightly.yml` succeeds.
    - `grep -q "SLACK_WEBHOOK_CI" .github/workflows/l3-nightly.yml` succeeds.
- [ ] **2.2 Run test — expect RED.** `bash tests/orchestration/test_l3_nightly_workflow.sh`. Expected: `FAIL: .github/workflows/l3-nightly.yml not found`. Exit: `1`.
- [ ] **2.3 Implement `.github/workflows/l3-nightly.yml`.** Jobs:
    - `goldens` (runs-on: `ubuntu-latest-4-core-kvm`): checkout, restore Packer warm-image cache, run `bash scripts/l3-run-goldens.sh`, upload `run.log` as `l3-verdicts` artifact.
    - `push-score` (needs: goldens, if: `success()`): download `l3-verdicts`, run `bash scripts/push-leaderboard-score.sh --run-log run.log --release false` with `LEADERBOARD_API_KEY` secret in `env:`.
    - `alert-on-fail` (needs: goldens, if: `failure()`): posts to `SLACK_WEBHOOK_CI` using `curl -X POST -H 'Content-type: application/json' --data '{"text":"[find-evil CI] l3-nightly | FAIL | ${{ github.sha }} | ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"}' $SLACK_WEBHOOK_CI`.
    - Top-level `permissions: { contents: read, actions: read }`.
    - `concurrency: { group: l3-nightly, cancel-in-progress: false }`.
- [ ] **2.4 Run test — expect GREEN.** `bash tests/orchestration/test_l3_nightly_workflow.sh`. Expected final line: `PASS: l3-nightly.yml structure ok`. Exit: `0`.
- [ ] **2.5 Commit.** `git add .github/workflows/l3-nightly.yml tests/orchestration/test_l3_nightly_workflow.sh && git commit -m "feat(ci): add l3-nightly workflow with leaderboard push and slack alert"`.

---

## Task 3: `scripts/push-leaderboard-score.sh` + test

**Files touched:** `scripts/push-leaderboard-score.sh` (new), `tests/orchestration/test_push_leaderboard_score.sh` (new), `tests/orchestration/fixtures/run.log.sample.json` (new)

**Contract:** Spec #4 §7 — reads `run.log` JSON produced by `scripts/l3-run-goldens.sh`, POSTs to `https://findevil-bench.dev/api/scores` with bearer auth.

- [ ] **3.1 Create fixture.** `tests/orchestration/fixtures/run.log.sample.json` — exact copy of the three-case example payload from Spec #4 §7 (nist-hacking-case, otrf-apt3-mordor, synthetic-benign), wrapped at the top level with the fields `cases` and `aggregate` only (i.e. the `run.log` format produced by L3).
- [ ] **3.2 Write failing test.** `tests/orchestration/test_push_leaderboard_score.sh`:
    - Stub `curl` by prepending a test-only `PATH` directory containing a fake `curl` that writes `$@` to `/tmp/curl-call.txt` and exits 0.
    - Run: `LEADERBOARD_API_KEY=testkey123 COMMIT_SHA=abcdef1234567890abcdef1234567890abcdef12 GITHUB_RUN_ID=999 bash scripts/push-leaderboard-score.sh --run-log tests/orchestration/fixtures/run.log.sample.json --release false`.
    - Assert `/tmp/curl-call.txt` contains `-X POST`.
    - Assert it contains `https://findevil-bench.dev/api/scores`.
    - Assert it contains `Authorization: Bearer testkey123`.
    - Assert the JSON body passed (via `--data @-` or `--data`) parses with `jq` and has: `.submitter == "find-evil"`, `.commit_sha == "abcdef1234567890abcdef1234567890abcdef12"`, `.run_id == "999"`, `.release == false`, `.release_tag == null`, `.cases | length == 3`, `.aggregate.accuracy` numeric.
    - Additionally run with `--release true --tag v5` and assert `.release == true && .release_tag == "v5"`.
    - Assert that if `curl` exits non-zero, the script exits 0 (non-blocking) but prints `WARN: leaderboard push returned non-2xx` to stderr.
- [ ] **3.3 Run test — expect RED.** `bash tests/orchestration/test_push_leaderboard_score.sh`. Expected: `FAIL: scripts/push-leaderboard-score.sh not found`. Exit: `1`.
- [ ] **3.4 Implement `scripts/push-leaderboard-score.sh`.**
    - Shebang `#!/usr/bin/env bash`, `set -euo pipefail`.
    - Flags: `--run-log <path>` (required), `--release <true|false>` (required), `--tag <string>` (required iff `--release true`).
    - Read env: `LEADERBOARD_API_KEY`, `COMMIT_SHA` (fallback `git rev-parse HEAD`), `GITHUB_RUN_ID` (fallback `local`).
    - Build JSON payload with `jq -n` using `--argjson cases` from the run-log, computing `timestamp_utc` via `date -u +%Y-%m-%dT%H:%M:%SZ`.
    - `curl -sS -o /tmp/leaderboard.resp -w '%{http_code}' -X POST -H "Authorization: Bearer $LEADERBOARD_API_KEY" -H 'Content-Type: application/json' --data @/tmp/leaderboard.body.json https://findevil-bench.dev/api/scores` — capture http_code; if not 2xx, print WARN to stderr and `exit 0` (non-blocking per §7).
    - `chmod +x` the script.
- [ ] **3.5 Run test — expect GREEN.** `bash tests/orchestration/test_push_leaderboard_score.sh`. Expected last line: `PASS: push-leaderboard-score.sh (7/7 assertions)`. Exit: `0`.
- [ ] **3.6 Commit.** `git add scripts/push-leaderboard-score.sh tests/orchestration/test_push_leaderboard_score.sh tests/orchestration/fixtures/run.log.sample.json && git commit -m "feat(scripts): add push-leaderboard-score.sh with non-blocking failure mode"`.

---

## Task 4: `.github/workflows/l3-weekly-goldens.yml`

**Files touched:** `.github/workflows/l3-weekly-goldens.yml` (new), `tests/orchestration/test_l3_weekly_workflow.sh` (new)

- [ ] **4.1 Write failing test.** `tests/orchestration/test_l3_weekly_workflow.sh` asserts:
    - File exists.
    - `actionlint` passes.
    - `yq '.on.schedule[0].cron'` returns `0 23 * * 0`.
    - `yq '.jobs.goldens.runs-on'` returns `ubuntu-latest-4-core-kvm`.
    - `grep -q "scripts/l3-run-goldens.sh --full-matrix"` succeeds.
    - `grep -q "scripts/push-leaderboard-score.sh"` succeeds.
- [ ] **4.2 Run test — expect RED.** `bash tests/orchestration/test_l3_weekly_workflow.sh`. Expected: `FAIL: .github/workflows/l3-weekly-goldens.yml not found`. Exit: `1`.
- [ ] **4.3 Implement `.github/workflows/l3-weekly-goldens.yml`.** Mirror structure of `l3-nightly.yml` but:
    - Trigger `on.schedule[0].cron: '0 23 * * 0'` and `on.workflow_dispatch: {}` only (no push trigger).
    - The `goldens` step invokes `bash scripts/l3-run-goldens.sh --full-matrix`.
    - Leaderboard push uses same script; the resulting `run.log` is uploaded as `l3-weekly-verdicts` artifact with `retention-days: 90`.
- [ ] **4.4 Run test — expect GREEN.** `bash tests/orchestration/test_l3_weekly_workflow.sh` — `PASS: l3-weekly-goldens.yml structure ok`. Exit: `0`.
- [ ] **4.5 Commit.** `git add .github/workflows/l3-weekly-goldens.yml tests/orchestration/test_l3_weekly_workflow.sh && git commit -m "feat(ci): add l3-weekly-goldens full-matrix workflow"`.

---

## Task 5: `.github/workflows/release.yml`

**Files touched:** `.github/workflows/release.yml` (new), `tests/orchestration/test_release_workflow.sh` (new)

**Depends on:** Tasks 3, 6, 7 (script + deb builder + Dockerfile). Workflow references them but test is static-only.

- [ ] **5.1 Write failing test.** `tests/orchestration/test_release_workflow.sh` asserts:
    - File exists, `actionlint` passes.
    - `yq '.on.push.tags[0]'` returns `v[0-9]*`.
    - Four jobs present: `verify-l3`, `build-deb`, `build-docker`, `build-report`.
    - `yq '.jobs."build-deb".needs'` includes `verify-l3`.
    - `yq '.jobs."build-docker".needs'` includes `verify-l3`.
    - `yq '.jobs."build-report".needs'` includes `verify-l3`.
    - `grep -q "gh run list" .github/workflows/release.yml` (for L3-green check).
    - `grep -q "scripts/build-deb.sh" .github/workflows/release.yml`.
    - `grep -q "docker buildx build" .github/workflows/release.yml`.
    - `grep -q "ghcr.io/find-evil/find-evil" .github/workflows/release.yml`.
    - `grep -q "pnpm run build:lib" .github/workflows/release.yml`.
    - `grep -q "gh release upload" .github/workflows/release.yml`.
    - `grep -q "scripts/push-leaderboard-score.sh --release true" .github/workflows/release.yml`.
    - `grep -q "SLACK_WEBHOOK_RELEASES" .github/workflows/release.yml`.
- [ ] **5.2 Run test — expect RED.** `bash tests/orchestration/test_release_workflow.sh`. Expected: `FAIL: .github/workflows/release.yml not found`. Exit: `1`.
- [ ] **5.3 Implement `.github/workflows/release.yml`.** Per Spec #4 §4:
    - Trigger: `on.push.tags: ['v[0-9]*']`.
    - Job `verify-l3` (runs-on: `ubuntu-22.04`): runs
      ```
      gh run list --workflow=l3-nightly.yml --branch=main --status=success --limit=5 \
        --json headSha,databaseId,createdAt \
        --jq '[.[] | select(.headSha == env.COMMIT_SHA)] | .[0]'
      ```
      with `env: { COMMIT_SHA: ${{ github.sha }}, GH_TOKEN: ${{ secrets.GITHUB_TOKEN }} }`. Must also check `createdAt` is within 24h. Exits 1 and posts to `SLACK_WEBHOOK_CI` if no match.
    - Job `build-deb` (runs-on: `ubuntu-22.04`, needs: `verify-l3`): checkout, cargo cache, `cargo build --release --locked`, `bash scripts/build-deb.sh "${GITHUB_REF_NAME}"`, upload artifact `find-evil_${{ github.ref_name }}_amd64.deb`, then `gh release upload ${{ github.ref_name }} find-evil_${{ github.ref_name }}_amd64.deb`.
    - Job `build-docker` (runs-on: `ubuntu-latest`, needs: `verify-l3`): `docker/login-action` using `GHCR_TOKEN`, `docker/setup-buildx-action`, `docker buildx build --platform linux/amd64 --tag ghcr.io/find-evil/find-evil:${{ github.ref_name }} --push .`; capture `docker buildx imagetools inspect` digest and append to release notes via `gh release edit`.
    - Job `build-report` (runs-on: `ubuntu-22.04`, needs: `verify-l3`): pnpm setup, `pnpm install --frozen-lockfile`, `pnpm run build:lib`, `gh release upload ${{ github.ref_name }} apps/web/dist/report.html`.
    - Job `leaderboard-release` (needs: [build-deb, build-docker, build-report]): downloads last `l3-verdicts` run-log artifact, runs `scripts/push-leaderboard-score.sh --run-log run.log --release true --tag ${{ github.ref_name }}`.
    - Job `announce` (needs: [build-deb, build-docker, build-report]): posts to `SLACK_WEBHOOK_RELEASES` with Spec #4 §4.6 text template.
- [ ] **5.4 Run test — expect GREEN.** `bash tests/orchestration/test_release_workflow.sh`. Expected: `PASS: release.yml structure ok (14/14 assertions)`. Exit: `0`.
- [ ] **5.5 Commit.** `git add .github/workflows/release.yml tests/orchestration/test_release_workflow.sh && git commit -m "feat(ci): add release.yml gated on L3 green with parallel deb/docker/report builds"`.

---

## Task 6: `scripts/build-deb.sh` + test

**Files touched:** `scripts/build-deb.sh` (new), `tests/orchestration/test_build_deb.sh` (new), `packaging/debian/control.tmpl` (new)

**Contract:** Produces `find-evil_<version>_amd64.deb` targeting `ubuntu:22.04`. Invoked as `scripts/build-deb.sh v5`.

- [ ] **6.1 Write failing test.** `tests/orchestration/test_build_deb.sh`:
    - Create a temp workspace with a fake `target/release/find-evil` binary (just `#!/bin/sh\necho v0.0.0-test`) and an `apps/mcp/target/release/findevil-mcp` fake binary.
    - Run: `bash scripts/build-deb.sh v9-test 2>&1 | tee /tmp/deb.log`.
    - Assert exit 0.
    - Assert file `find-evil_v9-test_amd64.deb` exists.
    - Assert `dpkg-deb --info find-evil_v9-test_amd64.deb | grep -q "Architecture: amd64"`.
    - Assert `dpkg-deb --info find-evil_v9-test_amd64.deb | grep -q "Package: find-evil"`.
    - Assert `dpkg-deb --info find-evil_v9-test_amd64.deb | grep -q "Version: v9-test"`.
    - Assert `dpkg-deb --contents find-evil_v9-test_amd64.deb | grep -q "./usr/local/bin/find-evil"`.
    - Skip remaining assertions gracefully if `dpkg-deb` not installed (print `SKIP (dpkg-deb unavailable)` and exit 0 only if the file was built).
- [ ] **6.2 Run test — expect RED.** `bash tests/orchestration/test_build_deb.sh`. Expected: `FAIL: scripts/build-deb.sh not found`. Exit: `1`.
- [ ] **6.3 Implement `packaging/debian/control.tmpl`:**
    ```
    Package: find-evil
    Version: __VERSION__
    Section: utils
    Priority: optional
    Architecture: amd64
    Depends: libc6 (>= 2.35), libssl3
    Maintainer: find-evil team <team@find-evil.dev>
    Description: Autonomous DFIR verdict agent (find-evil)
     Analyzes E01 evidence on SIFT and produces a CONFIRMED_EVIL / NO_EVIL verdict.
    ```
- [ ] **6.4 Implement `scripts/build-deb.sh`.**
    - `set -euo pipefail`, arg `VERSION="${1:?version required}"`.
    - Build staging dir `pkg-root/{DEBIAN,usr/local/bin,usr/share/find-evil}`.
    - Copy `target/release/find-evil` → `pkg-root/usr/local/bin/find-evil` (`chmod 0755`).
    - Copy `apps/mcp/target/release/findevil-mcp` if present.
    - `sed "s/__VERSION__/$VERSION/" packaging/debian/control.tmpl > pkg-root/DEBIAN/control`.
    - `dpkg-deb --build --root-owner-group pkg-root "find-evil_${VERSION}_amd64.deb"`.
    - `chmod +x` the script.
- [ ] **6.5 Run test — expect GREEN.** `bash tests/orchestration/test_build_deb.sh`. Expected last line: `PASS: build-deb.sh produces valid amd64 .deb`. Exit: `0`.
- [ ] **6.6 Commit.** `git add scripts/build-deb.sh packaging/debian/control.tmpl tests/orchestration/test_build_deb.sh && git commit -m "feat(scripts): add build-deb.sh producing ubuntu-22.04 amd64 package"`.

---

## Task 7: Root `Dockerfile` + test

**Files touched:** `Dockerfile` (new, at repo root), `tests/orchestration/test_dockerfile.sh` (new), `.dockerignore` (new)

**Contract:** `docker buildx build --tag ghcr.io/find-evil/find-evil:v<N> .` produces a runnable image; `docker run --rm <image> find-evil --version` exits 0.

- [ ] **7.1 Write failing test.** `tests/orchestration/test_dockerfile.sh`:
    - Assert `Dockerfile` exists at repo root.
    - `hadolint Dockerfile` exits 0 (skip if hadolint absent, with SKIP message).
    - `grep -q "^FROM ubuntu:22.04" Dockerfile`.
    - `grep -q "COPY.*find-evil" Dockerfile`.
    - `grep -qE '^(ENTRYPOINT|CMD).*find-evil' Dockerfile`.
    - Assert `.dockerignore` exists and contains `target/`, `node_modules/`, `.git/`.
- [ ] **7.2 Run test — expect RED.** `bash tests/orchestration/test_dockerfile.sh`. Expected: `FAIL: Dockerfile not found at repo root`. Exit: `1`.
- [ ] **7.3 Implement `Dockerfile`:**
    ```
    FROM ubuntu:22.04 AS runtime
    RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates libssl3 libewf2 libafflib0v5 sleuthkit libyara8 \
     && rm -rf /var/lib/apt/lists/*
    WORKDIR /opt/find-evil
    COPY target/release/find-evil /usr/local/bin/find-evil
    COPY apps/mcp/target/release/findevil-mcp /usr/local/bin/findevil-mcp
    RUN useradd -r -u 1000 -s /usr/sbin/nologin findevil
    USER findevil
    ENTRYPOINT ["find-evil"]
    CMD ["--help"]
    ```
    Implement `.dockerignore` with `target/`, `node_modules/`, `.git/`, `tests/`, `docs/`, `**/*.log`.
- [ ] **7.4 Run test — expect GREEN.** `bash tests/orchestration/test_dockerfile.sh`. Expected: `PASS: Dockerfile ok (hadolint+structure)`. Exit: `0`.
- [ ] **7.5 Commit.** `git add Dockerfile .dockerignore tests/orchestration/test_dockerfile.sh && git commit -m "feat(docker): add root Dockerfile targeting ubuntu-22.04 runtime"`.

---

## Task 8: `.github/workflows/competitor-watch.yml`

**Files touched:** `.github/workflows/competitor-watch.yml` (new), `tests/orchestration/test_competitor_watch_workflow.sh` (new)

**Depends on:** Task 9 `scripts/competitor-watch.sh`.

- [ ] **8.1 Write failing test.** `tests/orchestration/test_competitor_watch_workflow.sh` asserts:
    - File exists, `actionlint` passes.
    - `yq '.on.schedule[0].cron'` returns `0 9 * * 1`.
    - `yq '.jobs.watch.runs-on'` returns `ubuntu-24.04`.
    - `grep -q "scripts/competitor-watch.sh"` succeeds.
    - `grep -q "SLACK_WEBHOOK_COMPETITORS"` succeeds.
    - `grep -q "chore/competitor-state"` succeeds (state-branch checkout).
    - `yq '.jobs.watch.permissions.contents'` returns `write` (needs to push state branch).
- [ ] **8.2 Run test — expect RED.** Expected: `FAIL: .github/workflows/competitor-watch.yml not found`. Exit: `1`.
- [ ] **8.3 Implement workflow.**
    - Trigger: `on.schedule[0].cron: '0 9 * * 1'`, `on.workflow_dispatch: {}`.
    - `permissions: { contents: write }`.
    - Steps: checkout `chore/competitor-state` branch with `actions/checkout@v4` using `ref: chore/competitor-state` and `fetch-depth: 0`; if branch missing, create orphan branch with empty `state/competitor-watch.json` (`{}`); run `bash scripts/competitor-watch.sh`; commit + `git pull --rebase origin chore/competitor-state` + `git push`; pass `SLACK_WEBHOOK_COMPETITORS`, `SLACK_WEBHOOK_CI`, `GH_TOKEN` in env.
- [ ] **8.4 Run test — expect GREEN.** Expected: `PASS: competitor-watch.yml structure ok`. Exit: `0`.
- [ ] **8.5 Commit.** `git add .github/workflows/competitor-watch.yml tests/orchestration/test_competitor_watch_workflow.sh && git commit -m "feat(ci): add weekly competitor-watch workflow on chore/competitor-state branch"`.

---

## Task 9: `scripts/competitor-watch.sh` + test

**Files touched:** `scripts/competitor-watch.sh` (new), `tests/orchestration/test_competitor_watch.sh` (new), `tests/orchestration/fixtures/gh-api-stub.sh` (new)

**Contract:** Spec #4 §8 — monitors five targets, compares against `state/competitor-watch.json`, posts Slack on delta, updates state file.

- [ ] **9.1 Create gh-api stub.** `tests/orchestration/fixtures/gh-api-stub.sh` is a shim placed earlier in `$PATH` than real `gh`. It reads `$GH_STUB_FIXTURE` env var (a path) and returns canned JSON for each expected call pattern (`repos/yushin-dfir/dfir-agent/commits`, `repos/dhyabi2/findevil/commits`, etc.). Unknown calls exit 99.
- [ ] **9.2 Write failing test.** `tests/orchestration/test_competitor_watch.sh`:
    - Set up temp `state/competitor-watch.json` with "last week" baseline (known SHAs, star counts).
    - Point fixture to a JSON file where `dhyabi2/findevil` has a new SHA and `marez8505/find-evil` star count went 12→19.
    - Stub `curl` to capture Slack POST body to `/tmp/slack-posts.txt`.
    - Run `bash scripts/competitor-watch.sh`.
    - Assert `/tmp/slack-posts.txt` contains a line posted to `$SLACK_WEBHOOK_COMPETITORS` and includes `dhyabi2/findevil` with new SHA and `marez8505/find-evil: stars 12 → 19`.
    - Assert `state/competitor-watch.json` updated to reflect new values.
    - Assert that on a second run with no changes, NO Slack post is emitted (`/tmp/slack-posts.txt` size unchanged).
    - Assert that on a new topic-search repo with `stargazers_count >= 3`, posts appear in BOTH `$SLACK_WEBHOOK_COMPETITORS` and `$SLACK_WEBHOOK_CI`.
- [ ] **9.3 Run test — expect RED.** `bash tests/orchestration/test_competitor_watch.sh`. Expected: `FAIL: scripts/competitor-watch.sh not found`. Exit: `1`.
- [ ] **9.4 Implement `scripts/competitor-watch.sh`.**
    - `set -euo pipefail`.
    - Define `TARGETS=(yushin-dfir/dfir-agent dhyabi2/findevil marez8505/find-evil teamdfir/protocol-sift)`.
    - For each: `gh api repos/$T/commits?per_page=1 --jq '.[0].sha'` and `gh api repos/$T --jq .stargazers_count`.
    - Topic search: `gh api 'search/repositories?q=topic:find-evil&sort=updated' --jq '.items[] | {full_name, stargazers_count}'`.
    - Load `state/competitor-watch.json` (or `echo '{}'` if absent).
    - Compute deltas: new SHA, star delta ≥ 5, new topic repos with stars ≥ 3.
    - Build Slack message per §8 template if any delta.
    - If new topic repo with stars ≥ 3: post to BOTH `$SLACK_WEBHOOK_COMPETITORS` and `$SLACK_WEBHOOK_CI`.
    - If zero deltas: exit 0 without posting.
    - Write updated state back to `state/competitor-watch.json`.
- [ ] **9.5 Run test — expect GREEN.** Expected last line: `PASS: competitor-watch.sh (6/6 scenarios)`. Exit: `0`.
- [ ] **9.6 Commit.** `git add scripts/competitor-watch.sh tests/orchestration/test_competitor_watch.sh tests/orchestration/fixtures/gh-api-stub.sh && git commit -m "feat(scripts): add competitor-watch.sh with state-branch diff and tiered alerts"`.

---

## Task 10: `.github/workflows/budget-guard.yml` (Option-B aware)

**Files touched:** `.github/workflows/budget-guard.yml` (new), `tests/orchestration/test_budget_guard_workflow.sh` (new)

**Option-B contract:** Amendment A1 §5 — if repo secret `ANTHROPIC_API_KEY` is NOT set, workflow emits `"Option B mode — no metered API in use"` and exits 0. If set, queries Anthropic usage API and alerts on >$40/day (warn) or >$50/day (halt).

- [ ] **10.1 Write failing test.** `tests/orchestration/test_budget_guard_workflow.sh` asserts:
    - File exists, `actionlint` passes.
    - `yq '.on.schedule[0].cron'` returns `0 6 * * *`.
    - `grep -q "Option B mode" .github/workflows/budget-guard.yml` (the literal no-op message).
    - `grep -q "secrets.ANTHROPIC_API_KEY" .github/workflows/budget-guard.yml` (gate uses a secret-presence check via a shell step that inspects `env.ANTHROPIC_API_KEY`).
    - `grep -q "SWARM_HALT" .github/workflows/budget-guard.yml`.
    - `grep -q "SLACK_WEBHOOK_CI" .github/workflows/budget-guard.yml`.
    - No reference to `litellm` or `/spend` remains (grep for `litellm` returns 0 matches — spec A1 §5 removal).
- [ ] **10.2 Run test — expect RED.** Expected: `FAIL: .github/workflows/budget-guard.yml not found`. Exit: `1`.
- [ ] **10.3 Implement `.github/workflows/budget-guard.yml`:**
    - Trigger: `schedule: [{cron: '0 6 * * *'}]`, `workflow_dispatch: {}`.
    - Single job `guard` (runs-on: `ubuntu-24.04`) with one step:
      - `env: { ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}, SLACK_WEBHOOK_CI: ${{ secrets.SLACK_WEBHOOK_CI }}, GH_TOKEN: ${{ secrets.GITHUB_TOKEN }} }`.
      - Script body:
        ```
        if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
          echo "Option B mode — no metered API in use"
          exit 0
        fi
        # metered path: query Anthropic usage API
        SPEND=$(curl -sS -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" \
          "https://api.anthropic.com/v1/organizations/usage_report/messages?starting_at=$(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%SZ)" \
          | jq -r '.data[0].uncached_input_tokens_cost + .data[0].output_tokens_cost // 0')
        if awk "BEGIN{exit !($SPEND > 50)}"; then
          gh api repos/${{ github.repository }}/actions/variables/SWARM_HALT --method PATCH --field value=true
          curl -sS -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"[find-evil CI] budget-guard | HALT | 24h spend \$$SPEND > \$50 — SWARM_HALT=true\"}" \
            "$SLACK_WEBHOOK_CI"
        elif awk "BEGIN{exit !($SPEND > 40)}"; then
          curl -sS -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"[find-evil CI] budget-guard | WARN | 24h spend \$$SPEND > \$40\"}" \
            "$SLACK_WEBHOOK_CI"
        fi
        ```
- [ ] **10.4 Run test — expect GREEN.** Expected: `PASS: budget-guard.yml Option-B aware, no litellm references`. Exit: `0`.
- [ ] **10.5 Commit.** `git add .github/workflows/budget-guard.yml tests/orchestration/test_budget_guard_workflow.sh && git commit -m "feat(ci): add Option-B-aware budget-guard workflow (no-op without API key)"`.

---

## Task 11: `.github/workflows/devpost-submit.yml`

**Files touched:** `.github/workflows/devpost-submit.yml` (new), `tests/orchestration/test_devpost_submit_workflow.sh` (new)

**Depends on:** Tasks 12, 13, 14 (script + csv converter + README template).

- [ ] **11.1 Write failing test.** Asserts:
    - File exists, `actionlint` passes.
    - `yq '.on.push.tags[0]'` returns `v-submit`.
    - `grep -q "scripts/package-devpost.sh"` succeeds.
    - `grep -q "DEMO_VIDEO_URL"` succeeds.
    - `grep -q "gh run list --workflow=release.yml"` succeeds (the release-green wait-loop).
    - `grep -q "SLACK_WEBHOOK_RELEASES"` succeeds.
    - `grep -q "gh release upload v-submit find-evil-submission.zip"` succeeds.
    - `grep -q "scripts/json-to-benchmark-csv.py"` succeeds.
- [ ] **11.2 Run test — expect RED.** Expected: `FAIL: .github/workflows/devpost-submit.yml not found`. Exit: `1`.
- [ ] **11.3 Implement workflow.** Per Spec #4 §9:
    - `on.push.tags: ['v-submit']`.
    - Job `package` (runs-on: `ubuntu-22.04`, `permissions: { contents: write, actions: read }`):
      - Step 1: poll `gh run list --workflow=release.yml --branch=v-submit --status=success` up to 30 min (15 iterations × 120s), exit 1 if never green.
      - Step 2: `DEMO_VIDEO_URL=$(gh variable get DEMO_VIDEO_URL)`; if empty exit 1 and Slack-alert `$SLACK_WEBHOOK_CI` with the §9.2 error string.
      - Step 3: `gh release download v-submit --pattern 'find-evil_v-submit_amd64.deb' --pattern 'report.html'`.
      - Step 4: `gh run download --name l3-weekly-verdicts --dir ./weekly-latest` (latest successful weekly goldens run).
      - Step 5: `python3 scripts/json-to-benchmark-csv.py ./weekly-latest/run.log > benchmark-results.csv`.
      - Step 6: `bash scripts/package-devpost.sh` (reads `DEMO_VIDEO_URL` from env).
      - Step 7: `gh release upload v-submit find-evil-submission.zip`.
      - Step 8: post to `$SLACK_WEBHOOK_RELEASES` with Spec §9.8 text.
- [ ] **11.4 Run test — expect GREEN.** Expected: `PASS: devpost-submit.yml structure ok (8/8 assertions)`. Exit: `0`.
- [ ] **11.5 Commit.** `git add .github/workflows/devpost-submit.yml tests/orchestration/test_devpost_submit_workflow.sh && git commit -m "feat(ci): add devpost-submit workflow triggered on v-submit tag"`.

---

## Task 12: `scripts/package-devpost.sh` + test

**Files touched:** `scripts/package-devpost.sh` (new), `tests/orchestration/test_package_devpost.sh` (new)

**Depends on:** Tasks 1, 14, 15. Uses Task 13's output CSV as input.

**Contract:** Spec #4 §9.5 + §9.6 — assemble `find-evil-submission.zip` with exactly 7 files; integrity check exits 1 if any missing; envsubst fails-loudly if `DEMO_VIDEO_URL` is empty.

- [ ] **12.1 Write failing test.** `tests/orchestration/test_package_devpost.sh`:
    - In a tmp dir: create placeholders `find-evil_v-submit_amd64.deb`, `report.html`, `benchmark-results.csv` (with header + one `nist-hacking-case` row), stub `LICENSE`, `SUBMISSION_NOTES.md`, `docs/templates/devpost-readme.md` (with `${DEMO_VIDEO_URL}`, `${RELEASE_TAG}`, `${ACCURACY}`, `${DATE}`).
    - Run with `DEMO_VIDEO_URL="https://youtu.be/abc123" RELEASE_TAG=v-submit ACCURACY=0.92 bash scripts/package-devpost.sh` → expect exit 0.
    - Assert `find-evil-submission.zip` exists.
    - Assert `unzip -l find-evil-submission.zip` lists exactly 7 entries: `README-submission.md`, `benchmark-results.csv`, `demo-video-link.txt`, `LICENSE`, `find-evil_v-submit_amd64.deb`, `report.html`, `SUBMISSION_NOTES.md`.
    - Assert `unzip -p find-evil-submission.zip README-submission.md | grep -q 'https://youtu.be/abc123'`.
    - Assert `unzip -p find-evil-submission.zip README-submission.md | grep -vq '\${'` (no unsubstituted vars).
    - Assert `unzip -p find-evil-submission.zip demo-video-link.txt` equals `https://youtu.be/abc123\n`.
    - Run with `DEMO_VIDEO_URL="" …` → expect exit 1 and stderr contains `"Set DEMO_VIDEO_URL via: gh variable set DEMO_VIDEO_URL --body '<url>' before cutting v-submit"`.
    - Run after deleting `benchmark-results.csv` → expect exit 1 and stderr contains `"integrity check failed: missing benchmark-results.csv"`.
- [ ] **12.2 Run test — expect RED.** `bash tests/orchestration/test_package_devpost.sh`. Expected: `FAIL: scripts/package-devpost.sh not found`. Exit: `1`.
- [ ] **12.3 Implement `scripts/package-devpost.sh`.**
    - `set -euo pipefail`.
    - Check `[ -n "${DEMO_VIDEO_URL:-}" ]` — else print the exact Spec §9.2 error to stderr and `exit 1`.
    - `export DEMO_VIDEO_URL RELEASE_TAG ACCURACY DATE="$(date -u +%Y-%m-%d)"`.
    - `envsubst '${DEMO_VIDEO_URL} ${RELEASE_TAG} ${ACCURACY} ${DATE}' < docs/templates/devpost-readme.md > README-submission.md` (the explicit variable list prevents accidental substitution of unrelated `$` tokens).
    - `printf '%s\n' "$DEMO_VIDEO_URL" > demo-video-link.txt`.
    - Integrity check: for each of the 7 expected files, `[ -f "$f" ] || { echo "integrity check failed: missing $f" >&2; exit 1; }`.
    - `zip -j find-evil-submission.zip README-submission.md benchmark-results.csv demo-video-link.txt LICENSE find-evil_v-submit_amd64.deb report.html SUBMISSION_NOTES.md`.
    - Post-zip verification: `unzip -l find-evil-submission.zip | grep -c '^\s*[0-9]'` must equal 7.
- [ ] **12.4 Run test — expect GREEN.** Expected final line: `PASS: package-devpost.sh (9/9 assertions)`. Exit: `0`.
- [ ] **12.5 Commit.** `git add scripts/package-devpost.sh tests/orchestration/test_package_devpost.sh && git commit -m "feat(scripts): add package-devpost.sh with 7-file integrity check and envsubst guard"`.

---

## Task 13: `scripts/json-to-benchmark-csv.py` + test

**Files touched:** `scripts/json-to-benchmark-csv.py` (new), `tests/orchestration/test_json_to_benchmark_csv.py` (new)

**Contract:** Reads the L3 `run.log` JSON (same shape as Task 3 fixture), emits CSV with columns `fixture,findings_matched,findings_expected,verdict,verdict_correct,wall_clock_seconds`.

- [ ] **13.1 Write failing test.** `tests/orchestration/test_json_to_benchmark_csv.py` (run with `python3`):
    - Feeds `tests/orchestration/fixtures/run.log.sample.json` (from Task 3) on stdin OR as positional arg.
    - Captures stdout.
    - Asserts first line is exactly `fixture,findings_matched,findings_expected,verdict,verdict_correct,wall_clock_seconds`.
    - Asserts 3 data rows.
    - Asserts row 1 starts with `nist-hacking-case,14,14,CONFIRMED_EVIL,true,312`.
    - Asserts row 3 is `synthetic-benign,0,0,NO_EVIL,true,145`.
    - Assert running with no arg exits 2 and stderr contains `usage:`.
    - Assert running with a malformed JSON exits 1.
- [ ] **13.2 Run test — expect RED.** `python3 tests/orchestration/test_json_to_benchmark_csv.py`. Expected: `FAIL: scripts/json-to-benchmark-csv.py not found`. Exit: `1`.
- [ ] **13.3 Implement `scripts/json-to-benchmark-csv.py`.**
    - `#!/usr/bin/env python3`, stdlib only (`json`, `csv`, `sys`, `argparse`).
    - Usage: `json-to-benchmark-csv.py <run.log>`.
    - Parse JSON, iterate `.cases[]`, `csv.writer(sys.stdout).writerows(...)`.
    - Verdict-correct serialized lowercase (`true`/`false`) per test expectation (custom stringify, not Python's `True`).
- [ ] **13.4 Run test — expect GREEN.** Expected last line: `PASS: json-to-benchmark-csv.py (5/5 assertions)`. Exit: `0`.
- [ ] **13.5 Commit.** `git add scripts/json-to-benchmark-csv.py tests/orchestration/test_json_to_benchmark_csv.py && git commit -m "feat(scripts): add json-to-benchmark-csv.py for Devpost CSV export"`.

---

## Task 14: `docs/templates/devpost-readme.md`

**Files touched:** `docs/templates/devpost-readme.md` (new), `tests/orchestration/test_devpost_readme_template.sh` (new)

- [ ] **14.1 Write failing test.** Asserts:
    - File exists.
    - Contains each placeholder literally: `${DEMO_VIDEO_URL}`, `${RELEASE_TAG}`, `${ACCURACY}`, `${DATE}`.
    - Contains both CI status badges (`l1-unit.yml/badge.svg` and `l3-nightly.yml/badge.svg`) per Spec #4 §10.
    - Contains a "Credentials Required" section per Amendment A1 §3.3.
    - Lints as valid markdown with no broken-reference links (`markdownlint` or a simple `grep -c '](' vs grep -c '[\]\[' ` consistency check if markdownlint absent).
- [ ] **14.2 Run test — expect RED.** Expected: `FAIL: docs/templates/devpost-readme.md not found`. Exit: `1`.
- [ ] **14.3 Implement `docs/templates/devpost-readme.md`.** Sections:
    1. Title `# find-evil — Autonomous DFIR Verdict Agent`.
    2. CI badges (both `l1-unit.yml` and `l3-nightly.yml` SVGs).
    3. Demo video: `[Watch the demo](${DEMO_VIDEO_URL})`.
    4. Release: `Release: **${RELEASE_TAG}** • Aggregate accuracy: **${ACCURACY}** • Built: **${DATE}**`.
    5. What it does (2-3 sentences, Spec §1 summary).
    6. Credentials Required (verbatim from Amendment A1 §3.3 blockquote).
    7. Benchmark: link to `benchmark-results.csv` in the zip.
    8. Install: `sudo dpkg -i find-evil_${RELEASE_TAG}_amd64.deb` OR `docker run ghcr.io/find-evil/find-evil:${RELEASE_TAG}`.
    9. License: Apache-2.0 (see `LICENSE`).
- [ ] **14.4 Run test — expect GREEN.** Expected: `PASS: devpost-readme.md template ok`. Exit: `0`.
- [ ] **14.5 Commit.** `git add docs/templates/devpost-readme.md tests/orchestration/test_devpost_readme_template.sh && git commit -m "docs(templates): add devpost-readme template with CI badges and credentials section"`.

---

## Task 15: `SUBMISSION_NOTES.md` stub

**Files touched:** `SUBMISSION_NOTES.md` (new at repo root), `tests/orchestration/test_submission_notes.sh` (new)

- [ ] **15.1 Write failing test.** Asserts:
    - `SUBMISSION_NOTES.md` exists at repo root.
    - File is readable (may be empty or contain a single placeholder line).
- [ ] **15.2 Run test — expect RED.** Expected: `FAIL: SUBMISSION_NOTES.md not found`. Exit: `1`.
- [ ] **15.3 Implement.** Write a stub:
    ```
    # Judge-Facing Notes

    (Optional — edit before cutting v-submit tag. Empty file is acceptable.)
    ```
- [ ] **15.4 Run test — expect GREEN.** Expected: `PASS: SUBMISSION_NOTES.md stub present`. Exit: `0`.
- [ ] **15.5 Commit.** `git add SUBMISSION_NOTES.md tests/orchestration/test_submission_notes.sh && git commit -m "docs: add SUBMISSION_NOTES.md stub for pre-submit edits"`.

---

## Task 16: `scripts/setup-branch-protection.sh`

**Files touched:** `scripts/setup-branch-protection.sh` (new), `tests/orchestration/test_setup_branch_protection.sh` (new)

**Contract:** Spec #4 §6 — idempotent `gh api PUT` applying required status checks `l0-static` and `l1-unit`.

- [ ] **16.1 Write failing test.** Stubs `gh` on `$PATH` capturing args to `/tmp/gh-args.txt`. Asserts:
    - Running `bash scripts/setup-branch-protection.sh myorg/myrepo` exits 0.
    - Captured args include `api`, `repos/myorg/myrepo/branches/main/protection`, `--method PUT`.
    - Captured args include `--field 'required_status_checks[contexts][]=l0-static'`.
    - Captured args include `--field 'required_status_checks[contexts][]=l1-unit'`.
    - Captured args include `--field 'enforce_admins=true'`.
    - Captured args include `--field 'required_pull_request_reviews[required_approving_review_count]=1'`.
    - Captured args include `--field 'allow_force_pushes=false'`.
    - Captured args include `--field 'allow_deletions=false'`.
    - Running without arg exits 2 with `usage:` to stderr.
- [ ] **16.2 Run test — expect RED.** Expected: `FAIL: scripts/setup-branch-protection.sh not found`. Exit: `1`.
- [ ] **16.3 Implement.** Mirror Spec §6 `gh api` invocation exactly; `REPO="${1:?usage: setup-branch-protection.sh <owner/repo>}"`; run the PUT.
- [ ] **16.4 Run test — expect GREEN.** Expected: `PASS: setup-branch-protection.sh (9/9 fields asserted)`. Exit: `0`.
- [ ] **16.5 Commit.** `git add scripts/setup-branch-protection.sh tests/orchestration/test_setup_branch_protection.sh && git commit -m "feat(scripts): add setup-branch-protection.sh per Spec #4 §6"`.

---

## Task 17: End-to-end verification + manual smoke-test checklist

**Files touched:** `docs/superpowers/checklists/2026-04-23-orchestration-smoke-test.md` (new), `tests/orchestration/test_e2e_dry_run.sh` (new)

**Goal:** Prove the full swarm PR → L0+L1 gate → merge → L3 nightly → release tag → Devpost zip chain works by running every script against local fixtures. Production GHA runs are verified manually per the checklist.

- [ ] **17.1 Write failing E2E dry-run test.** `tests/orchestration/test_e2e_dry_run.sh` executes in one shell session:
    - Verifies all nine workflow files exist and `actionlint` passes on each.
    - Executes every individual task's unit test in sequence; aggregate exit code must be 0.
    - Simulates the Devpost-path: run `scripts/json-to-benchmark-csv.py` against the sample fixture → `scripts/package-devpost.sh` against a staged dir → assert 7-file zip produced.
    - Simulates the leaderboard path: run `scripts/push-leaderboard-score.sh` with stubbed `curl` for both `release=false` and `release=true`.
    - Simulates competitor-watch deltas path: `scripts/competitor-watch.sh` with stubbed gh + curl.
- [ ] **17.2 Run test — expect RED initially.** Run `bash tests/orchestration/test_e2e_dry_run.sh`. Expected failure identifies the first missing integration (most likely a script path ordering issue) — document and fix. Re-run until GREEN. Expected final line: `PASS: E2E dry run — 9 workflows, 10 scripts, 7-file zip assembled`. Exit: `0`.
- [ ] **17.3 Write manual smoke-test checklist** at `docs/superpowers/checklists/2026-04-23-orchestration-smoke-test.md`:
    - [ ] Open a dummy swarm PR from a branch → L0 + L1 checks appear as required statuses within 5 minutes (AC Spec §11).
    - [ ] L2 appears as advisory (non-blocking).
    - [ ] Merge via `gh pr merge --squash` → `main` push triggers `l3-nightly.yml`.
    - [ ] L3 green → leaderboard POST observed in workflow log; 2xx in `/tmp/leaderboard.resp` on the runner.
    - [ ] L3 red → Slack `#ci-alerts` post received.
    - [ ] `git tag v1-smoke && git push origin v1-smoke` → `release.yml` runs `verify-l3` step and exits 1 if L3 not green in 24h; confirms the gate.
    - [ ] With L3 green: `release.yml` uploads `.deb`, docker image digest in release notes, and `report.html` to the GH Release.
    - [ ] `sudo dpkg -i find-evil_v1-smoke_amd64.deb && find-evil --version` exits 0 in an `ubuntu:22.04` container.
    - [ ] `docker run --rm ghcr.io/find-evil/find-evil:v1-smoke find-evil --version` exits 0.
    - [ ] `report.html` opens offline with `--disable-features=NetworkService`.
    - [ ] First Monday: `competitor-watch.yml` fires; state file updated on `chore/competitor-state` branch.
    - [ ] `budget-guard.yml` daily: confirm log shows `"Option B mode — no metered API in use"` when no `ANTHROPIC_API_KEY` secret; add the secret and confirm metered branch queries Anthropic usage API.
    - [ ] `gh variable set DEMO_VIDEO_URL --body 'https://youtu.be/smoke'`, then `git tag v-submit-smoke && git push origin v-submit-smoke` → `devpost-submit.yml` runs, uploads `find-evil-submission.zip` with exactly 7 files, posts to `#releases`.
    - [ ] Unzipped `README-submission.md` contains no unresolved `${...}` placeholders.
- [ ] **17.4 Commit.** `git add tests/orchestration/test_e2e_dry_run.sh docs/superpowers/checklists/2026-04-23-orchestration-smoke-test.md && git commit -m "test(orchestration): add E2E dry run and manual smoke-test checklist"`.

---

## Post-Plan Verification Gate

Before declaring this plan complete:

- [ ] All 17 task unit tests pass in a clean run: `for t in tests/orchestration/test_*.sh; do bash "$t" || exit 1; done && python3 tests/orchestration/test_json_to_benchmark_csv.py` exits 0.
- [ ] `actionlint .github/workflows/*.yml` exits 0 (all 9 workflows present: `l0-static.yml`, `l1-unit.yml`, `l2-sift-lite.yml`, `l3-nightly.yml`, `l3-weekly-goldens.yml`, `release.yml`, `competitor-watch.yml`, `budget-guard.yml`, `devpost-submit.yml`; the first three are produced by the Spec #3 sandbox plan — this plan assumes they exist and only adds the other six).
- [ ] `git log --oneline` shows 17 commits from this plan, one per task.
- [ ] Repo root contains: `LICENSE`, `Dockerfile`, `.dockerignore`, `SUBMISSION_NOTES.md`.
- [ ] `scripts/` contains: `push-leaderboard-score.sh`, `build-deb.sh`, `competitor-watch.sh`, `package-devpost.sh`, `json-to-benchmark-csv.py`, `setup-branch-protection.sh` (all `chmod +x` where applicable).
- [ ] `docs/templates/devpost-readme.md` and `docs/superpowers/checklists/2026-04-23-orchestration-smoke-test.md` exist.
- [ ] Manual smoke-test checklist (Task 17.3) executed against a real GitHub org/repo at least once before the first `v<N>` tag is cut.

---

## Assumptions and Interfaces

| Interface | Source | This plan's assumption |
|---|---|---|
| `scripts/l3-run-goldens.sh` (Spec #3 §4.4) | Spec #3 sandbox plan | Exists and writes `run.log` JSON with `.cases[]` and `.aggregate` shape per Spec #4 §7. Supports `--full-matrix` flag for Task 4. |
| `.github/workflows/l0-static.yml`, `l1-unit.yml`, `l2-sift-lite.yml` | Spec #3 sandbox plan | Produced there; referenced by branch protection (Task 16) and E2E checklist. |
| `target/release/find-evil` and `apps/mcp/target/release/findevil-mcp` binaries | Spec #2 Product | Produced by Spec #2's `cargo build --release --locked` before Task 6/7 run. |
| `apps/web/` Vite project | Spec #2 Product | Has `pnpm run build:lib` that emits single-file `report.html`. |
| Findevil-bench.dev endpoint | M1 moonshot, week 6 | API at `POST https://findevil-bench.dev/api/scores` exists; if it does not, leaderboard pushes fail silently (non-blocking per §7). |
| Anthropic usage-report API shape | Anthropic public docs | Accepts `GET /v1/organizations/usage_report/messages?starting_at=...` with `x-api-key` header and returns `data[0].uncached_input_tokens_cost + .output_tokens_cost`. If the real shape differs, Task 10's metered branch needs a one-line `jq` adjustment. The Option-B no-op branch is unaffected. |
