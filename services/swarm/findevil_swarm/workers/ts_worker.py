"""TypeScript worker — builds + tests TS/TSX PRs (``apps/web/``, ``apps/mcp-widgets/``).

Thin subclass of ``BaseWorker`` with TS-specific guidance and
``pnpm -r test`` as the L1 default.
"""

from __future__ import annotations

from typing import ClassVar

from findevil_swarm.workers.base_worker import BaseWorker


class TypeScriptWorker(BaseWorker):
    language: ClassVar[str] = "typescript"
    default_l1_command: ClassVar[str] = "pnpm -r test"

    system_prompt_fragment: ClassVar[str] = (
        "TypeScript-specific guidance:\n"
        "- Target Node 20 + pnpm 9.12.0; use ``pnpm install --frozen-lockfile``.\n"
        "- Next.js 15 + shadcn/ui + Tailwind v4 stack for the Product UI.\n"
        "- ``tsc --noEmit`` must pass; ``pnpm -r lint`` must pass.\n"
        "- Use ``@ai-sdk/react`` ``useChat`` for SSE consumption from the "
        "Python FastAPI backend.\n"
        "- MCP App widgets (``apps/mcp-widgets/``) are static HTML+JS bundles — "
        "no Next.js dependency. They communicate with the Rust MCP server via "
        "the ``ui/notifications/tool-result`` MCP Apps message (SEP-1865).\n"
        "- Cursor 2.6 strips ``_meta`` from ``ui/notifications/tool-result`` — "
        "widgets must have a HTTP-GET fallback (``apps/mcp-widgets/shared/bridge.ts``).\n"
        "- DFIR vocabulary: Case, Observable, Task, Finding, Verdict, Confidence. "
        "Never: session, run, artifact, step, result, hit, conclusion, score.\n"
    )


__all__ = ["TypeScriptWorker"]
