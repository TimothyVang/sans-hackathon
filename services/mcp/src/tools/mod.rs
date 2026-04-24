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

/// Convenience re-exports.
pub use case_open::{CaseHandle, CaseOpenError, CaseOpenInput, case_open};
