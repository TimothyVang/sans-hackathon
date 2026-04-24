"""Claude-CLI-invoking workers (Option B).

Each worker owns one language lane — ``rust_worker``, ``python_worker``,
``ts_worker``. All three subclass ``BaseWorker`` and differ only in
system-prompt fragments and L1 command defaults.
"""

from findevil_swarm.workers.base_worker import (
    BaseWorker,
    WorkerInput,
    WorkerResult,
)
from findevil_swarm.workers.python_worker import PythonWorker
from findevil_swarm.workers.rust_worker import RustWorker
from findevil_swarm.workers.ts_worker import TypeScriptWorker

__all__ = [
    "BaseWorker",
    "PythonWorker",
    "RustWorker",
    "TypeScriptWorker",
    "WorkerInput",
    "WorkerResult",
]
