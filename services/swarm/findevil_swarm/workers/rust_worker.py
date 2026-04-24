"""Rust worker — builds + tests Rust PRs (``services/mcp/`` code).

Thin subclass of ``BaseWorker`` with Rust-specific guidance in the
system prompt and ``cargo test`` as the L1 default.
"""

from __future__ import annotations

from typing import ClassVar

from findevil_swarm.workers.base_worker import BaseWorker


class RustWorker(BaseWorker):
    language: ClassVar[str] = "rust"
    default_l1_command: ClassVar[str] = "cargo test --workspace --locked"

    system_prompt_fragment: ClassVar[str] = (
        "Rust-specific guidance:\n"
        "- Target crate is rmcp 0.16.x; pin with = in Cargo.toml.\n"
        "- Use ``evtx = \"=0.11.2\"`` for in-process EVTX parsing.\n"
        "- Use ``rs_merkle = \"=1.4.0\"`` for the M2 append-only tree.\n"
        "- Use ``duckdb = \"=0.10\"`` for the L1 case DB.\n"
        "- AGPL/GPL tools (Hayabusa, Chainsaw, Volatility3, Velociraptor, YARA) "
        "must only be invoked as subprocesses — never linked. Calling them via "
        "``std::process::Command`` is the contract.\n"
        "- Run ``cargo test --workspace --locked`` before committing. "
        "``cargo clippy --deny warnings`` must be clean.\n"
        "- No new dependency without a spec amendment. Prefer stdlib.\n"
    )


__all__ = ["RustWorker"]
