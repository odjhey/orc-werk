"""Capability identifiers (`CONTRACT-CAPABILITIES`) and the shared
advertisement/negotiation surface (`INV-013`, `SCN-006`).

Capabilities describe semantic guarantees a provider adapter can promise --
never marketing features. Every mandatory v0 port exposes
`capabilities()` (see `orc_werk.ports.base.Port`) so callers/policy can
query what one adapter instance guarantees before invoking a
capability-gated operation, and so an adapter that cannot guarantee a
stronger semantic fails explicitly (`ERR-UNSUPPORTED-CAPABILITY`) instead
of silently downgrading it (`INV-013`).
"""

from __future__ import annotations

from typing import Iterable

# Work graph capabilities.
CAP_WORK_ATOMIC_CLAIM = "CAP-WORK-ATOMIC-CLAIM"
CAP_WORK_GRAPH_PATCH = "CAP-WORK-GRAPH-PATCH"
CAP_WORK_EXTERNAL_GATES = "CAP-WORK-EXTERNAL-GATES"

WORK_GRAPH_CAPABILITIES = frozenset(
    {CAP_WORK_ATOMIC_CLAIM, CAP_WORK_GRAPH_PATCH, CAP_WORK_EXTERNAL_GATES}
)

# Execution capabilities.
CAP_EXEC_SEND = "CAP-EXEC-SEND"
CAP_EXEC_CANCEL = "CAP-EXEC-CANCEL"
CAP_EXEC_RESUME_BEST_EFFORT = "CAP-EXEC-RESUME-BEST-EFFORT"
CAP_EXEC_RESUME_EXACT = "CAP-EXEC-RESUME-EXACT"
CAP_EXEC_STRUCTURED_LIFECYCLE = "CAP-EXEC-STRUCTURED-LIFECYCLE"

EXECUTION_CAPABILITIES = frozenset(
    {
        CAP_EXEC_SEND,
        CAP_EXEC_CANCEL,
        CAP_EXEC_RESUME_BEST_EFFORT,
        CAP_EXEC_RESUME_EXACT,
        CAP_EXEC_STRUCTURED_LIFECYCLE,
    }
)

# Assurance capabilities.
CAP_ASSURE_CANDIDATE_BOUND = "CAP-ASSURE-CANDIDATE-BOUND"
CAP_ASSURE_STRUCTURED_VERDICT = "CAP-ASSURE-STRUCTURED-VERDICT"
CAP_ASSURE_STRUCTURED_FINDINGS = "CAP-ASSURE-STRUCTURED-FINDINGS"
CAP_ASSURE_MAY_MUTATE_CANDIDATE = "CAP-ASSURE-MAY-MUTATE-CANDIDATE"

ASSURANCE_CAPABILITIES = frozenset(
    {
        CAP_ASSURE_CANDIDATE_BOUND,
        CAP_ASSURE_STRUCTURED_VERDICT,
        CAP_ASSURE_STRUCTURED_FINDINGS,
        CAP_ASSURE_MAY_MUTATE_CANDIDATE,
    }
)

# CONTRACT-CAPABILITIES defines no capability identifiers for CandidatePort
# or JournalPort as of this writing; both still implement the shared
# `capabilities()` surface (typically returning an empty set) so the
# advertisement mechanism is uniform across all five mandatory v0 ports.
CANDIDATE_CAPABILITIES: frozenset[str] = frozenset()
JOURNAL_CAPABILITIES: frozenset[str] = frozenset()

ALL_CAPABILITY_IDS = (
    WORK_GRAPH_CAPABILITIES
    | EXECUTION_CAPABILITIES
    | ASSURANCE_CAPABILITIES
    | CANDIDATE_CAPABILITIES
    | JOURNAL_CAPABILITIES
)


def validate_capabilities(capabilities: Iterable[str]) -> frozenset[str]:
    """Normalize and validate an adapter's advertised capability set.

    Raises `ValueError` for any identifier outside the `CONTRACT-CAPABILITIES`
    registry (mirrors the unknown-id guard `orc_werk.core.errors.canonical_error`
    already applies to `CONTRACT-ERRORS`) -- an adapter may advertise a
    subset of known capabilities, never an invented one.
    """
    caps = frozenset(capabilities)
    unknown = caps - ALL_CAPABILITY_IDS
    if unknown:
        raise ValueError(f"unknown capability id(s): {sorted(unknown)}")
    return caps
