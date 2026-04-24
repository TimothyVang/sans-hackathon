"""Find Evil! agent runtime — LangGraph ACH graph + FastAPI SSE.

See:
  - ``docs/superpowers/specs/2026-04-25-the-product-design.md`` — Spec #2
  - ``docs/superpowers/specs/2026-04-23-amendment-option-b-claude-code-mode.md``
    — credential modes (CLAUDE_CODE_OAUTH_TOKEN, interactive session,
    ANTHROPIC_API_KEY)
"""

from findevil_agent.config import CredentialMode, resolve_credentials
from findevil_agent.events import (
    AgentEvent,
    AgentMessage,
    ChainUpdate,
    ContradictionFound,
    Finding,
    HypothesisUpdate,
    PlanApproved,
    PlanProposed,
    RunVerdict,
    ToolCallOutput,
    ToolCallStart,
    VerifierAction,
)

__version__ = "0.1.0"

__all__ = [
    "AgentEvent",
    "AgentMessage",
    "ChainUpdate",
    "ContradictionFound",
    "CredentialMode",
    "Finding",
    "HypothesisUpdate",
    "PlanApproved",
    "PlanProposed",
    "RunVerdict",
    "ToolCallOutput",
    "ToolCallStart",
    "VerifierAction",
    "__version__",
    "resolve_credentials",
]
