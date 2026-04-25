//! Find Evil! typed MCP server — library face.
//!
//! Spec #2 §3 + §6. The crate's binary ([`bin/findevil-mcp`]) wires
//! these modules into an rmcp `ServerHandler` over stdio; the
//! library face lets integration tests + the Python agent's
//! in-process harness exercise tool modules directly without a
//! full subprocess round-trip.
//!
//! Invariants (see `CLAUDE.md`):
//! - No `execute_shell` tool, ever.
//! - Every tool response carries `tool_call_id` (UUID4) + SHA-256
//!   of the raw output bytes.
//! - AGPL/GPL backing tools (Hayabusa, Chainsaw, Volatility3,
//!   Velociraptor, YARA) are invoked via `std::process::Command`,
//!   never linked.

#![forbid(unsafe_code)]

pub mod crypto;
pub mod server;
pub mod tools;

/// Crate version baked in at compile time — surfaced in the MCP
/// server's capability handshake and in audit logs.
pub const CRATE_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Re-exports for test + binary convenience.
pub use crate::crypto::merkle::{verify_inclusion_proof, InclusionProof, MerkleError, MerkleTree};
pub use crate::tools::case_open::{case_open, CaseHandle, CaseOpenError, CaseOpenInput};
pub use crate::tools::evtx_query::{
    evtx_query, path_looks_like_evtx, EvtxError, EvtxQueryInput, EvtxQueryOutput, EvtxRow,
};
pub use crate::tools::mft_timeline::{
    mft_timeline, path_looks_like_mft, MftEntryRow, MftError, MftInput, MftOutput,
};
pub use crate::tools::prefetch_parse::{
    path_looks_like_prefetch, prefetch_parse, PrefetchError, PrefetchInput, PrefetchOutput,
};
pub use crate::tools::registry_query::{
    path_looks_like_hive, registry_query, RegistryEntry, RegistryError, RegistryInput,
    RegistryOutput, RegistryValue,
};
pub use crate::tools::usnjrnl_query::{
    path_looks_like_usnjrnl, usnjrnl_query, UsnJrnlEntry, UsnJrnlError, UsnJrnlInput, UsnJrnlOutput,
};
pub use crate::tools::yara_scan::{
    path_looks_like_yara_rules, yara_scan, YaraError, YaraInput, YaraMatch, YaraOutput,
    YaraPatternMatch,
};
