"""Application coordination over Orc Werk core and ports (`TASK-M0-005`).

`orc_werk.app` imports `orc_werk.core` and `orc_werk.ports` only -- never
`orc_werk.adapters` or `orc_werk.cli` (`ARCH-REPOSITORY-STRUCTURE`).
"""

from orc_werk.app.orchestrator import (
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_WORK_ID,
    Orchestrator,
    RunConfig,
    default_single_work_plan,
)

__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_WORK_ID",
    "Orchestrator",
    "RunConfig",
    "default_single_work_plan",
]
