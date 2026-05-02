# Find Evil! Product Implementation Plan

> **Status: RETIRED (with A2 + A5 carve-outs noted in the superseded-by banner below).** Shipped across `services/mcp/` (Rust DFIR), `services/agent/findevil_agent/{crypto,verifier,judge,contradiction,correlator,pools}.py` (M2 + M4), and `services/agent_mcp/` (the Python MCP wrapper that A2 introduced). Both MCP servers are auto-spawned by Claude Code via `.mcp.json`. Kept for git-log archaeology. **Do not execute as a TDD plan.**

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Superseded by Amendment A2 (2026-04-25):** Tasks that build the LangGraph runtime, FastAPI service, `graph.py` / `api.py` / `cli.py` / `supervisor.py`, or the `services/agent/specialists/` subagents are no longer the path forward. A2 drops the custom Python orchestrator — Claude Code IS the orchestrator, and the M2 + M4 stacks ship as a Python MCP server (`services/agent_mcp/`). The Rust MCP tool tasks, the M2 cryptographic chain-of-custody tasks, and the M4 ACH logic (verifier / pools / judge / contradictions / correlator) all stand and shipped. The Next.js SPA tasks are deferred to bonus polish. See `docs/specs/2026-04-25-amendment-a2-claude-code-primary-interface.md` for the current architecture.

**Goal:** Build the automated DFIR pipeline (FIND EVIL!) that judges run on the SIFT VM — typed Rust MCP server, LangGraph ACH agent graph, Next.js UI, MCP Apps widgets, cryptographic chain-of-custody.

**Architecture:** Seven layers — evidence vault, SIFT tool subprocesses, typed Rust MCP server (rmcp 0.16.x), three-layer memory (DuckDB per case / SqliteSaver / Hermes cross-case), M4 ACH agent graph (single supervisor + two opposing-prior pools + judge + contradiction node), FastAPI+LangGraph Python runtime, Next.js 15 SPA + MCP Apps widgets.

**Tech Stack:** Rust 1.88 (bumped from the original 1.83 pin — see CLAUDE.md "Spec/code divergences" §1; rmcp 0.16.x, evtx 0.11.2, rs_merkle 1.4.0, duckdb 0.10, pyo3), Python 3.11 (langgraph>=1.0, anthropic Claude Agent SDK, fastapi, sigstore 3.x, opentimestamps-client), Next.js 15 + shadcn + Tailwind v4 + @ai-sdk/react, Hayabusa/Chainsaw/Volatility3/Velociraptor as subprocess-only (AGPL/GPL).

---

## Conventions

- Every task follows TDD: write failing test first, confirm failure, implement, confirm green, then commit.
- All paths are repository-absolute (relative to project root `C:\Users\newbi\Desktop\PUG Projects\SANS-Hackathon\` / POSIX `~/SANS-Hackathon/`).
- Commit messages use Conventional Commits: `feat(scope):`, `test(scope):`, `chore(scope):`, `fix(scope):`.
- Each task ends with a single commit. Never batch tasks into one commit.
- Run every listed command and verify the expected output line appears before checking the step.
- Never use `--no-verify`, `--no-gpg-sign`, or amend commits in this plan.

---

# GROUP A — Rust MCP Server (Weeks 2–3)

## Task A1 — Cargo workspace + `services/mcp/Cargo.toml` with pinned deps

- [ ] Create workspace root `Cargo.toml` at repo root with `[workspace] members = ["services/mcp"]` and `resolver = "2"`.
- [ ] Create `services/mcp/Cargo.toml` with `[package] name = "findevil-mcp"`, `version = "0.1.0"`, `edition = "2021"`, `rust-version = "1.88"` (the original spec pin was 1.83 — see CLAUDE.md "Spec/code divergences" §1).
- [ ] Add pinned `[dependencies]`:
  - `rmcp = { version = "=0.16.0", features = ["server", "transport-io"] }`
  - `evtx = "=0.11.2"`
  - `rs_merkle = "=1.4.0"`
  - `duckdb = { version = "=0.10.2", features = ["bundled"] }`
  - `pyo3 = { version = "=0.22", features = ["auto-initialize"] }`
  - `serde = { version = "=1.0.210", features = ["derive"] }`
  - `serde_json = "=1.0.128"`
  - `tokio = { version = "=1.40", features = ["macros", "rt-multi-thread", "process", "io-util"] }`
  - `sha2 = "=0.10.8"`
  - `hex = "=0.4.3"`
  - `uuid = { version = "=1.10", features = ["v4"] }`
  - `anyhow = "=1.0.89"`
  - `thiserror = "=1.0.64"`
  - `tracing = "=0.1.40"`
- [ ] Add `[dev-dependencies]`: `tempfile = "=3.12"`, `assert_cmd = "=2.0"`, `pretty_assertions = "=1.4"`.
- [ ] Write failing test `services/mcp/tests/version_pins.rs` that invokes `cargo tree -p findevil-mcp --depth 1 --prefix none` and asserts every dep line matches one of the pinned versions.
- [ ] Run `cargo check --workspace`. Expected output contains `Finished \`dev\` profile`.
- [ ] Run `cargo test -p findevil-mcp --test version_pins`. Expected: PASS.
- [ ] Commit: `chore(mcp): scaffold cargo workspace with pinned rmcp 0.16 deps`.

## Task A2 — `services/mcp/src/lib.rs` + `main.rs` rmcp ServerHandler over stdio

- [ ] Write failing test `services/mcp/tests/stdio_handshake.rs`: spawns `findevil-mcp` binary via `assert_cmd::Command`, writes a JSON-RPC `initialize` request on stdin, asserts reply has `"serverInfo": { "name": "findevil-mcp", "version": "0.1.0" }`.
- [ ] Run `cargo test -p findevil-mcp --test stdio_handshake`. Expected: fails with "no such binary" or non-zero exit.
- [ ] Create `services/mcp/src/lib.rs`: define `struct FindEvilServer;` implementing `rmcp::ServerHandler`. Required methods: `get_info()` returns `ServerInfo { name: "findevil-mcp", version: "0.1.0", capabilities: ServerCapabilities::default() }`. Register empty `tools()` list.
- [ ] Create `services/mcp/src/main.rs`: `#[tokio::main] async fn main() -> anyhow::Result<()>` → builds `FindEvilServer` and calls `rmcp::transport::stdio::serve(server).await`.
- [ ] Run `cargo build -p findevil-mcp --release`. Expected: `Compiling findevil-mcp`.
- [ ] Run `cargo test -p findevil-mcp --test stdio_handshake`. Expected: PASS.
- [ ] Commit: `feat(mcp): rmcp ServerHandler over stdio transport`.

## Task A3 — `tools/case_open.rs` + `tests/tool_smoke.rs` (SHA-256 + libewf + DuckDB init)

- [ ] Write failing test `services/mcp/tests/tool_smoke.rs` function `test_case_open_returns_handle`:
  - creates tempdir, writes `fixture.e01` (64-byte zeroed file — libewf signature stub accepted in test mode)
  - calls `case_open` via JSON-RPC with `{ "image_path": "<path>" }`
  - asserts reply has `case_id` matching UUID4, `db_path` ends `/evidence.ddb`, `image_hash` is 64-char hex, `image_size_bytes == 64`.
- [ ] Run `cargo test -p findevil-mcp --test tool_smoke test_case_open_returns_handle`. Expected: fails (tool unregistered).
- [ ] Create `services/mcp/src/tools/mod.rs` with `pub mod case_open;` and a `Tool` enum used by `dispatch`.
- [ ] Create `services/mcp/src/tools/case_open.rs`:
  - `#[derive(Deserialize)] pub struct CaseOpenInput { image_path: String }`
  - `#[derive(Serialize)] pub struct CaseHandle { id: String, db_path: String, image_hash: String, image_size_bytes: u64 }`
  - `pub async fn case_open(input: CaseOpenInput) -> Result<CaseHandle, ToolError>`:
    1. verify file exists; `sha2::Sha256` streamed over `tokio::fs::File`; hex-encode digest
    2. generate `case_id = Uuid::new_v4().to_string()`
    3. create `~/.findevil/cases/<case_id>/` directory
    4. open DuckDB connection at `<dir>/evidence.ddb`, run schema DDL (`events`, `findings`, `merkle_leaves`, `audit` tables — see `db/duckdb_case.rs`)
    5. return `CaseHandle`
- [ ] Create `services/mcp/src/db/duckdb_case.rs` with `pub fn init_schema(conn: &duckdb::Connection) -> Result<()>` containing the four `CREATE TABLE` statements (events, findings, merkle_leaves, audit).
- [ ] Register `case_open` in `lib.rs` tool list.
- [ ] Run `cargo test -p findevil-mcp --test tool_smoke test_case_open_returns_handle`. Expected: PASS.
- [ ] Commit: `feat(mcp): case_open tool with SHA-256 verify + DuckDB init`.

## Task A4 — `tools/evtx_query.rs` (evtx 0.11.2 in-process + DuckDB insert)

- [ ] Download OTRF Mordor fixture `security-mordor-1.evtx` into `services/mcp/tests/fixtures/` (git-lfs track `.evtx`). If not available, check for any SANS-provided EVTX under `fixtures/`.
- [ ] Add failing test `services/mcp/tests/tool_smoke.rs::test_evtx_query_populates_duckdb`:
  - opens case, invokes `evtx_query` with `{ evtx_path: "<fixture>", eids: [4624] }`
  - asserts returned `Vec<EvtxRow>` length > 0 AND DuckDB `SELECT COUNT(*) FROM events WHERE event_id = 4624` matches.
- [ ] Run the test. Expected: fails (tool not registered).
- [ ] Create `services/mcp/src/tools/evtx_query.rs`:
  - input: `EvtxQueryInput { case_id: String, evtx_path: String, eids: Option<Vec<u32>>, xpath: Option<String> }`
  - output row: `EvtxRow { event_id: u32, ts: String, channel: String, record_id: u64, data: serde_json::Value }`
  - iterate `evtx::EvtxParser::from_path(&evtx_path)?`, apply eids filter, batch-insert into DuckDB `events` via prepared statement, return rows (cap 10,000).
- [ ] Register `evtx_query` in tool list.
- [ ] Run `cargo test -p findevil-mcp --test tool_smoke test_evtx_query_populates_duckdb`. Expected: PASS.
- [ ] Commit: `feat(mcp): evtx_query tool with in-process evtx crate + DuckDB insert`.

## Task A5 — `tools/mft_timeline.rs` (Chainsaw v2 subprocess)

- [ ] Add failing integration test `services/mcp/tests/tool_smoke.rs::test_mft_timeline_invokes_chainsaw`:
  - gates on env `CHAINSAW_BIN` (skip with `println!` + `return` if unset)
  - asserts returned `Vec<MftRow>` has at least one row with non-empty `path`.
- [ ] Run the test. Expected: fails (tool missing) or skips when env unset.
- [ ] Create `services/mcp/src/tools/mft_timeline.rs`:
  - input: `MftTimelineInput { case_id: String, start: Option<String>, end: Option<String> }`
  - output row: `MftRow { ts: String, src_attr: String, path: String, size: u64, inode: u64 }`
  - spawn `tokio::process::Command::new(chainsaw_bin()).args(["mft", "--format=jsonl", "--output=-", "<image>"])` with 120s timeout, parse JSONL lines, apply optional date window.
- [ ] Add helper `services/mcp/src/config.rs::chainsaw_bin() -> PathBuf` (reads `FINDEVIL_CHAINSAW` env, defaults to `~/.local/bin/chainsaw`).
- [ ] Register tool.
- [ ] Run `CHAINSAW_BIN=~/.local/bin/chainsaw cargo test -p findevil-mcp test_mft_timeline_invokes_chainsaw`. Expected: PASS (or skip with message when unset in CI).
- [ ] Commit: `feat(mcp): mft_timeline via Chainsaw v2 subprocess with 120s cap`.

## Task A6 — `tools/hayabusa_scan.rs` (Hayabusa 2.x subprocess + JSONL parse)

- [ ] Add failing test `test_hayabusa_scan_parses_jsonl` (env-gated on `HAYABUSA_BIN`):
  - returns `Vec<HayabusaHit>` with at least one `sigma_id` populated.
- [ ] Run. Expected: fails.
- [ ] Create `services/mcp/src/tools/hayabusa_scan.rs`:
  - input: `HayabusaScanInput { case_id: String, profile: Option<String>, min_level: Option<String> }`
  - output row: `HayabusaHit { ts: String, eid: u32, rule: String, level: String, details: serde_json::Value, sigma_id: String }`
  - spawn `hayabusa csv-timeline -d <evtx_dir> -o - --profile <profile|"standard"> --min-level <min_level|"medium"> --json-output`
  - 120s timeout; stream stdout; parse JSONL line-by-line.
- [ ] Register tool; ensure supervisor can call it immediately after `case_open` (pre-warm path).
- [ ] Run the gated test. Expected: PASS.
- [ ] Commit: `feat(mcp): hayabusa_scan JSONL parser with min_level filter`.

## Task A7 — `tools/vol_pslist.rs` + `tools/vol_malfind.rs` (Volatility3 subprocess)

- [ ] Add failing test `test_vol_pslist_returns_processes` gated on `VOLATILITY_BIN` + `MEMORY_DUMP_FIXTURE`.
- [ ] Run. Expected: fails.
- [ ] Create `services/mcp/src/tools/vol_pslist.rs`:
  - input: `VolPsListInput { case_id: String, dump_path: String, profile: Option<String> }`
  - output row: `ProcessRow { pid: u32, ppid: u32, name: String, create_time: String, cmdline: Option<String> }`
  - spawn `vol -f <dump_path> -r json windows.pslist`, parse JSON array into rows.
- [ ] Create `services/mcp/src/tools/vol_malfind.rs`:
  - input: `VolMalfindInput { case_id: String, dump_path: String, pid: Option<u32> }`
  - output row: `MalfindRow { pid: u32, vad_start: String, protection: String, hex_preview: String }`
  - spawn `vol -f <dump_path> -r json windows.malfind` optionally filter by pid.
- [ ] Add failing test `test_vol_malfind_returns_vads`.
- [ ] Register both tools.
- [ ] Run gated tests. Expected: PASS.
- [ ] Commit: `feat(mcp): vol_pslist + vol_malfind via Volatility3 subprocess`.

## Task A8 — `tools/yara_scan.rs` (YARA Forge Core tarball)

- [ ] Add failing test `test_yara_scan_detects_eicar`:
  - drops EICAR-like string (`X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*`) into tempfile
  - runs `yara_scan` with ruleset name `"forge_core"` against tempdir
  - asserts at least one `YaraHit` with `rule` matching `"EICAR.*"`.
- [ ] Run. Expected: fails.
- [ ] Create `services/mcp/src/tools/yara_scan.rs`:
  - input: `YaraScanInput { case_id: String, target_path: String, ruleset: String }`
  - output row: `YaraHit { file: String, rule: String, offset: u64, strings: Vec<String> }`
  - resolve ruleset → `~/.findevil/yara/<ruleset>/packaged.yar`; spawn `yara -r -s <rules> <target>`; parse line format `rule [meta] file:offset: $str`.
- [ ] Add install step: `scripts/install.sh` downloads weekly YARA Forge Core tarball to `~/.findevil/yara/forge_core/`.
- [ ] Register tool.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(mcp): yara_scan with YARA Forge Core ruleset resolution`.

## Task A9 — `tools/usnjrnl_query.rs` + `registry_query.rs` + `prefetch_parse.rs` (Chainsaw subprocess)

- [ ] Add three failing tests in `tool_smoke.rs` (`test_usnjrnl_query_extracts_rows`, `test_registry_query_reads_hive`, `test_prefetch_parse_counts_runs`) gated on `CHAINSAW_BIN` + relevant fixtures under `services/mcp/tests/fixtures/`.
- [ ] Run. Expected: fail.
- [ ] Create `services/mcp/src/tools/usnjrnl_query.rs`:
  - input: `UsnJrnlInput { case_id, start?, end? }`, row: `UsnRow { ts, file_name, reason, mft_ref }`
  - spawn `chainsaw usnjrnl --json-output <image>`.
- [ ] Create `services/mcp/src/tools/registry_query.rs`:
  - input: `{ case_id, hive_path, key_path }`, row: `RegistryRow { key, value_name, value_type, data }`
  - spawn `chainsaw registry --hive <hive_path> --key <key_path> --json-output`.
- [ ] Create `services/mcp/src/tools/prefetch_parse.rs`:
  - input: `{ case_id, pf_path? }`, row: `PrefetchRow { executable, run_count, last_run, volumes }`
  - spawn `chainsaw prefetch --json-output <path>`.
- [ ] Register all three.
- [ ] Run tests. Expected: PASS.
- [ ] Commit: `feat(mcp): usnjrnl/registry/prefetch Chainsaw subprocess wrappers`.

## Task A10 — `tools/vel_collect.rs` (Velociraptor gRPC)

- [ ] Add failing test `test_vel_collect_invokes_grpc` gated on `VELOCIRAPTOR_BIN`.
- [ ] Run. Expected: fails.
- [ ] Create `services/mcp/src/tools/vel_collect.rs`:
  - input: `VelCollectInput { case_id: String, artifact: String }`
  - output row: `ArtifactRow { artifact, key, value: serde_json::Value, ts: Option<String> }`
  - spawn `velociraptor artifacts collect --json --artifact=<artifact>` against offline `.e01` mount; parse stdout JSON stream.
- [ ] Register tool.
- [ ] Run the test. Expected: PASS.
- [ ] Commit: `feat(mcp): vel_collect tool via Velociraptor offline collector`.

## Task A11 — `crypto/merkle.rs` + `tests/merkle_roundtrip.rs` (rs_merkle prove leaf 42)

- [ ] Write failing test `services/mcp/tests/merkle_roundtrip.rs::test_insert_100_prove_42`:
  - create `MerkleState`, append 100 SHA-256 leaves (`leaf_i = sha256(format!("leaf-{}", i))`)
  - call `prove_leaf(42)` → returns `(leaf_hash, proof_hashes, root)`
  - verify with `rs_merkle::MerkleProof::verify(root, &[42], &[leaf_hash], 100)` returns `true`
  - negative case: mutate leaf 42 hash → verify returns `false`.
- [ ] Run. Expected: fails (module missing).
- [ ] Create `services/mcp/src/crypto/mod.rs` and `services/mcp/src/crypto/merkle.rs`:
  - `pub struct MerkleState { tree: rs_merkle::MerkleTree<Sha256Algo>, leaves: Vec<[u8;32]> }`
  - `append_leaf(&mut self, payload: &[u8]) -> usize`
  - `root(&self) -> [u8;32]`
  - `prove_leaf(&self, index: usize) -> Result<MerkleProofBundle>`
  - strictly append-only (no `remove_leaf`; no `reset`).
- [ ] Run `cargo test -p findevil-mcp --test merkle_roundtrip`. Expected: PASS.
- [ ] Commit: `feat(mcp): append-only rs_merkle state with prove-leaf-42 test`.

## Task A12 — `crypto/manifest.rs` (RunManifest + JCS RFC 8785 serialization)

- [ ] Write failing test `services/mcp/tests/manifest_jcs.rs::test_jcs_canonical_form_stable`:
  - build `RunManifest { case_id, merkle_root, leaves, findings, created_at }`
  - serialize twice via `manifest.to_jcs_bytes()` with fields inserted in different orders → both byte-identical
  - assert SHA-256 of canonical bytes matches a stored fixture hex string.
- [ ] Run. Expected: fails.
- [ ] Create `services/mcp/src/crypto/manifest.rs`:
  - `#[derive(Serialize, Deserialize)] pub struct RunManifest { case_id: String, merkle_root: String, leaves: Vec<MerkleLeafRef>, findings: Vec<FindingRef>, created_at: String }`
  - `pub fn to_jcs_bytes(&self) -> Result<Vec<u8>>` — use `serde_jcs` crate (add dep `serde_jcs = "=0.1.0"` to Cargo.toml) to emit RFC 8785 canonical JSON.
- [ ] Add `serde_jcs = "=0.1.0"` to Cargo.toml deps.
- [ ] Run `cargo test -p findevil-mcp --test manifest_jcs`. Expected: PASS.
- [ ] Commit: `feat(mcp): RunManifest with JCS RFC 8785 canonical serialization`.

---

# GROUP B — Python Agent Service (Weeks 3–4)

## Task B1 — `services/agent/pyproject.toml` with pinned deps

- [ ] Create `services/agent/pyproject.toml` (uv-managed) with:
  - `[project] name = "findevil-agent"`, `version = "0.1.0"`, `requires-python = ">=3.11,<3.12"`
  - `dependencies`:
    - `langgraph==1.0.0`
    - `langgraph-checkpoint-sqlite==1.0.0`
    - `anthropic==0.45.0`
    - `claude-agent-sdk==0.3.0`
    - `fastapi==0.115.0`
    - `uvicorn[standard]==0.32.0`
    - `sigstore==3.5.0`
    - `opentimestamps-client==0.7.2`
    - `pydantic==2.9.2`
    - `pydantic-to-typescript==2.0.0`
    - `duckdb==1.1.1`
    - `mitreattack-python==3.0.6`
    - `httpx==0.27.2`
    - `python-ulid==3.0.0`
  - `[project.scripts] find-evil = "findevil_agent.cli:main"`
- [ ] Write failing test `services/agent/tests/test_deps_pinned.py` using `importlib.metadata.version` asserting exact pinned values.
- [ ] Run `uv sync --directory services/agent`. Expected: `Resolved N packages`.
- [ ] Run `uv run --directory services/agent pytest tests/test_deps_pinned.py`. Expected: PASS.
- [ ] Commit: `chore(agent): pyproject with langgraph 1.0 + sigstore 3.x pinned deps`.

## Task B2 — `services/agent/config.py` + `resolve_credentials()` (Amendment A1)

- [ ] Write failing test `tests/test_resolve_credentials.py` with four parametrized cases:
  - env `CLAUDE_CODE_HARNESS=1` → returns `"claude_code"`
  - `~/.claude/` exists + valid session → returns `"claude_code"`
  - only `ANTHROPIC_API_KEY=sk-ant-x` set → returns `"api_key"`
  - no env, no dir → raises `CredentialsError` with message containing both `claude auth login` and `ANTHROPIC_API_KEY`.
- [ ] Use `monkeypatch` + `tmp_path` for fake `~/.claude/`.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/config.py`:
  - `MODEL: Final[str] = "claude-opus-4-7"` (one value for both pools, per Spec #2 §8.2)
  - `TOOL_BINARIES: dict[str, Path]` — chainsaw, hayabusa, volatility, yara, velociraptor
  - `BUDGET_SECONDS: Final[int] = 120`
  - `class CredentialsError(RuntimeError): ...`
  - `def resolve_credentials() -> Literal["claude_code", "api_key"]` implementing Amendment A1 §3.1 order of precedence.
- [ ] Run `uv run pytest tests/test_resolve_credentials.py -v`. Expected: 4 PASSED.
- [ ] Commit: `feat(agent): config.py + resolve_credentials() per Amendment A1`.

## Task B3 — `services/agent/events.py` (Pydantic AgentEvent union — 11 variants)

- [ ] Write failing test `tests/test_events_union.py`:
  - parametrize over all 11 event_type literals (`ToolCallStart`, `ToolCallOutput`, `AgentMessage`, `Finding`, `VerifierAction`, `ChainUpdate`, `RunVerdict`, `PlanProposed`, `PlanApproved`, `HypothesisUpdate`, `ContradictionFound`)
  - for each: build minimum-valid dict, `AgentEvent.model_validate(d)` succeeds, `event.model_dump_json()` roundtrips.
  - negative: `Finding` without `tool_call_id` raises `ValidationError`.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/events.py` with all 11 Pydantic v2 classes per Spec #2 §5, and `AgentEvent = Annotated[Union[...], Field(discriminator="event_type")]`.
- [ ] Run test. Expected: 12 PASSED.
- [ ] Commit: `feat(agent): AgentEvent pydantic union (11 discriminated variants)`.

## Task B4 — `services/agent/mcp_client.py` (Rust MCP stdio subprocess manager)

- [ ] Write failing test `tests/test_mcp_client.py::test_invokes_case_open`:
  - spawn mock server script (Python script reading JSON-RPC on stdin, echoing canned `case_open` reply)
  - `client = McpClient(binary=mock_path); handle = await client.call("case_open", {"image_path": "x"})`
  - assert `handle["case_id"]` present, `handle["image_hash"]` is 64-char hex.
  - second test `test_generates_uuid4_tool_call_id` — every call emits `tool_call_id` matching UUID4 regex.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/mcp_client.py`:
  - `class McpClient`: spawns `asyncio.subprocess.create_subprocess_exec(binary, stdin=PIPE, stdout=PIPE)`
  - sends `{"jsonrpc":"2.0","method":"initialize",...}` on start
  - `async def call(method: str, params: dict) -> dict` with request-id counter, response correlation, 120s timeout
  - generates `tool_call_id = str(uuid.uuid4())` per call and propagates into `params._meta.tool_call_id`.
- [ ] Run test. Expected: 2 PASSED.
- [ ] Commit: `feat(agent): mcp_client.py with stdio JSON-RPC dispatch`.

## Task B5 — `services/agent/crypto/signer.py` + test (sigstore 3.x keyless)

- [ ] Write failing test `tests/test_signer.py::test_sign_and_verify_roundtrip`:
  - gated on env `FINDEVIL_RUN_SIGSTORE=1` (skip otherwise to not spam production Fulcio)
  - payload `{"tool_call_id":"...", "tool_name":"evtx_query", "input":{...}, "output_hash":"<sha>", "ts":"...", "case_id":"..."}`
  - `bundle = await signer.sign_tool_call(payload)` → non-empty base64
  - `signer.verify_bundle(bundle, payload)` returns `True`
  - tampering `output_hash` → `verify_bundle` returns `False`.
- [ ] Also add offline test `test_jcs_canonicalization` asserting stable bytes regardless of key order.
- [ ] Run. Expected: offline test fails; sigstore test skips.
- [ ] Create `services/agent/src/findevil_agent/crypto/signer.py`:
  - one ephemeral Fulcio cert per run (lazy `_ensure_identity()`)
  - JCS-canonicalize payload via `rfc8785` helper (add `rfc8785==0.1.3` dep)
  - `sign_tool_call` writes to Rekor async in batches; returns base64 bundle
  - `verify_bundle` replays proof against cached Rekor checkpoint.
- [ ] Update `pyproject.toml` to add `rfc8785==0.1.3`; re-run `uv sync`.
- [ ] Run tests. Expected: JCS test PASS; sigstore test PASS only when env flag set.
- [ ] Commit: `feat(agent): sigstore 3.x keyless signer with JCS canonical payloads`.

## Task B6 — `services/agent/crypto/audit_log.py` + test (hash-chain JSONL)

- [ ] Write failing test `tests/test_audit_log.py`:
  - `log = AuditLog(tmp_path / "audit.jsonl")`
  - append three entries; read file back; assert line 2's `prev_hash` equals `sha256(line 1 bytes)` and line 3 matches line 2.
  - negative: mutate line 2 on disk; `log.verify_chain()` returns `(False, 2)`.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/crypto/audit_log.py`:
  - `class AuditLog`: `append(entry: dict)` computes `prev_hash = sha256(last_line_bytes)` and includes it before writing
  - `verify_chain() -> tuple[bool, int]` returns first tampered line index.
- [ ] Run test. Expected: 2 PASSED.
- [ ] Commit: `feat(agent): audit_log.py hash-chain JSONL with verify_chain()`.

## Task B7 — `services/agent/crypto/ots.py` + test (opentimestamps subprocess)

- [ ] Write failing test `tests/test_ots.py::test_stamp_writes_ots_file` (gated on `FINDEVIL_RUN_OTS=1`):
  - write scratch `manifest.json`; call `await ots.stamp(path)`; assert `manifest.json.ots` exists and is >100 bytes.
  - second test `test_upgrade_poll_non_blocking`: `stamp()` returns immediately (wall clock <3s); `upgrade()` runs in background task.
- [ ] Run. Expected: tests skip or fail.
- [ ] Create `services/agent/src/findevil_agent/crypto/ots.py`:
  - `async def stamp(manifest_path: Path) -> Path`: `await asyncio.create_subprocess_exec("ots", "stamp", str(manifest_path))`
  - `async def upgrade(ots_path: Path, max_attempts=48, interval_seconds=300)`: polls in background via `asyncio.sleep`.
- [ ] Run tests. Expected: PASS when gated env set.
- [ ] Commit: `feat(agent): ots.py wrapper with async upgrade poll`.

## Task B8 — `specialists/disk_analyst.py` + `memory_analyst.py` + `log_analyst.py` (Claude Agent SDK subagents)

- [ ] Write failing test `tests/test_specialists.py::test_disk_analyst_tool_surface`:
  - instantiate `DiskAnalyst(mcp_client=mock)`, inspect `allowed_tools` attr == `{"mft_timeline","usnjrnl_query","prefetch_parse","registry_query"}`.
  - similar for `MemoryAnalyst` (tools = `{"vol_pslist","vol_malfind"}`) and `LogAnalyst` (tools = `{"evtx_query","hayabusa_scan","yara_scan"}`).
  - test that invoking a non-allowed tool raises `ToolNotAllowed`.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/specialists/{disk_analyst,memory_analyst,log_analyst}.py`:
  - each class extends a `BaseSpecialist` using `claude_agent_sdk.Agent`
  - each has class-level `ALLOWED_TOOLS: frozenset[str]`
  - `async def run(goal: str, pool: Literal["A","B"]) -> list[Finding]`.
- [ ] Run tests. Expected: PASS.
- [ ] Commit: `feat(agent): disk/memory/log analyst subagents with tool allowlists`.

## Task B9 — `pools/persistence.py` + `pools/exfil.py` (opposing-prior system prompts)

- [ ] Write failing test `tests/test_pools.py::test_persistence_prompt_contains_priors`:
  - load `PersistencePool` → `prompt` contains `"T1053.005"`, `"T1543.003"`, `"T1546.003"`, `"T1547.001"`, `"T1546.012"`, `"LOLBins"`.
  - `test_exfil_prompt_contains_priors` → contains `"T1071"`, `"T1074"`, `"T1105"`, `"T1567"`, `"T1052.001"`.
  - both pools share same `MODEL` value from `config.MODEL`.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/pools/persistence.py` + `pools/exfil.py`:
  - both classes wire three specialists (disk, memory, log) and expose `async def investigate(case_id, plan) -> list[Finding]`
  - each class has class-level `SYSTEM_PROMPT` with respective MITRE prior list from Spec #2 §8.1
  - both use `config.MODEL` exclusively (no per-pool model override).
- [ ] Run tests. Expected: PASS.
- [ ] Commit: `feat(agent): Pool A persistence + Pool B exfil with opposing priors`.

## Task B10 — `contradiction.py` + test (ContradictionFound before judge)

- [ ] Write failing test `tests/test_contradiction.py::test_contradiction_detects_conflicting_claims`:
  - build two `Finding` lists with same `tool_call_id` but opposite `confidence`
  - `events = await detect_contradictions(pool_a_findings, pool_b_findings)`
  - asserts at least one `ContradictionFound`, `resolution_required == True` in interactive mode, `False` in unattended
  - test that this event is emitted BEFORE judge by asserting return type ordering in an integrated graph fixture.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/contradiction.py`:
  - `async def detect_contradictions(pool_a: list[Finding], pool_b: list[Finding], unattended: bool) -> list[ContradictionFound]`
  - detection rule: same `tool_call_id` cited by both pools with different `confidence`, OR directly contradictory `description` pairs (semantic similarity via Claude classifier call with structured output).
- [ ] Run tests. Expected: PASS.
- [ ] Commit: `feat(agent): contradiction.py detects pool disagreements pre-judge`.

## Task B11 — `judge.py` + test (credibility-weighted merge)

- [ ] Write failing test `tests/test_judge_scoring.py::test_credibility_formula`:
  - parametrize over 5 cases covering the thresholds in Spec #2 §8.2:
    - both pools CONFIRMED, equal credibility → `merged_confidence == 1.0`, verdict `"CONFIRMED"`
    - pool A CONFIRMED (cred 0.8), pool B HYPOTHESIS (cred 0.5) with corroboration → expected ≈ 0.87
    - neither pool cites → `merged_confidence < 0.50` → `"HYPOTHESIS"` + both claims retained
  - second test `test_judge_hard_2min_budget`: judge times out returning best-effort verdict + warning event.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/judge.py`:
  - `async def judge(findings_a, findings_b, credibility_a, credibility_b, budget_seconds=120) -> list[Finding]`
  - implements formula from Spec #2 §8.2 verbatim: `score_X = conf × cred`, `merged = (score_A+score_B)/(cred_A+cred_B)`
  - threshold mapping 0.80/0.50 → CONFIRMED/INFERRED/HYPOTHESIS
  - updates credibility after verifier pass (exposed via `update_credibility` hook).
- [ ] Run tests. Expected: PASS.
- [ ] Commit: `feat(agent): judge.py credibility-weighted merge (Estornell 2025)`.

## Task B12 — `verifier.py` + test (vetoes uncited findings)

- [ ] Write failing test `tests/test_verifier_veto.py`:
  - `Finding` with empty `tool_call_id` → verifier emits `VerifierAction{action: "rejected", reason: "missing tool_call_id"}`
  - `Finding` citing valid `tool_call_id` → re-executes tool; if output hash matches, action=`approved`; if differs, action=`rejected` with reason `"replay mismatch"`.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/verifier.py`:
  - `async def verify(findings, mcp_client, audit_log) -> list[VerifierAction]`
  - for each finding: if `tool_call_id` absent → reject immediately
  - else replay via `mcp_client.call` with stored input; compare output hash vs `ToolCallOutput.output_hash` from `audit.jsonl`.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(agent): verifier.py with tool_call_id veto + replay check`.

## Task B13 — `correlator.py` + test (SOUL.md cross-artifact rules)

- [ ] Write failing test `tests/test_correlator.py`:
  - execution claim (`mitre_technique="T1059"`) backed only by Amcache → correlator downgrades to HYPOTHESIS with reason `"SOUL.md: execution needs Prefetch + Amcache/ShimCache OR EDR"`
  - same claim backed by Prefetch + Amcache → stays CONFIRMED.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/correlator.py`:
  - `async def correlate(findings: list[Finding]) -> list[Finding]`
  - reads SOUL.md rules table (hard-coded from `agent-config/SOUL.md`):
    - execution requires ≥2 artifact classes among {disk:Prefetch, disk:Amcache/ShimCache, logs:EDR, memory:vol}
  - emits downgrade `VerifierAction` event when a rule fires.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(agent): correlator.py enforces SOUL.md cross-artifact execution rule`.

## Task B14 — `supervisor.py` + test (plan decomposition + scatter-gather)

- [ ] Write failing test `tests/test_supervisor.py`:
  - `test_plan_proposed_event_fires_before_tool_calls`
  - `test_plan_approved_unblocks_scatter`
  - `test_scatter_dispatches_to_both_pools`: assert supervisor calls `persistence_pool.investigate` AND `exfil_pool.investigate` with identical `plan`.
  - `test_unattended_auto_approves_plan_in_0s`.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/supervisor.py`:
  - `async def propose_plan(case_handle, hermes) -> PlanProposed` — always leads with `hayabusa_scan` (demo beat, §10)
  - `async def await_plan_approval(case_id, unattended: bool) -> PlanApproved` — interactive awaits `POST /plan/approve`; unattended returns immediately
  - `async def scatter(plan, persistence_pool, exfil_pool) -> tuple[list[Finding], list[Finding]]` — `asyncio.gather`.
- [ ] Run tests. Expected: PASS.
- [ ] Commit: `feat(agent): supervisor.py plan decomposition + scatter-gather dispatch`.

## Task B15 — `graph.py` + test (StateGraph + SqliteSaver + kill/resume)

- [ ] Write failing tests in `tests/test_graph_smoke.py`:
  - `test_graph_compiles_with_sqlite_saver`
  - `test_edge_order`: assert edges `supervisor → plan_gate → scatter → gather → contradiction_detect → judge → verify → correlate → verdict`.
- [ ] Write failing test `tests/test_kill_resume.py::test_sigkill_midrun_resumes`:
  - start run; after first `ToolCallOutput` event, send `SIGKILL`; restart with `--resume`; final `RunVerdict` matches uninterrupted baseline.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/graph.py`:
  - `StateGraph(AgentState)` where `AgentState` tracks `plan`, `findings_a`, `findings_b`, `contradictions`, `verdict`
  - `SqliteSaver.from_conn_string("~/.findevil/cases/<id>/graph.db")` for checkpointing
  - `HUMAN_IN_THE_LOOP` flag threaded through plan_gate + contradiction_detect
  - resume logic: on startup, if checkpoint exists, resume from last node; never re-execute completed tool calls.
- [ ] Run tests. Expected: PASS.
- [ ] Commit: `feat(agent): graph.py StateGraph with SqliteSaver resume (kill/resume AC-07)`.

## Task B16 — `api.py` + test (FastAPI endpoints)

- [ ] Write failing tests in `tests/test_api.py`:
  - `test_post_cases_returns_case_id`
  - `test_get_stream_emits_sse_events` (captures first 3 `data:` lines, parses them as AgentEvent)
  - `test_post_plan_approve_unblocks`
  - `test_post_contradiction_resolve_routes_to_graph`
  - `test_get_verdict_404_until_complete`
  - `test_get_manifest_returns_jcs_json`.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/api.py`:
  - FastAPI app; endpoints per Spec #2 §4.2:
    - `POST /cases` → spawns graph; returns `{case_id}`
    - `GET /cases/{id}/stream` → SSE; `event: agent; data: <AgentEvent.model_dump_json()>\n\n`
    - `POST /cases/{id}/plan/approve`
    - `POST /cases/{id}/contradiction/resolve` with `{contradiction_id, decision: "trust_a"|"trust_b"|"flag"}`
    - `GET /cases/{id}/verdict`
    - `GET /cases/{id}/manifest`.
- [ ] Run tests. Expected: PASS.
- [ ] Commit: `feat(agent): FastAPI with 6 endpoints + SSE stream`.

## Task B17 — `cli.py` (find-evil CLI — serve/run/verify + unattended + exit codes)

- [ ] Write failing tests in `tests/test_cli.py`:
  - `test_run_unattended_emits_verdict_json_on_stdout`
  - `test_exit_code_0_for_confirmed_evil`
  - `test_exit_code_1_for_benign_inconclusive`
  - `test_exit_code_2_for_tool_timeout`
  - `test_exit_code_3_for_crypto_manifest_failure`
  - `test_verify_subcommand_runs_offline_steps_first`
  - `test_confirmed_tool_sha256_chip_format`: stderr line matches regex `^\[confirmed · [a-z_]+ · sha256:[0-9a-f]{8,} · [a-z_]+-\d+\]$`.
- [ ] Run. Expected: fails.
- [ ] Create `services/agent/src/findevil_agent/cli.py` (entry point `main()` via argparse):
  - subcommands: `serve`, `run --case X.e01 [--unattended] [--resume]`, `verify <manifest>`
  - `serve` spawns FastAPI (uvicorn) + launches Rust MCP + opens browser
  - `run` invokes graph directly (bypasses HTTP); prints verdict JSON to stdout in unattended mode
  - `verify` executes 4-step sequence from Spec #2 §7.2 (Merkle replay → sigstore → ots → receipt)
  - exit codes: 0 CONFIRMED/SUSPICIOUS, 1 BENIGN/INCONCLUSIVE, 2 tool/graph failure, 3 crypto failure
  - CLI formatter emits `[confirmed · tool · sha256 · tool_call_id]` lines verbatim for demo beat.
- [ ] Run tests. Expected: PASS.
- [ ] Commit: `feat(agent): find-evil CLI (serve/run/verify) with exit codes 0/1/2/3`.

---

# GROUP C — Next.js UI (Weeks 4–7)

## Task C1 — `apps/web/package.json` + Next.js 15 scaffold

- [ ] Run `pnpm create next-app@15.0.0 apps/web --ts --app --tailwind --no-eslint --no-src-dir --import-alias "@/*"`.
- [ ] Add `pnpm-workspace.yaml` at repo root listing `apps/web` + `apps/mcp-widgets/*`.
- [ ] Pin in `apps/web/package.json`:
  - `"next": "15.0.3"`, `"react": "19.0.0"`, `"tailwindcss": "4.0.0-beta.3"`
  - add `"shadcn": "2.1.0"` CLI devDependency
  - `"@ai-sdk/react": "1.0.3"`, `"ai": "4.0.3"`
  - `"@tanstack/react-table": "8.20.5"`
  - `"@observablehq/plot": "0.6.16"`
  - `"@duckdb/duckdb-wasm": "1.29.0"`.
- [ ] Run `pnpm --filter apps/web exec shadcn init -d` to initialize shadcn (Tailwind v4 config).
- [ ] Write failing test `apps/web/__tests__/versions.test.ts` asserting `package.json` dependency versions exactly match list above.
- [ ] Run `pnpm --filter apps/web test`. Expected: PASS.
- [ ] Run `pnpm --filter apps/web build`. Expected: `Generating static pages`.
- [ ] Commit: `chore(web): next 15 + tailwind v4 + shadcn + @ai-sdk/react scaffold`.

## Task C2 — `apps/web/lib/events.ts` (pydantic-to-typescript generated types)

- [ ] Add `services/agent/scripts/gen_events_ts.py` → runs `pydantic2ts --module findevil_agent.events --output ../../apps/web/lib/events.ts`.
- [ ] Write failing test `apps/web/__tests__/events_types.test.ts`:
  - imports `AgentEvent` from `@/lib/events`
  - asserts all 11 discriminated `event_type` literals present using `type` assertion helper.
- [ ] Run `uv run --directory services/agent python scripts/gen_events_ts.py`. Expected: generates `apps/web/lib/events.ts`.
- [ ] Run `pnpm --filter apps/web test`. Expected: PASS.
- [ ] Add npm script `"gen:events": "cd ../../services/agent && uv run python scripts/gen_events_ts.py"` to `apps/web/package.json`.
- [ ] Commit: `feat(web): generated events.ts from pydantic AgentEvent union`.

## Task C3 — `apps/web/app/page.tsx` (landing + case list + dropzone)

- [ ] Write failing test `apps/web/__tests__/landing.test.tsx` using `@testing-library/react`:
  - renders `<LandingPage />`
  - finds `heading` named `/find evil/i`, a dropzone with `role="region"` accepting `.e01`, and a `<CaseList>` section.
- [ ] Run. Expected: fails.
- [ ] Create `apps/web/app/page.tsx`: landing with shadcn `<Card>` hero, `<Dropzone>` (custom component using HTML5 drag/drop for `.e01`), `<CaseList>` fetching `GET /cases` via `@/lib/api`.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(web): landing page with dropzone + case list`.

## Task C4 — `apps/web/app/case/new/page.tsx` (upload flow)

- [ ] Write failing test `apps/web/__tests__/case_new.test.tsx`:
  - drops a fake `File` into the upload zone → fires `POST /cases` with `FormData`
  - on response `{case_id}` → router pushes to `/case/<id>`.
- [ ] Run. Expected: fails.
- [ ] Create `apps/web/app/case/new/page.tsx`:
  - wraps Dropzone in a form
  - progress bar during upload
  - on success `router.push(\`/case/\${case_id}\`)`.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(web): case/new upload flow with progress + redirect`.

## Task C5 — `apps/web/app/case/[id]/page.tsx` (split-pane)

- [ ] Write failing test `apps/web/__tests__/case_page.test.tsx`:
  - renders with mocked SSE feed
  - asserts `role="main"` split-pane contains `NarrativePane` on the left and `EvidenceCanvas` on the right
  - chrome strip (`ReadOnlyMcpBadge`, `HashChainBadge`, `NotifyStatus`, `KillResumeControl`) visible at top.
- [ ] Run. Expected: fails.
- [ ] Create `apps/web/app/case/[id]/page.tsx`:
  - uses `@ai-sdk/react` `useChat` against `/api/stream/:id`
  - left pane `<NarrativePane>` (flex-1, min-w-[420px])
  - right pane `<EvidenceCanvas>` (flex-1)
  - top chrome bar with 4 status components
  - `searchParams` read for deep-link (panel, event_id, tool_call_id).
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(web): case/[id] split-pane shell with SSE useChat binding`.

## Task C6 — `apps/web/components/narrative/NarrativePane.tsx`

- [ ] Write failing test `apps/web/__tests__/narrative_pane.test.tsx`:
  - feed synthetic AgentEvent sequence
  - asserts each `AgentMessage` rendered as a Dropzone-style card; `Finding` rendered with sha256 chip; auto-scrolls to bottom.
- [ ] Run. Expected: fails.
- [ ] Create `apps/web/components/narrative/NarrativePane.tsx`:
  - receives `events: AgentEvent[]` prop
  - renders `<StreamingSpanTree>` wrapped in scroll container
  - `PlanModePanel` shown when most-recent event_type is `PlanProposed`
  - `ContradictionSurface` overlay when active `ContradictionFound` with `resolution_required=true`.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(web): NarrativePane Dropzone-style reasoning flow`.

## Task C7 — `apps/web/components/narrative/PlanModePanel.tsx`

- [ ] Write failing test `apps/web/__tests__/plan_mode.test.tsx`:
  - renders with `PlanProposed` event: displays `plan_steps` as ordered list and an `Approve plan` button
  - clicking button triggers `POST /cases/{id}/plan/approve`.
- [ ] Run. Expected: fails.
- [ ] Create `apps/web/components/narrative/PlanModePanel.tsx`.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(web): PlanModePanel with approve button calling POST /plan/approve`.

## Task C8 — `apps/web/components/narrative/StreamingSpanTree.tsx` (chip format hard-coded)

- [ ] Write failing test `apps/web/__tests__/streaming_span_tree.test.tsx`:
  - given `Finding{tool_call_id:"evtx_query-007", confidence:"CONFIRMED"}` + matching `ToolCallOutput{output_hash:"d84f1a2b..."}`
  - renders chip with exact text `[confirmed · evtx_query · sha256:d84f1a2b · evtx_query-007]`
  - chip regex matches `^\[confirmed · [a-z_]+ · sha256:[0-9a-f]{8,} · [a-z_]+-\d+\]$`.
- [ ] Run. Expected: fails.
- [ ] Create `apps/web/components/narrative/StreamingSpanTree.tsx`:
  - renders tree of tool calls + agent messages (Langfuse-style nested spans)
  - each Finding gets chip built from exact format template (single string constant; no variations).
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(web): StreamingSpanTree with hard-coded [confirmed · tool · sha256] chip`.

## Task C9 — `apps/web/components/narrative/VerifierDiff.tsx` (fade-out animation)

- [ ] Write failing test `apps/web/__tests__/verifier_diff.test.tsx`:
  - `VerifierAction{action:"rejected", reason:"no tool_call_id"}`
  - asserts `data-fading="true"` attr after 100ms; tooltip has `reason` text on hover.
- [ ] Run. Expected: fails.
- [ ] Create `apps/web/components/narrative/VerifierDiff.tsx`:
  - uses CSS `transition: opacity 1.2s ease-out`
  - renders original finding struck through; revised below; tooltip on the strike.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(web): VerifierDiff fade-out with reason tooltip`.

## Task C10 — EvidenceCanvas + TimelineTab + HypothesisBoard + EventTable + ObservablesTab

- [ ] Write failing tests in `apps/web/__tests__/evidence_canvas.test.tsx`:
  - `test_tabs_present` — asserts tabs `Timeline`, `Hypotheses`, `Events`, `Observables`
  - `test_timeline_renders_plot` — stubbed Observable Plot renders `<svg>` with utc X axis
  - `test_hypothesis_board_mitre_grid` — `HypothesisUpdate{hypothesis:"persistence", confidence_delta:+0.2}` updates persistence bar to 0.7
  - `test_event_table_tanstack` — renders 100 rows in paginated TanStack table
  - `test_observables_tab_renders_iocs`.
- [ ] Run. Expected: fails.
- [ ] Create `apps/web/components/evidence/EvidenceCanvas.tsx` (shadcn Tabs host), plus `TimelineTab.tsx`, `HypothesisBoard.tsx`, `EventTable.tsx`, `ObservablesTab.tsx` per Spec #2 §4.3.
- [ ] Run tests. Expected: 5 PASSED.
- [ ] Commit: `feat(web): EvidenceCanvas with Timeline + Hypotheses + Events + Observables tabs`.

## Task C11 — `VerdictCard.tsx` + `ContradictionSurface.tsx`

- [ ] Write failing test `apps/web/__tests__/verdict_card.test.tsx`:
  - `RunVerdict{verdict:"CONFIRMED_EVIL", confidence_score:0.87}` → renders headline "CONFIRMED_EVIL", finding_count visible, expandable evidence list.
- [ ] Write failing test `apps/web/__tests__/contradiction_surface.test.tsx`:
  - renders `ContradictionFound` with `pool_a_claim`, `pool_b_claim`, conflicting `tool_call_ids`, and three buttons: `Trust A`, `Trust B`, `Flag for review`
  - each button triggers `POST /cases/{id}/contradiction/resolve` with the correct decision value.
- [ ] Run. Expected: fails.
- [ ] Create `apps/web/components/verdict/VerdictCard.tsx` and `apps/web/components/verdict/ContradictionSurface.tsx`.
- [ ] Run tests. Expected: PASS.
- [ ] Commit: `feat(web): VerdictCard + ContradictionSurface with Trust A/B/Flag buttons`.

## Task C12 — `components/chrome/*` (ReadOnlyMcpBadge, HashChainBadge, NotifyStatus, KillResumeControl)

- [ ] Write failing tests `apps/web/__tests__/chrome.test.tsx` covering each component:
  - `ReadOnlyMcpBadge` — green indicator with tooltip "Evidence vault is read-only"
  - `HashChainBadge` — click re-verifies Merkle root in a web worker; shows spinner then green/red
  - `NotifyStatus` — shows toast/Slack status when `RunVerdict` fires
  - `KillResumeControl` — Kill button sends `POST /cases/{id}/kill`; Resume button starts `--resume` flow.
- [ ] Run. Expected: fails.
- [ ] Create `apps/web/components/chrome/ReadOnlyMcpBadge.tsx`, `HashChainBadge.tsx`, `NotifyStatus.tsx`, `KillResumeControl.tsx`.
- [ ] Add web worker `apps/web/public/merkle-worker.js` that replays the root from `run.manifest.json`.
- [ ] Run tests. Expected: PASS.
- [ ] Commit: `feat(web): chrome badges + kill/resume control + worker Merkle verify`.

## Task C13 — `apps/web/app/case/[id]/report.html` (Vite single-file offline report)

- [ ] Write failing test `apps/web/__tests__/offline_report.test.ts`:
  - runs Vite library build on `apps/web/report/index.tsx` → asserts produced `report.html` is a single file (<2MB) with inlined JS + CSS, no external fetches.
- [ ] Run. Expected: fails.
- [ ] Create `apps/web/report/index.tsx` + `apps/web/vite.report.config.ts`:
  - library mode; `build.rollupOptions.output.inlineDynamicImports = true`
  - base64-inline CSS + fonts
  - takes `window.__MANIFEST__` injection at build time
  - renders VerdictCard + static timeline PNG + embedded manifest JSON.
- [ ] Add npm script `"build:report"` invoking `vite build -c vite.report.config.ts`.
- [ ] Run `pnpm --filter apps/web build:report`. Expected: produces `dist/report.html`.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(web): offline single-file report.html via Vite library build`.

---

# GROUP D — MCP Apps Widgets (Week 7)

## Task D1 — `apps/mcp-widgets/shared/bridge.ts` + `deeplink.ts` (Cursor fallback)

- [ ] Write failing test `apps/mcp-widgets/__tests__/bridge.test.ts`:
  - `getWidgetData({case_id:"x", widget:"timeline"})` with `_meta` intact → returns `_meta.ui.dataUrl` payload
  - without `_meta` → falls back to `GET /widgets/timeline/data?case_id=x`
  - `deepLink({case_id, panel:"timeline", event_id, tool_call_id})` → URL `http://localhost:8080/case/<id>?panel=timeline&event_id=<e>&tool_call_id=<t>`.
- [ ] Run. Expected: fails.
- [ ] Create `apps/mcp-widgets/shared/bridge.ts` + `deeplink.ts`:
  - `bridge.ts` wires MCP Apps `ui/notifications/tool-result`, `ui/open-link` calls; HTTP GET fallback for Cursor `_meta` strip
  - `deeplink.ts` builds the deep-link URL per Spec #2 §9.2.
- [ ] Run tests. Expected: PASS.
- [ ] Commit: `feat(widgets): shared bridge + deeplink with Cursor _meta fallback`.

## Task D2 — `apps/mcp-widgets/timeline/` (Observable Plot)

- [ ] Write failing test `apps/mcp-widgets/__tests__/timeline.test.ts`:
  - renders with `{events:[{ts, label, source:"evtx", severity:"high"}, ...]}`
  - asserts `<svg>` present, color-coded by severity, click fires `ui/open-link`.
- [ ] Run. Expected: fails.
- [ ] Create `apps/mcp-widgets/timeline/index.html` + `timeline.ts` + `manifest.json`:
  - Observable Plot timescale chart; linked-brush selection; UTC timestamps
  - click handler invokes `deepLink(...)` from `shared/deeplink.ts`.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(widgets): timeline widget with Observable Plot linked-brush`.

## Task D3 — `apps/mcp-widgets/ioc-heatmap/` (Canvas heatmap)

- [ ] Write failing test `apps/mcp-widgets/__tests__/ioc_heatmap.test.ts`:
  - renders `{iocs:[{rule,file,hit_count,mitre}, ...]}`
  - asserts `<canvas>` drawn, hover shows `tool_call_id` + SHA-256.
- [ ] Run. Expected: fails.
- [ ] Create `apps/mcp-widgets/ioc-heatmap/index.html` + `heatmap.ts` + `manifest.json`.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(widgets): ioc-heatmap canvas widget with hover tooltip`.

## Task D4 — `apps/mcp-widgets/evidence-diff/` (DOM diff viewer)

- [ ] Write failing test `apps/mcp-widgets/__tests__/evidence_diff.test.ts`:
  - renders `{original_finding, revised_finding, reason, tool_call_id}`
  - asserts side-by-side DOM diff with struck-through original; reason visible.
- [ ] Run. Expected: fails.
- [ ] Create `apps/mcp-widgets/evidence-diff/index.html` + `diff.ts` + `manifest.json`.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(widgets): evidence-diff DOM side-by-side viewer`.

---

# GROUP E — Integration + Verification (Weeks 6–7)

## Task E1 — `scripts/serve.sh` (FastAPI + Next.js + Rust MCP)

- [ ] Write failing test `scripts/tests/test_serve_sh.bats`:
  - runs `scripts/serve.sh --smoke` (new flag: start services, wait for health, exit 0)
  - asserts ports 8080 (FastAPI) and 3000 (Next.js dev) respond with `200` within 30s
  - asserts `findevil-mcp` subprocess child of parent Python agent
  - verifies graceful SIGTERM stops all three children.
- [ ] Run `bats scripts/tests/test_serve_sh.bats`. Expected: fails.
- [ ] Create `scripts/serve.sh`:
  - `set -euo pipefail`
  - starts `cargo run -p findevil-mcp --release` as background subprocess (`MCP_PID`)
  - starts `uv run --directory services/agent findevil-agent serve` (`API_PID`)
  - starts `pnpm --filter apps/web dev` (`WEB_PID`)
  - traps `SIGINT`/`SIGTERM` to kill all three
  - `--smoke` flag exits 0 once health endpoints respond
  - opens `http://localhost:8080` in default browser when not `--smoke`.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(scripts): serve.sh launches FastAPI + Next.js + Rust MCP with graceful shutdown`.

## Task E2 — `scripts/install.sh` with `resolve_credentials()` preflight (Amendment A1)

- [ ] Write failing test `scripts/tests/test_install_credentials.bats`:
  - `env -i bash scripts/install.sh --check-credentials` → exits 1 with ERROR message listing both `claude auth login` AND `ANTHROPIC_API_KEY`
  - with `ANTHROPIC_API_KEY=sk-ant-test` → exits 0 with message `Will use ANTHROPIC_API_KEY`
  - with mocked `claude` in PATH and `~/.claude/` dir → exits 0 with message `Detected Claude Code harness`.
- [ ] Run. Expected: fails.
- [ ] Create `scripts/install.sh` implementing Amendment A1 §3.2 block verbatim plus:
  - apt deps: `libewf-dev libyara-dev build-essential curl`
  - `cargo build -p findevil-mcp --release`
  - `uv sync --directory services/agent`
  - `pnpm install`
  - download YARA Forge Core tarball to `~/.findevil/yara/forge_core/`
  - write tool binary paths to `~/.findevil/config.toml`.
- [ ] Run test. Expected: 3 PASSED.
- [ ] Commit: `feat(scripts): install.sh with Option B credential preflight + SIFT deps`.

## Task E3 — `scripts/mcp-scanner-check.sh` (Cisco mcp-scanner against services/mcp)

- [ ] Write failing test `scripts/tests/test_mcp_scanner.bats`:
  - runs `scripts/mcp-scanner-check.sh` → expects exit 0 and output containing `execute_shell findings: 0`.
- [ ] Run. Expected: fails.
- [ ] Create `scripts/mcp-scanner-check.sh`:
  - clones `cisco-ai-defense/mcp-scanner` at pinned commit to `/tmp/mcp-scanner/`
  - runs `mcp-scanner scan --target services/mcp/ --output json > /tmp/scan.json`
  - parses JSON: exit 1 if any finding with `rule == "arbitrary_execution"` or `rule == "execute_shell"` or similar
  - prints `execute_shell findings: <n>`.
- [ ] Run test. Expected: PASS.
- [ ] Commit: `feat(scripts): mcp-scanner-check.sh enforces AC-13 zero arbitrary execution`.

## Task E4 — All 15 acceptance criteria as named tests

- [ ] Create `tests/acceptance/` dir at repo root with 15 named tests (one per AC), implemented in the appropriate stack:
  - `AC01_end_to_end_under_15min.py` (pytest) — `find-evil run --case fixtures/nist-hacking.E01 --unattended`; asserts exit ∈ {0,1} in ≤900s.
  - `AC02_correct_verdict_71pct_recall.py` — loads `goldens/nist-hacking-case.findings.json`; asserts ≥10/14 canonical findings present.
  - `AC03_no_uncited_findings.py` — every `Finding` in SSE stream has `tool_call_id` present in `audit.jsonl`.
  - `AC04_verify_offline_under_60s.py` — `find-evil verify run.manifest.json`; asserts exit 0 in ≤60s (Steps 1–2).
  - `AC05_ots_receipt_present.py` — asserts `run.manifest.ots` exists; `ots upgrade` succeeds after confirmation.
  - `AC06_merkle_inclusion_proofs.py` — random 3 leaves; `find-evil verify --check-leaf <i>` returns VALID.
  - `AC07_kill_resume.py` — already exists from Task B15; move/link here.
  - `AC08_contradiction_surface.py` — run NIST fixture; asserts ≥1 `ContradictionFound` event in `audit.jsonl`.
  - `AC09_plan_mode_gate.py` — non-unattended; asserts `PlanProposed` emitted before any `ToolCallStart`; `POST /plan/approve` unblocks.
  - `AC10_openclaw_parity.py` — `openclaw run` verdict == `find-evil run` verdict on same fixture.
  - `AC10a_credential_mode_parity.py` (from Amendment A1 §3.4) — same fixture under both `claude_code` and `api_key` modes → identical verdict.
  - `AC11_first_confirmed_ioc_15s.py` — asserts first `[confirmed · …]` line within 15s of `case_open` complete.
  - `AC12_read_only_enforcement.sh` (bats) — mount evidence ro; run full investigation; `inotifywait -r /evidence -e modify,create,delete` zero lines.
  - `AC13_no_execute_shell.sh` — re-invokes `scripts/mcp-scanner-check.sh`.
  - `AC14_widget_text_fallback.py` — invokes `evtx_query` via plain MCP client; asserts `content[0].text` non-empty.
  - `AC15_unattended_exit_codes.sh` — runs three fixtures and asserts exit codes 0, 1, 2 respectively.
- [ ] For each AC test: write it red first, implement any missing glue, then confirm green.
- [ ] Wire into GHA workflow `.github/workflows/l3-sift-goldens.yml` (add new jobs calling each AC test).
- [ ] Run entire suite locally: `uv run pytest tests/acceptance/` + `bats tests/acceptance/*.sh`. Expected: 15 PASSED.
- [ ] Commit: `test(acceptance): all 15 Spec #2 §12 acceptance criteria (incl. AC-10a credential parity)`.

---

## Post-Plan Verification

- [ ] Run `cargo test --workspace` → all Rust tests green.
- [ ] Run `uv run --directory services/agent pytest` → all Python tests green.
- [ ] Run `pnpm -r test` → all TypeScript tests green.
- [ ] Run `scripts/mcp-scanner-check.sh` → zero `execute_shell` findings.
- [ ] Run full acceptance suite against NIST Hacking Case fixture → 15/15 PASS.
- [ ] Tag release: `git tag product-v0.1.0-week7-complete`.
- [ ] Commit: `chore(release): product v0.1.0 week-7 complete — 15/15 acceptance criteria green`.
