"""Canonical Facts (PROTOCOL-FACTS).

A Fact is an immutable canonical observation. IDs and required data fields
mirror `docs/protocol/facts.md` verbatim. `FACT-WORK-CANCELLED` is declared
(reserved) but MUST NOT be produced by v0/M0 reducer/policy code
(STATE-DELIVERY "Reserved states and decisions").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from orc_werk.core.portable import is_portable, to_portable

FACT_INTENT_SUBMITTED = "FACT-INTENT-SUBMITTED"
FACT_WORK_CREATED = "FACT-WORK-CREATED"
FACT_WORK_READY = "FACT-WORK-READY"
FACT_WORK_CLAIMED = "FACT-WORK-CLAIMED"
FACT_EXEC_STARTED = "FACT-EXEC-STARTED"
FACT_EXEC_SETTLED = "FACT-EXEC-SETTLED"
FACT_CANDIDATE_OBSERVED = "FACT-CANDIDATE-OBSERVED"
FACT_ASSURE_STARTED = "FACT-ASSURE-STARTED"
FACT_ASSURE_SETTLED = "FACT-ASSURE-SETTLED"
FACT_WORK_COMPLETED = "FACT-WORK-COMPLETED"
FACT_WORK_BLOCKED = "FACT-WORK-BLOCKED"
# TASK-M3B-001 (issues #76/#95): pairs with DEC-ABANDON-ATTEMPT
# (STATE-DELIVERY mechanical fact sequencing item 9). Reachable in v0/M0.
FACT_ATTEMPT_ABANDONED = "FACT-ATTEMPT-ABANDONED"

# Reserved: declared per PROTOCOL-FACTS, unreachable in v0/M0 (STATE-DELIVERY).
FACT_WORK_CANCELLED = "FACT-WORK-CANCELLED"

# Required data fields per docs/protocol/facts.md, verbatim.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    FACT_INTENT_SUBMITTED: ("intent_id", "text"),
    FACT_WORK_CREATED: ("work_id", "delivery_run_id"),
    FACT_WORK_READY: ("work_id",),
    FACT_WORK_CLAIMED: ("work_id", "claim_ref"),
    FACT_EXEC_STARTED: ("execution_id", "work_id"),
    FACT_EXEC_SETTLED: ("execution_id", "work_id", "outcome"),
    FACT_CANDIDATE_OBSERVED: ("candidate_id", "fingerprint", "execution_id"),
    FACT_ASSURE_STARTED: ("assurance_id", "candidate_id"),
    FACT_ASSURE_SETTLED: ("assurance_id", "candidate_fingerprint", "verdict"),
    FACT_WORK_COMPLETED: ("work_id",),
    FACT_WORK_BLOCKED: ("work_id", "reason"),
    FACT_ATTEMPT_ABANDONED: ("work_id", "reason"),
    FACT_WORK_CANCELLED: ("work_id",),
}

ALL_FACT_IDS = frozenset(REQUIRED_FIELDS)

# Producible by v0/M0 reducer/policy; excludes FACT-WORK-CANCELLED.
PRODUCIBLE_FACT_IDS = ALL_FACT_IDS - {FACT_WORK_CANCELLED}

EXEC_OUTCOMES = frozenset({"completed", "failed", "cancelled"})
ASSURANCE_VERDICTS = frozenset({"accepted", "rejected", "inconclusive"})


@dataclass(frozen=True)
class Fact:
    """One immutable canonical Fact.

    `data` carries the fact's required fields (per PROTOCOL-FACTS) plus
    delivery_run_id scoping where not already part of `data`. `extensions`
    is opaque, portable baggage (CONTRACT-EXTENSIONS) that core code MUST
    NOT branch on (CONF-EXT-006).
    """

    id: str
    delivery_run_id: str
    data: Mapping[str, Any] = field(default_factory=dict)
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.id not in ALL_FACT_IDS:
            raise ValueError(f"unknown fact id: {self.id!r}")
        required = REQUIRED_FIELDS[self.id]
        missing = [name for name in required if name not in self.data]
        if missing:
            raise ValueError(f"{self.id} missing required data field(s): {missing}")
        if not is_portable(dict(self.data)):
            raise ValueError(f"{self.id} data is not portable/JSON-compatible")
        if not is_portable(dict(self.extensions)):
            raise ValueError(f"{self.id} extensions is not portable/JSON-compatible")
        if self.id == FACT_EXEC_SETTLED and self.data["outcome"] not in EXEC_OUTCOMES:
            raise ValueError(f"{self.id} outcome must be one of {sorted(EXEC_OUTCOMES)}")
        if self.id == FACT_ASSURE_SETTLED and self.data["verdict"] not in ASSURANCE_VERDICTS:
            raise ValueError(f"{self.id} verdict must be one of {sorted(ASSURANCE_VERDICTS)}")

    def field(self, name: str) -> Any:
        return self.data[name]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "delivery_run_id": self.delivery_run_id,
            "data": to_portable(dict(self.data)),
            "extensions": to_portable(dict(self.extensions)),
        }


def make_fact(
    fact_id: str,
    *,
    delivery_run_id: str,
    extensions: Mapping[str, Any] | None = None,
    **data: Any,
) -> Fact:
    """Convenience constructor: `make_fact(FACT_WORK_READY, delivery_run_id=..., work_id=...)`.

    `FACT-WORK-CREATED` lists `delivery_run_id` as required *data* (per
    PROTOCOL-FACTS) in addition to the envelope-scoping `delivery_run_id`
    every Fact carries; this constructor fills that data field from the
    keyword argument so callers do not have to repeat it.
    """
    if fact_id == FACT_WORK_CREATED:
        data.setdefault("delivery_run_id", delivery_run_id)
    return Fact(
        id=fact_id,
        delivery_run_id=delivery_run_id,
        data=data,
        extensions=dict(extensions or {}),
    )
