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

Related: [[Key Decisions]] · [[Patterns]] · [[North Star]]
