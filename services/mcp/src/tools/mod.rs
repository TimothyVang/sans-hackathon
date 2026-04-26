//! Typed DFIR tool surface.
//!
//! Each submodule is one MCP tool. Every module exports:
//!   * an `Input` struct (the Pydantic-equivalent JSON shape the
//!     agent sends),
//!   * an output type that implements [`serde::Serialize`],
//!   * an error type `<Name>Error` with `thiserror::Error`,
//!   * an async (or sync) entrypoint function callable from the
//!     rmcp `ServerHandler` wire-up in `lib.rs` / `main.rs`.
//!
//! Constraints from Spec #2 §3:
//!   * No tool exposes raw shell exec.
//!   * Every tool result is reproducible from the input + on-disk
//!     evidence alone (no network side-effects).
//!   * Every tool is testable in isolation via integration tests
//!     under `services/mcp/tests/`.

pub mod case_open;
pub mod evtx_query;
pub mod hayabusa_scan;
pub mod mft_timeline;
pub mod prefetch_parse;
pub mod registry_query;
pub mod usnjrnl_query;
pub mod vel_collect;
pub mod vol_malfind;
pub mod vol_pslist;
pub mod yara_scan;

/// Convenience re-exports.
pub use case_open::{case_open, CaseHandle, CaseOpenError, CaseOpenInput};
pub use evtx_query::{
    evtx_query, path_looks_like_evtx, EvtxError, EvtxQueryInput, EvtxQueryOutput, EvtxRow,
};
pub use hayabusa_scan::{
    hayabusa_scan, HayabusaAlert, HayabusaError, HayabusaInput, HayabusaOutput,
};
pub use mft_timeline::{
    mft_timeline, path_looks_like_mft, MftEntryRow, MftError, MftInput, MftOutput,
};
pub use prefetch_parse::{
    path_looks_like_prefetch, prefetch_parse, PrefetchError, PrefetchInput, PrefetchOutput,
};
pub use registry_query::{
    path_looks_like_hive, registry_query, RegistryEntry, RegistryError, RegistryInput,
    RegistryOutput, RegistryValue,
};
pub use usnjrnl_query::{
    path_looks_like_usnjrnl, usnjrnl_query, UsnJrnlEntry, UsnJrnlError, UsnJrnlInput, UsnJrnlOutput,
};
pub use vel_collect::{vel_collect, VelCollectError, VelCollectInput, VelCollectOutput, VelRow};
pub use vol_malfind::{
    vol_malfind, VolInjection, VolMalfindError, VolMalfindInput, VolMalfindOutput,
};
pub use vol_pslist::{
    path_looks_like_memory_image, vol_pslist, VolError, VolProcess, VolPslistInput, VolPslistOutput,
};
pub use yara_scan::{
    path_looks_like_yara_rules, yara_scan, YaraError, YaraInput, YaraMatch, YaraOutput,
    YaraPatternMatch,
};
