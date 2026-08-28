"""Per-Work derived state (`STATE-DELIVERY`).

`WorkProjection` is the reducer's pure derivation from an ordered Fact
sequence -- mechanics only (validates/derives, does not choose, per
TASK-M0-001). State identifiers are plain strings (not `enum.Enum`
instances) so projections stay portable/JSON-compatible by construction
(ARCH-REPOSITORY-STRUCTURE); `to_dict()` is the canonical serializable
shape, the dataclass itself is a reference-implementation convenience.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Optional

# Canonical v0 states (STATE-DELIVERY).
STATE_READY = "READY"
STATE_EXECUTING = "EXECUTING"
STATE_ASSURING = "ASSURING"
STATE_ACCEPTED = "ACCEPTED"
STATE_BLOCKED = "BLOCKED"

# Reserved: declared, not reachable by v0/M0 reducer/policy.
STATE_FAILED = "FAILED"
STATE_CANCELLED = "CANCELLED"

ALL_STATES = frozenset(
    {STATE_READY, STATE_EXECUTING, STATE_ASSURING, STATE_ACCEPTED, STATE_BLOCKED, STATE_FAILED, STATE_CANCELLED}
)
TERMINAL_STATES = frozenset({STATE_ACCEPTED, STATE_BLOCKED})
# Reachable by v0/M0 reducer/policy; FAILED/CANCELLED excluded (STATE-DELIVERY).
V0_REACHABLE_STATES = frozenset({STATE_READY, STATE_EXECUTING, STATE_ASSURING, STATE_ACCEPTED, STATE_BLOCKED})


@dataclass(frozen=True)
class WorkProjection:
    """Derived per-Work state after folding an ordered Fact sequence."""

    work_id: str
    delivery_run_id: str
    state: str = STATE_READY

    ready_confirmed: bool = False

    # INV-018: attempt_number is cumulative and equals the count of
    # execution-start facts observed for this Work's lineage.
    attempt_number: int = 0
    executions: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    current_execution_id: Optional[str] = None

    candidates: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    current_candidate_id: Optional[str] = None

    assurances: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    current_assurance_id: Optional[str] = None
    assurance_started_for_current: bool = False

    claim_ref: Optional[str] = None

    blocked_reason: Optional[str] = None
    blocked_confirmed: bool = False
    completed_confirmed: bool = False

    # Portable fact dicts that justify the currently-pending policy decision
    # (INV-011/INV-012 basis).
    trigger_facts: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def current_candidate_fingerprint(self) -> Optional[str]:
        if self.current_candidate_id is None:
            return None
        return self.candidates[self.current_candidate_id]["fingerprint"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_id": self.work_id,
            "delivery_run_id": self.delivery_run_id,
            "state": self.state,
            "ready_confirmed": self.ready_confirmed,
            "attempt_number": self.attempt_number,
            "executions": [dict(item) for item in self.executions],
            "current_execution_id": self.current_execution_id,
            "candidates": {key: dict(val) for key, val in self.candidates.items()},
            "current_candidate_id": self.current_candidate_id,
            "assurances": [dict(item) for item in self.assurances],
            "current_assurance_id": self.current_assurance_id,
            "assurance_started_for_current": self.assurance_started_for_current,
            "claim_ref": self.claim_ref,
            "blocked_reason": self.blocked_reason,
            "blocked_confirmed": self.blocked_confirmed,
            "completed_confirmed": self.completed_confirmed,
        }


def replace_projection(projection: WorkProjection, **changes: Any) -> WorkProjection:
    return replace(projection, **changes)


@dataclass(frozen=True)
class DeliveryProjection:
    """Delivery-run-scoped projection: intent + all per-Work projections."""

    delivery_run_id: str
    intent_id: Optional[str] = None
    works: Mapping[str, WorkProjection] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "delivery_run_id": self.delivery_run_id,
            "intent_id": self.intent_id,
            "works": {work_id: proj.to_dict() for work_id, proj in self.works.items()},
        }
