# TOOLS.md — MCP Surface

The agent has access to two MCP servers, both auto-spawned by Claude Code via `.mcp.json` at session start. **No `execute_shell` exists** — the typed surface below is the only verb set the agent has.

| Server | Lang | Tools |
|---|---|---|
| `findevil-mcp` | Rust (`services/mcp/`) | 12 typed DFIR tools |
| `findevil-agent-mcp` | Python (`services/agent_mcp/`) | 10 crypto + ACH tools |

Every successful tool call carries `_meta.output_sha256` (hex SHA-256 of the canonical JSON output). Findings cite tool calls by `tool_call_id`. The verifier vetoes any finding that doesn't.

---

## Rust DFIR tools (`findevil-mcp`)

### case_open
Args: `{image_path: str, expected_sha256?: str, label?: str}`
Returns: `{id, image_path, image_hash, size_bytes, opened_at}`
Use when: starting an investigation. **Must be called first** — every subsequent tool needs the `case_id`. The image hash is the first audit-chain leaf; if the agent passes `expected_sha256` and it doesn't match, `case_open` errors before any other tool runs.

### evtx_query
Args: `{case_id, evtx_path, event_ids?: int[], xpath?: str, since_iso?, until_iso?, limit?}`
Returns: `{events[], rows_seen, parse_errors}`
Use when: account/logon/service/scheduled-task/process-creation questions. In-process via `evtx = 0.11.2` (~1600× faster than python-evtx). `event_ids` filter is the cheap path; `xpath` allows arbitrary XPath 1.0 against the rendered XML. Always pair Type 3 (Network logon) findings with the source IP — internal RFC1918 is almost always benign.

### prefetch_parse
Args: `{case_id, prefetch_path}`
Returns: `{executable_name, run_count, last_run_times[], volumes[], file_references[], prefetch_hash}`
Use when: confirming execution. Every `.pf` file proves the named binary ran on this host at the named UTC times — not just "was registered." Prefer this over Amcache (which is *catalog*-registration time, not execution).

### mft_timeline
Args: `{case_id, mft_path, start_iso?, end_iso?, path_glob?, limit?}`
Returns: `{rows[], rows_seen, parse_errors}` where each row is `{ts, src_attr ($SI/$FN), path, size, inode, is_allocated}`
Use when: filesystem creation/modification ordering, especially for "what changed in the compromise window?" Prefer `$FN` over `$SI` (anti-forensics tooling stomps `$SI`, rarely `$FN`). `path_glob` accepts standard glob (`*`, `?`, `**`). Read `is_allocated` to detect deleted files.

### registry_query
Args: `{case_id, hive_path, key_path, value_name?, recursive?, depth?, limit?}`
Returns: `{entries[]}` with `{key, name, type, data}` formatted by RegValue type (REG_SZ→text, REG_MULTI_SZ→pipe-joined, REG_DWORD→decimal, REG_BINARY→hex truncated at 4096B)
Use when: persistence questions (Run/RunOnce, Services, IFEO, AppInit_DLLs), user-context (NTUSER.DAT shellbags, MRUs), ShimCache, BAM. Pass the primary hive only; transaction logs (`.LOG1` / `.LOG2`) are not auto-merged. `recursive=true` walks depth-first capped at 16 by default.

### yara_scan
Args: `{case_id, target_path, rules_paths[], recursive?, max_matches_per_rule?, max_total_matches?, limit?}`
Returns: `{matches[], files_scanned, rules_compiled, scan_errors}`
Use when: IOC matching. In-process via `yara-x = 1.12.0` (BSD-3-Clause, VirusTotal pure-Rust YARA). Each match shows `{rule_name, namespace, tags, pattern_matches[]}` with offset+length+64-byte hex preview. **Always cite the rule name in findings.** Prefer YARA-Forge `core` tier (curated low-FP); `extended`/`community` tiers without corroboration are FP-prone.

### usnjrnl_query
Args: `{case_id, journal_path, since_iso?, until_iso?, reasons[]?, mft_entry?, parent_mft_entry?, limit?}`
Returns: `{entries[], records_seen, parse_errors, row_count, major_version}`
Use when: tracking filesystem changes the MFT can't show (deleted-file event sequences, rename chains, hard-link manipulation). `reasons[]` filters by USN reason flag names (FILE_CREATE, FILE_DELETE, RENAME_NEW_NAME, etc.; case-insensitive). Multi-GB journals stream — no OOM.

### hayabusa_scan
Args: `{case_id, evtx_dir, rules_dir?, min_level?, limit?}`
Returns: `{events[], events_seen, stderr_tail}` where each event is `{timestamp_iso, rule, level, channel, event_id, computer, details}`
Use when: Sigma-rule sweep over an EVTX directory. Subprocess to `hayabusa` (AGPL — never linked). `min_level` ∈ {informational, low, medium, high, critical}. Pre-compiled Hayabusa rules expected at `~/hayabusa/rules` unless `rules_dir` is overridden. False-positive note: routine admin activity (Sysinternals tools, scheduled WMI, AV updates) trips medium-severity rules; pair every Hayabusa hit with `prefetch_parse` and `evtx_query 4624` cross-corroboration before believing it.

### vol_pslist
Args: `{case_id, memory_path, pid_filter?: int[], limit?}`
Returns: `{processes[], processes_seen, stderr_tail}` where each process is `{pid, ppid, image_name, create_time_iso, exit_time_iso?, threads, handles, session_id, wow64}`
Use when: enumerating processes from a memory image via the kernel's active list. **Always pair with `vol_psscan` for DKOM cross-validation.** pslist=0 + psscan>0 is the textbook T1014 (Rootkit) signature. Subprocess to `volatility3` (BSD-2 — never linked, env var `$VOLATILITY_BIN` first then PATH).

### vol_psscan
Args: `{case_id, memory_path, pid_filter?: int[], limit?}`
Returns: `{processes[], processes_seen, stderr_tail}` — same shape as `vol_pslist` but with `offset_v` (EPROCESS virtual address)
Use when: cross-validating `vol_pslist` for DKOM detection. psscan signature-scans EPROCESS pool memory, finding orphaned `_EPROCESS` blocks unlinked from the active list. **The redundancy is deliberate** — divergence between pslist and psscan IS the rootkit finding.

### vol_malfind
Args: `{case_id, memory_path, pid_filter?: int[], limit?}`
Returns: `{injections[], injections_seen, stderr_tail}` where each injection is `{pid, image_name, vad_start_hex, vad_end_hex, protection, mz_match: bool, sample_hex}` (64-byte preview)
Use when: hunting injected code (T1055). `mz_match=true` + RWX `protection` + non-Microsoft-signed parent process = high-confidence injection. Slowest of the vol_* tools — give it a 30-minute timeout on 5GB+ memory images (the orchestrator already does).

### vel_collect
Args: `{case_id, artifact: str, args?: {str: str}, format?, limit?}`
Returns: `{rows[], rows_seen, stderr_tail}` — `rows` are free-form (every Velociraptor artifact has its own column shape; typed-here would be hostile)
Use when: any of Velociraptor's 200+ DFIR artifacts (`Windows.Forensics.Prefetch`, `Generic.Forensic.LocalHashes`, etc.). `artifact` validated against dotted-path pattern, `args` keys validated against `[A-Za-z_][A-Za-z0-9_]*` to block flag injection. Subprocess to `velociraptor` (Apache-2.0; env var `$VELOCIRAPTOR_BIN` first then PATH).

---

## Python crypto + ACH tools (`findevil-agent-mcp`)

### audit_append
Args: `{path, kind, payload}`
Returns: `{record, prev_hash, new_hash, seq}`
Use when: writing any record to the hash-chained audit log. Every tool call, finding emission, agent message, judge selfscore record goes here. The `prev_hash` is auto-computed.

### audit_verify
Args: `{path}`
Returns: `{ok: bool, record_count, broken_seq?, broken_field?}`
Use when: replaying an audit chain to confirm integrity. Walk every `prev_hash` SHA-256 link; first mismatch reports the seq + field. The `manifest_verify` tool calls this internally.

### manifest_finalize
Args: `{case_id, run_id, started_at, audit_log_path, output_path, signer, extra?}`
Returns: `{leaf_count, merkle_root_hex, signature_payload_sha256}` — the on-disk manifest also has `signature.cert_fingerprint`, `leaves[]`, `finalized_at`
Use when: closing a case. Builds the rs_merkle tree over every audit-log leaf, signs with sigstore (or `signer="stub"` in dev), writes `run.manifest.json`. Must run BEFORE `ots_stamp`.

### manifest_verify
Args: `{manifest_path}`
Returns: `{overall: bool, audit_chain_ok, merkle_root_ok, signature_present, ...}`
Use when: any third party wants offline verification. Replays the audit chain → recomputes the Merkle root from `leaves[]` → checks signature presence. Tampering with `merkle_root_hex` produces a precise diagnostic naming both the declared and rebuilt roots.

### ots_stamp
Args: `{manifest_path}`
Returns: `{ots_path, calendar_servers}`
Use when: anchoring a manifest to Bitcoin via OpenTimestamps. Network-required; emits `<manifest>.ots`. Demonstrates FRE 902(14) self-authenticating evidence — the proof matures over ~1 hour as Bitcoin confirms the calendar's batch root.

### ots_verify
Args: `{ots_path, manifest_path}`
Returns: `{ok: bool, attested_at?, block_height?, calendar_attestations[]}`
Use when: confirming the Bitcoin anchor. Offline once the proof has matured (cached in the `.ots` file).

### verify_finding
Args: `{finding, tool_call_index, findevil_mcp_command: list[str]}`
Returns: `{action: 'approved'|'rejected'|'downgraded', replay_record}`
Use when: re-running a finding's cited `tool_call_id` to confirm the original output's SHA-256 still matches. The verifier spawns its own short-lived findevil-mcp child process — same binary, same args, same hash, byte-for-byte. Budget 30s/finding per Spec #2 §8.1.

### detect_contradictions
Args: `{case_id, pool_a, pool_b, resolution_required?: bool}`
Returns: `{contradictions[], pool_a_count, pool_b_count}`
Use when: surfacing Pool A vs Pool B disagreements BEFORE judging. Same-`tool_call_id` findings with different `confidence` levels or contradicting `mitre_technique` labels emit. **Surface the contradictions first; the analyst sees them before the judge merges.**

### judge_findings
Args: `{pool_a_findings, pool_b_findings, pool_a_verifier_actions, pool_b_verifier_actions}`
Returns: `{merged[], budget_exceeded: bool}`
Use when: credibility-weighted merge after verification. Each pool's score = `base_confidence × pool_credibility`. Pools that produced corroborating CONFIRMED findings build credibility; pools that produced HYPOTHESIS-only get downweighted.

### correlate_findings
Args: `{findings}`
Returns: `{outcomes[]}` where each outcome is `{action: 'kept'|'downgraded', reason}`
Use when: enforcing the SOUL.md ≥2-artifact-class rule. A finding claiming "X executed" must cite ≥2 distinct artifact classes (Prefetch + Amcache+ShimCache, or EDR + memory). Single-source claims auto-downgrade.

---

## End-of-investigation

Per `agent-config/JUDGING.md` §End-of-investigation, after `correlate_findings` returns and BEFORE `manifest_finalize`, the supervisor emits **6 `kind=judge_selfscore` audit records** — one per SANS Find Evil! 2026 rubric criterion (failures+corrections, confidence distribution, artifact classes, typed-surface rejections, citation rate, reproducibility). The orchestrator (`scripts/find_evil_auto.py::_emit_judge_selfscore`) does this automatically. Judges grep `"kind":"judge_selfscore"` to find the agent's own assessment cryptographically locked.

---

## Invariants

- **Every call emits a `tool_call_id`.** Findings cite it. Verifier vetoes uncited.
- **No tool mutates evidence.** All reads operate on read-only mounts; original images stay untouched.
- **No `execute_shell`.** The narrow typed surface above is the entire verb set. Adding shell pass-through breaks the architectural-guardrail story.
- **AGPL/GPL backing tools (Hayabusa, Volatility3, Velociraptor, YARA core) are subprocess-only — never linked.** Apache-2.0 license clean.
- **All timestamps UTC, ISO-8601, trailing `Z`.** SHA-256 preferred over MD5.
