#!/usr/bin/env bash
set -euo pipefail
[ -f "$HOME/.cargo/env" ] && source "$HOME/.cargo/env"
export PATH="$HOME/.cargo/bin:$PATH"
exec cargo run --release -p findevil-mcp --quiet
