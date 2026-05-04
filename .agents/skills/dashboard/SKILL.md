---
name: dashboard
description: Open or start the local Find Evil dashboard and Codex investigation cockpit when the operator asks for /dashboard, dashboard, Codex UI, chat window, suggested investigations, or localhost:3000/codex.
---

# Find Evil Dashboard

Use this skill when the operator asks to open the dashboard, use `/dashboard`, start the Codex cockpit, or inspect the web UI.

## Safety Rules

- Do not change the MCP surface.
- Do not mutate evidence.
- Do not add broad MCPs such as filesystem, browser, Docker, Kubernetes, GitHub, or fetch.
- Do not print or store secrets.
- Keep the web dashboard local to this machine.

## What To Open

- Audit dashboard: `http://localhost:3000/`
- Codex investigation cockpit: `http://localhost:3000/codex`
- Raw audit stream debugger: `http://localhost:3000/debug`

Default to `/codex` when the user says `/dashboard` from a Codex session, because that page contains suggested Find Evil investigation prompts and the optional chat runner.

## Launch Procedure

1. Check whether `http://localhost:3000/codex` is already responding.
2. If it is not responding, start the dashboard with `scripts/codex-dashboard.ps1` on Windows or `scripts/codex-dashboard.sh` on POSIX.
3. Confirm that `/codex` returns HTTP 200.
4. Tell the operator the URL to open.

The launcher enables `FINDEVIL_CODEX_UI_ENABLE=1` for the local process so the optional one-shot Codex runner is available. The route is still constrained by the app's allow-list and per-mode MCP tool allow-lists.

## Expected Commands

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/codex-dashboard.ps1
```

POSIX shell:

```bash
bash scripts/codex-dashboard.sh
```

## Operator Response

After launch, respond with:

```text
Dashboard is running:
- Codex cockpit: http://localhost:3000/codex
- Audit dashboard: http://localhost:3000/
- Debug stream: http://localhost:3000/debug
```

If startup fails, report the exact failing command and log path.
