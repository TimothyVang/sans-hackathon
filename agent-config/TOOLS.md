# TOOLS.md — MCP Surface

## sift.mft_timeline
Args: {image_path: str, start?: iso8601, end?: iso8601}
Returns: rows of {ts, src_attr, path, size, inode}
Use when: you need file creation/modification ordering. Prefer $FN over $SI.

## sift.vol_pslist
Args: {dump_path: str, profile?: str}
Returns: {pid, ppid, name, create_time, exit_time, cmdline}
Use when: enumerating processes from a memory image. Pair with vol_malfind.

## sift.vol_malfind
Args: {dump_path: str, pid?: int}
Returns: {pid, vad_start, protection, hex_preview}
Use when: hunting injected code. RWX + MZ header = high signal.

## sift.yara_scan
Args: {target_path: str, rules_path: str}
Returns: {file, rule, offset, strings[]}
Use when: IOC match needed. Always cite rule name in findings.

## sift.evtx_query
Args: {evtx_path: str, eids?: int[], xpath?: str}
Returns: event rows.
Use when: account/logon/service/task questions.

## Invariants
- Every call emits a `tool_call_id`. Findings cite it.
- No tool mutates evidence. All reads operate on write-blocked copies.
