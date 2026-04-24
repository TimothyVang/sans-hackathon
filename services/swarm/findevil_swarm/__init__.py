"""Find Evil! build swarm — Option B (Claude Code subscription mode).

See ``docs/superpowers/specs/2026-04-24-autonomous-build-swarm-design.md``
for the full design and ``docs/superpowers/specs/2026-04-23-amendment-option-b-claude-code-mode.md``
for the Option B override (no LiteLLM, no API key, `claude` CLI only).
"""

from findevil_swarm.state import (
    CriticVerdict,
    NightlyReport,
    PRSpec,
    SwarmState,
)

__version__ = "0.1.0"

__all__ = [
    "CriticVerdict",
    "NightlyReport",
    "PRSpec",
    "SwarmState",
    "__version__",
]
