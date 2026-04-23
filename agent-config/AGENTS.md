# AGENTS.md — Roles and Routing

## supervisor
Owns the investigation plan. Decomposes goals into sub-tasks. Never touches evidence directly; only dispatches.

## disk_analyst
Tools: sift.mft_timeline, sift.usnjrnl, sift.prefetch, sift.amcache, sift.shimcache, sift.registry.
Scope: filesystem + registry artifacts.

## memory_analyst
Tools: sift.vol_pslist, sift.vol_malfind, sift.vol_netscan, sift.vol_cmdline.
Scope: volatile memory captures only.

## log_analyst
Tools: sift.evtx_query, sift.sysmon_parse, sift.iis_parse.
Scope: Windows Event Log, Sysmon, app logs.

## verifier
Tools: read-only. Re-executes tool_calls behind every claim before report write-out.
Veto power: can reject any finding lacking tool_call_id.

## Routing rules
- Identity/account questions -> log_analyst first
- Persistence questions -> disk_analyst + log_analyst (must agree)
- Live-process questions -> memory_analyst
- Report assembly -> supervisor, gated by verifier
