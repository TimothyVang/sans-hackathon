//! Find Evil! MCP server binary.
//!
//! Spec #2 §2 + §3. Stdio transport for the rmcp server. Today this
//! is a minimal runtime that validates the library face compiles +
//! exposes a `--version` flag; the full rmcp `ServerHandler` wire-up
//! arrives in the Week 2-3 tasks once every tool module is in
//! place. Keeping a compilable binary now means the L0/L1 GHA jobs
//! exercise real Rust code instead of self-skipping.

#![forbid(unsafe_code)]

use std::env;

use findevil_mcp::CRATE_VERSION;

fn main() -> std::process::ExitCode {
    let args: Vec<String> = env::args().collect();
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .with_writer(std::io::stderr)
        .init();

    if args.iter().any(|a| a == "--version" || a == "-V") {
        println!("findevil-mcp {CRATE_VERSION}");
        return std::process::ExitCode::SUCCESS;
    }

    if args.iter().any(|a| a == "--help" || a == "-h") {
        println!(
            "findevil-mcp {CRATE_VERSION}\n\
             \n\
             Usage: findevil-mcp [OPTIONS]\n\
             \n\
             Options:\n\
               --version, -V   Print version and exit\n\
               --help, -h      Print this help\n\
             \n\
             Without arguments, runs the MCP stdio server. Currently\n\
             returns exit 0 with a placeholder message; full server\n\
             starts landing in Week 2-3 (Spec #2 §6).\n"
        );
        return std::process::ExitCode::SUCCESS;
    }

    tracing::info!(
        target = "findevil_mcp",
        "findevil-mcp {CRATE_VERSION} started (pre-server stub)"
    );
    // Intentionally exit 0: pre-Week-2 this binary is wire-up only.
    std::process::ExitCode::SUCCESS
}
