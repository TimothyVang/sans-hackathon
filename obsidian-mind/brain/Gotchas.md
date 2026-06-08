---
date: 2026-06-08
description: Hard-won technical gotchas for VERDICT — environment, dashboard, engine, SIFT, n8n — plus Tier-1 DFIR artifact caveats.
tags: [brain, gotchas]
---

# Gotchas

## Tier-1 DFIR artifact caveats (never violate)

- **Amcache `LastModified` ≠ execution.** It is catalog-registration time. Execution claims
  need **≥2 artifact classes** (Prefetch + Amcache/ShimCache, or EDR telemetry). See [[Patterns]].
- **ShimCache is insertion-ordered, not LRU**, and order semantics changed at Win8.1. Presence ≠
  execution.
- **EVTX Logon Type 3 (Network) vs 10 (RemoteInteractive).** Always pair a Type 3 finding with
  the source IP — internal RFC1918 is almost always benign.
- **MFT: prefer `$FN` over `$SI`** (anti-forensics stomps `$SI`, rarely `$FN`).
- **DKOM (`vol_pslist`=0, `vol_psscan`>0) is NOT automatically T1014.** Disambiguate from an
  acquisition smear / kernel-global read failure first: `KeNumberProcessors`=0, duplicate
  `System` EPROCESS, or psscan-only OS singletons → smear, label it **HYPOTHESIS**.

## Dashboard verification (this host)

- **Port 3000 is occupied by a foreign server.** `scripts/verdict` auto-opens
  `http://localhost:3000` and deep-links wrongly. Run the dashboard on **:3100** with
  `pnpm --filter @findevil/web exec next dev -p 3100`, export `FINDEVIL_REPO_ROOT=$PWD` +
  `FINDEVIL_DASHBOARD_EXTRA_ROOTS=$PWD/tmp/auto-runs`, and pass `--no-dashboard` to verdict.
- **Use plain `next dev` (webpack), NOT `--turbo`** — turbo intermittently throws
  `Cannot find module './chunks/ssr/[turbopack]_runtime.js'`.
- **cloakbrowser MCP Chrome (CDP :9222) cannot reach the host's `localhost`** (isolated net).
  Screenshot the dashboard with the **host's own Playwright** (global; chromium in
  `~/.cache/ms-playwright`). A one-shot `--headless --screenshot` HANGS because `/api/audit` SSE
  never closes — use `goto(url,{waitUntil:'commit'})` + `waitForSelector(...)`.
- **`?case=<path>` only loads under an allow-listed root** resolved against `FINDEVIL_REPO_ROOT`;
  `next` runs with cwd `apps/web`, so export `FINDEVIL_REPO_ROOT=<repo root>` or the API 400s.

## Engine fixes (root causes that dead-ended runs)

- **`verify_finding` `-32602`** = relative evidence path. The verifier's replay spawns from
  `services/agent_mcp` cwd; a relative `memory_path` 404s. Fix: absolutize the evidence path in
  `find_evil_auto.py Investigation.__init__` (LOCAL_MODE).
- **matplotlib missing** → `render_report.py` silently skips ("No module named 'matplotlib'").
  It's a host-side dep now installed by `scripts/install-dfir-tools.sh`; `requirements.txt` lists it.
- **One bad artifact crashed the whole MCP server.** A panic (e.g. legacy `frnsc-hive` on XP
  hives) killed `findevil-mcp` mid-run. Fixed: `server.rs handle_tools_call` wraps the handler in
  `catch_unwind` → clean per-call ToolError (profile is unwind, not panic=abort).
- **"cleared" QA false-positive**: `no_forbidden_unqualified_language` substring-matched "cleared"
  inside finding-ids/filenames. Fixed by matching forbidden terms as prose words with word
  boundaries in `find_evil_auto.py` (did NOT edit `expert-rules.json`).

## NIST SCHARDT disk wall (SIFT)

- OVA is **`sift-2026-04-22.ova`** (8.9 GB) at repo root — NOT the `sift-2026.03.24.ova` the
  script historically defaulted to.
- VMware kernel modules may need `sudo vmware-modconfig --console --install-all`.
- Guest comes up at **192.168.137.130** (NAT 192.168.137.0/24), user `sansforensics`. Export
  `FIND_EVIL_GUEST_IP=192.168.137.130` (the `find_evil_auto.py` default `192.168.197.143` is stale).
- Disk mount needs root: set `FIND_EVIL_GUEST_MOUNT_BIN` → a guest `sudo-mount` wrapper.
- **XP registry parser FIXED**: `frnsc-hive` replaced by in-tree `services/mcp/src/tools/regf.rs`.
- **NIST now reaches SUSPICIOUS/CONFIRMED** via **UserAssist** corroboration (Prefetch +
  UserAssist = two execution classes); ShimCache/Amcache/USBSTOR absent on SCHARDT.

## n8n / browser automation

- n8n Code node: use **`this.helpers.httpRequest`** (not `$helpers`); `require('fs')` disallowed.
- browserless `/content` returns **404 when Content-Type is missing** — send a pre-stringified
  body with explicit `Content-Type: application/json`, drop `json:true`.
- Docker `bridge` has no DNS — put containers on a user network (`findevil-net`).
- Google SSO rejects bundled Chromium — launch **real Chrome** (`channel:"chrome"`) with
  automation fingerprints stripped (`scripts/get-api-key.cjs`).
- **Do not self-whitelist MCP tools** in `.claude/settings.local.json` — the auto-mode classifier
  denies it as self-modification. Let tools prompt, or ask the user.

## SANS HACKATHON-2026 evidence corpus + Egnyte downloads

- Evidence lives at the Egnyte folder-link `https://sansorg.egnyte.com/fl/HhH7crTYT4JK` (shared by
  Rob Lee, anonymous-public, until Jun 17 2026). Three scenarios:
  - **Compromised APT Attack Scenarios/** — `SRL-2015` and `SRL-2018` enterprise compromises.
    SRL-2018 = 7 host `.E01` disks (base-dc, base-file, base-rd-01/02, base-wkstn-01/05, dmz-ftp;
    ~11–17 GB each) + an `SRL-2018/` memory subfolder. The `base-dc-memory.img` already in
    `evidence/` is this scenario's DC memory.
  - **Standard Forensic Case/** = **ROCBA** — `rocba-cdrive.e01` (22 GB) + `Rocba-Memory.zip`
    (5.3 GB) + `ROCBA-BACKGROUND.pptx` (scenario *background*, not an answer key).
  - **Standard Forensics Case 2/** = **VANKO** — `VANKO.zip` (40.7 GB) + brief.
- **Download mechanism** (no login): select file(s) → "Download Selected" injects a hidden
  `<iframe src="https://sansorg.egnyte.com/dd/HhH7crTYT4JK/?entryId=<uuid>">`. Capture that iframe
  `src` via Playwright/Puppeteer — it's the direct download, supports HTTP range/resume, and `curl`
  fetches it anonymously with a `Referer: …/fl/HhH7crTYT4JK` header. The row's DOM `data-id` is NOT
  the `entryId` (different UUIDs). **Office files (.pptx) PREVIEW instead of download**, so the
  iframe never fires for them. The REST listing endpoints (`/rest/public/1.0/links/info/<id>/contents`)
  reject GET (405; the SPA POSTs).
- **Large downloads are throttled** hard — small files ~6 MB/s, the 22 GB e01 crawls at ~100 KB/s
  (~60 h ETA). Always `curl -C -` (resume); expect big images to take a long time.
- **Nested-archive gotcha:** `Rocba-Memory.zip` → `Rocba-Memory/Rocba-Memory.7z` → `Rocba-Memory.raw`
  (19.05 GB raw memory). Extract both layers (`unzip` then `7z e`) before investigating.
- **ROCBA / base-dc are live-run-only (NOT scoreable).** Their briefs are scenario background, not
  answer keys, so there is no ground truth to author a golden from — running them yields a Verdict +
  report but no recall score. Only cases with a real answer key get a golden: currently `nitroba`
  (100 %) and `nist-hacking-case` (via `SCHARDT.dd`). Never fabricate a golden. See [[Patterns]].
- **`evidence/` vs `fixtures/` is enforced, not conventional:** `scripts/fetch-fixtures.sh` aborts if
  `FIXTURES` resolves under `evidence/`, and `l3-run-goldens.sh` only reads `fixtures/<case>`.
  `evidence/` = ad-hoc live-run drop zone; `fixtures/` = scored benchmark corpus paired with `goldens/`.

- **CI pins `ruff==0.7.4`** (`.github/workflows/l0-static.yml`). Local `uvx ruff` pulls the LATEST
  ruff, which formats differently → files pass `ruff format` locally but CI's 0.7.4 `format --check`
  flags them (cost a red CI cycle 2026-06-08). Match CI: `uvx ruff@0.7.4 format .` + `uvx ruff@0.7.4 check .`.
  `cargo` lives at `~/.cargo/bin/cargo` (not on default PATH). eslint: use `next/link` `<Link>`, never
  `<a href="/">` internal nav (`@next/next/no-html-link-for-pages`).
- **L1 CI (`docker/l1-compose.yml`) green-up (2026-06-08) — `unrs-resolver` was a RED HERRING.**
  L1's `pnpm install` runs `--ignore-scripts`, so the `unrs-resolver` napi-postinstall never fires;
  pnpm install/build/test pass and L1 reaches its smoke stage. Don't chase that ghost. The real L1
  blockers were four things the feature branch added without updating their gates:
  1. **judge corroboration broke** — `services/agent/findevil_agent/judge.py` `_group_key()` keyed on
     the free-text finding *description*, so cross-pool Pool-A/Pool-B findings worded differently never
     merged (broke `test_corroborated_finding_gets_bonus`). Fix: key on
     `(tool_call_id, artifact_path, mitre_technique)` — drop the description.
  2. **`selfscore_aggregate` deleted** — the unified-launcher commit (09154c3) accidentally dropped the
     fleet `judge_selfscore` rollup from `scripts/fleet_correlate.py`, but `fleet-policy-smoke` still
     locks it → `AttributeError`. Fix: restore the 3 deleted blocks (working tree then matches master).
  3. **`divergence-smoke` #10 stale** — hard-required exactly 2 `.mcp.json` servers, but the branch
     added the 4 documented non-product servers (n8n-mcp/playwright/puppeteer/qmd; CLAUDE.md §3/§4).
     Allow-list them; scope the gateway/shell forbidden-token scan to the product servers only.
  4. **`path-existence-smoke` passes locally, fails in CI** — on refs that resolve only via gitignored
     content present on a dev disk but absent from CI's clean checkout (`n8n-references/`, docker
     `./out/`). Allow-list both. **To reproduce a CI-only path failure locally, stash the gitignored
     dirs** (`mv n8n-references out /tmp/…`) then run the smoke. Same trick for any "green locally, red
     in CI" path smoke. Also: a literal ellipsis `…` (U+2026) in a backtick path = placeholder, never
     a real file — allow-listed.

## The headless engine runs under bare python3 (3.10) — it CANNOT import findevil_agent

`scripts/verdict` launches the engine as `python3 scripts/find_evil_auto.py …` (host system
python — **3.10 here**), NOT a `findevil_agent` venv. `findevil_agent` requires **3.11+**
(`from enum import StrEnum`) and its package `__init__` eagerly imports pydantic, so **any**
`import findevil_agent.*` in `find_evil_auto.py` fails at module load. That's why the playbook
import (and now the Hermes memory glue) is wrapped in `try/except ImportError` with an **inline
3.10-safe fallback** — the import is effectively always-False in the real engine.

**Trap:** wiring that imports `findevil_agent` into the engine *compiles, lints, and passes unit
tests* but **silently no-ops at runtime** (guarded import → `_AVAILABLE=False` → early return).
You only catch it with a live run. Fix: inline the logic (stdlib-only) in `find_evil_auto.py` and
unit-test it by importing the module under the 3.11 agent venv
(`uv run pytest`, `sys.path.insert(scripts/)`) — see `services/agent/tests/test_memory_hooks.py`.
The MCP *tools* (agent_mcp server) DO have findevil_agent — only the thin host engine doesn't.

## Hermes cross-case memory is now wired (was dormant) — provenance, never evidence

`memory_recall`/`memory_remember` were registered tools but never invoked. Now: `reason()` calls
`_enrich_findings_with_recall` (recall each finding's MITRE/IOC term → attach hits as a
NON-evidentiary `prior_observations` field), and `run()` calls `_remember_confirmed` after
`_emit_final_findings` (remember CONFIRMED findings). Both pass `audit_log_path` so the tool
**calls** are hash-chained, but the `memory_recall`/`memory_remember` audit kinds are **excluded
from the Merkle root** (`build_manifest` only leafs `tool_call_output`+`finding_approved`) — so
memory never inflates `leaf_count` and never becomes a `tool_call_id`. Verified live on the
DE_1102 evtx: 2nd run recalls the 1st run's finding (`prior_observations` populated), manifest
still PASSes. Store path = `resolve_memory_store_path` (`$FINDEVIL_MEMORY_STORE` →
`~/.findevil/memory/memory.sqlite`). See [[Key Decisions#Memory is never evidence]] and [[Patterns]].

Related: [[Key Decisions]] · [[Patterns]] · [[North Star]]
