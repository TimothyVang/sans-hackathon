"""Python worker — builds + tests Python PRs (``services/agent/``, ``services/swarm/``).

Thin subclass of ``BaseWorker`` with Python-specific guidance and
``uv run pytest`` as the L1 default.
"""

from __future__ import annotations

from typing import ClassVar

from findevil_swarm.workers.base_worker import BaseWorker


class PythonWorker(BaseWorker):
    language: ClassVar[str] = "python"
    default_l1_command: ClassVar[str] = "uv run pytest -xvs --cov"

    system_prompt_fragment: ClassVar[str] = (
        "Python-specific guidance:\n"
        "- Target Python 3.11. Use ``uv`` for env + lockfile (never pip).\n"
        "- Use Pydantic v2 for all schema types.\n"
        "- Use ``ruff check`` + ``ruff format --check`` — both must be clean.\n"
        "- LangGraph >=1.0 in pinned range. Use PostgresSaver for the swarm, "
        "SqliteSaver for the Product — never mix.\n"
        "- Use ``structlog`` for structured logging; never ``print``.\n"
        "- Test-driven: write the failing test first, confirm RED, implement, "
        "confirm GREEN, commit. One task per commit.\n"
        "- ``from __future__ import annotations`` at the top of every module.\n"
    )


__all__ = ["PythonWorker"]
