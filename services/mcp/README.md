# findevil-mcp

Typed Rust MCP server for Find Evil! per Spec #2 §3 and §6.

**Authoritative design:** `docs/superpowers/specs/2026-04-25-the-product-design.md`.
**Invariants:** `CLAUDE.md` §"Non-negotiable invariants".

## Status

| Component | Status |
|---|---|
| Workspace + crate scaffold | ✅ |
| `case_open` tool | ✅ first implementation (Week 2 Task A3) |
| `mft_timeline`, `evtx_query`, other 9 tools | ⏳ swarm builds in Weeks 2-3 |
| rmcp 0.16 `ServerHandler` wire-up | ⏳ Week 2 Task A2 completion |
| M2 sigstore + rs_merkle integration | ⏳ Week 3 Task A11/A12 |

## Quick start

```sh
# From the repo root:
cargo build --workspace --release --locked
cargo test --workspace --locked
cargo clippy --workspace --all-targets -- -D warnings
```

## Tool surface (eventually 11 tools; currently 1)

Per Spec #2 §6:

| Tool | Module | Status |
|---|---|---|
| `case_open` | `tools/case_open.rs` | ✅ |
| `mft_timeline` | `tools/mft_timeline.rs` | ⏳ |
| `evtx_query` | `tools/evtx_query.rs` | ⏳ |
| `hayabusa_scan` | `tools/hayabusa_scan.rs` | ⏳ |
| `vol_pslist` | `tools/vol_pslist.rs` | ⏳ |
| `vol_malfind` | `tools/vol_malfind.rs` | ⏳ |
| `yara_scan` | `tools/yara_scan.rs` | ⏳ |
| `usnjrnl_query` | `tools/usnjrnl_query.rs` | ⏳ |
| `registry_query` | `tools/registry_query.rs` | ⏳ |
| `prefetch_parse` | `tools/prefetch_parse.rs` | ⏳ |
| `vel_collect` | `tools/vel_collect.rs` | ⏳ |

## Structure for swarm-written tools

Every tool module must:

- Export an `Input` struct that `#[derive(serde::Deserialize)]` + `#[serde(deny_unknown_fields)]`.
- Export a typed output that `#[derive(serde::Serialize)]`.
- Export a `<Name>Error` enum with `#[derive(thiserror::Error)]`.
- Expose a pure entrypoint function `pub fn <tool_name>(input: &Input) -> Result<Output, Error>` (or `async fn` when the tool is I/O-bound).
- Never call `std::process::Command` without also declaring the tool invocation in the module docstring (AGPL/GPL binaries run via subprocess only; see `CLAUDE.md`).
- Ship integration tests under `services/mcp/tests/` that use `tempfile` + `FINDEVIL_HOME` override so they never stomp on the developer's real case store.

## Pinned dependencies (Spec #2 §16)

- `sha2 = "0.10"`
- `uuid = "1"` + `v4,serde`
- `serde = "1"` + `derive`
- `thiserror = "1"`
- `tokio = "1"` (activated when rmcp server lands)
- `chrono = "0.4"` + `serde`
- `tracing` + `tracing-subscriber`

Development-only: `tempfile`, `hex`.

## Tests

```sh
# Fast unit tests (single module):
cargo test -p findevil-mcp --lib

# Integration smoke across all tools:
cargo test -p findevil-mcp --test tool_smoke

# Everything:
cargo test --workspace --locked
```

## Notes for swarm workers

- Do **not** add a dependency without listing it in Spec #2 §16 first.
- Do **not** link AGPL/GPL code (Hayabusa, Chainsaw, Volatility3, Velociraptor, YARA). Subprocess only.
- Every tool's `Input` must `#[serde(deny_unknown_fields)]` to catch schema drift between the Python agent and this crate.
- Every error variant must be safe to surface back to the agent — no filesystem absolute paths that leak private state (case dirs under `FINDEVIL_HOME` are fine; arbitrary agent `cwd` paths are not).
