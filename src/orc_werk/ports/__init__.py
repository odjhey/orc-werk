"""Canonical Orc Werk port interfaces (`PORTS-INDEX`).

Language-level interfaces mirroring the five mandatory v0 port documents
(`docs/contracts/ports/`): `WorkGraphPort`, `ExecutionPort`, `CandidatePort`,
`AssurancePort`, `JournalPort`. Depends only on `orc_werk.core` canonical
types and the standard library -- no provider/adapter imports
(`ARCH-REPOSITORY-STRUCTURE`: `ports -> core` only).
"""

from __future__ import annotations

from orc_werk.ports.assurance import AssuranceObservation, AssurancePort
from orc_werk.ports.base import (
    LIFECYCLE_STATE_REQUESTED,
    LIFECYCLE_STATE_RUNNING,
    LIFECYCLE_STATE_SETTLED,
    LIFECYCLE_STATES,
    Port,
)
from orc_werk.ports.candidate import (
    CANDIDATE_COMPARISON_DIFFERENT,
    CANDIDATE_COMPARISON_SAME,
    CANDIDATE_COMPARISONS,
    CandidatePort,
)
from orc_werk.ports.capabilities import (
    ALL_CAPABILITY_IDS,
    ASSURANCE_CAPABILITIES,
    CANDIDATE_CAPABILITIES,
    CAP_ASSURE_CANDIDATE_BOUND,
    CAP_ASSURE_MAY_MUTATE_CANDIDATE,
    CAP_ASSURE_STRUCTURED_FINDINGS,
    CAP_ASSURE_STRUCTURED_VERDICT,
    CAP_EXEC_CANCEL,
    CAP_EXEC_RESUME_BEST_EFFORT,
    CAP_EXEC_RESUME_EXACT,
    CAP_EXEC_SEND,
    CAP_EXEC_STRUCTURED_LIFECYCLE,
    CAP_WORK_ATOMIC_CLAIM,
    CAP_WORK_EXTERNAL_GATES,
    CAP_WORK_GRAPH_PATCH,
    EXECUTION_CAPABILITIES,
    JOURNAL_CAPABILITIES,
    WORK_GRAPH_CAPABILITIES,
    validate_capabilities,
)
from orc_werk.ports.execution import ExecutionObservation, ExecutionPort
from orc_werk.ports.journal import JournalPort
from orc_werk.ports.work_graph import (
    DEPENDENCY_CONDITION_ACCEPTED,
    VALID_DEPENDENCY_CONDITIONS,
    WorkGraphPort,
    validate_plan,
)

__all__ = [
    "ALL_CAPABILITY_IDS",
    "ASSURANCE_CAPABILITIES",
    "AssuranceObservation",
    "AssurancePort",
    "CANDIDATE_CAPABILITIES",
    "CANDIDATE_COMPARISON_DIFFERENT",
    "CANDIDATE_COMPARISON_SAME",
    "CANDIDATE_COMPARISONS",
    "CAP_ASSURE_CANDIDATE_BOUND",
    "CAP_ASSURE_MAY_MUTATE_CANDIDATE",
    "CAP_ASSURE_STRUCTURED_FINDINGS",
    "CAP_ASSURE_STRUCTURED_VERDICT",
    "CAP_EXEC_CANCEL",
    "CAP_EXEC_RESUME_BEST_EFFORT",
    "CAP_EXEC_RESUME_EXACT",
    "CAP_EXEC_SEND",
    "CAP_EXEC_STRUCTURED_LIFECYCLE",
    "CAP_WORK_ATOMIC_CLAIM",
    "CAP_WORK_EXTERNAL_GATES",
    "CAP_WORK_GRAPH_PATCH",
    "CandidatePort",
    "DEPENDENCY_CONDITION_ACCEPTED",
    "EXECUTION_CAPABILITIES",
    "ExecutionObservation",
    "ExecutionPort",
    "JOURNAL_CAPABILITIES",
    "JournalPort",
    "LIFECYCLE_STATE_REQUESTED",
    "LIFECYCLE_STATE_RUNNING",
    "LIFECYCLE_STATE_SETTLED",
    "LIFECYCLE_STATES",
    "Port",
    "VALID_DEPENDENCY_CONDITIONS",
    "WORK_GRAPH_CAPABILITIES",
    "WorkGraphPort",
    "validate_capabilities",
    "validate_plan",
]
