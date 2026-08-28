"""Canonical Decisions (PROTOCOL-DECISIONS).

A Decision is an attributable orchestration choice. IDs mirror
`docs/protocol/decisions.md` verbatim. `DEC-ESCALATE` and `DEC-CANCEL` are
declared (reserved) but MUST NOT be produced by v0/M0 policy
(STATE-DELIVERY "Reserved states and decisions").

Every Decision satisfies INV-011 (attributable) and INV-012 (cites basis):
`attribution` names what made the choice, `basis` is a tuple of portable
fact/state snapshots the choice was based on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from orc_werk.core.portable import is_portable, to_portable

DEC_DISPATCH = "DEC-DISPATCH"
DEC_RETRY = "DEC-RETRY"
DEC_REQUEST_ASSURANCE = "DEC-REQUEST-ASSURANCE"
DEC_ACCEPT = "DEC-ACCEPT"
DEC_BLOCK = "DEC-BLOCK"

# Reserved: declared per PROTOCOL-DECISIONS, unreachable in v0/M0 (STATE-DELIVERY).
DEC_ESCALATE = "DEC-ESCALATE"
DEC_CANCEL = "DEC-CANCEL"

ALL_DECISION_IDS = frozenset(
    {DEC_DISPATCH, DEC_RETRY, DEC_REQUEST_ASSURANCE, DEC_ACCEPT, DEC_BLOCK, DEC_ESCALATE, DEC_CANCEL}
)

# Producible by v0/M0 policy; excludes DEC-ESCALATE and DEC-CANCEL.
PRODUCIBLE_DECISION_IDS = frozenset(
    {DEC_DISPATCH, DEC_RETRY, DEC_REQUEST_ASSURANCE, DEC_ACCEPT, DEC_BLOCK}
)

# v0 policy attribution is a fixed, deterministic identity (no operator/LLM
# judgment in M0 -- see docs/product/thesis.md / M-000 "out of scope: LLM
# planner/watchtower policy").
V0_POLICY_ATTRIBUTION: Mapping[str, Any] = {"policy": "v0-deterministic"}


@dataclass(frozen=True)
class Decision:
    id: str
    delivery_run_id: str
    work_id: str
    attribution: Mapping[str, Any]
    basis: Sequence[Mapping[str, Any]]
    data: Mapping[str, Any] = field(default_factory=dict)
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.id not in ALL_DECISION_IDS:
            raise ValueError(f"unknown decision id: {self.id!r}")
        if not self.attribution:
            raise ValueError(f"{self.id} missing attribution (INV-011)")
        if not self.basis:
            raise ValueError(f"{self.id} missing basis (INV-012)")
        if not is_portable(dict(self.attribution)):
            raise ValueError(f"{self.id} attribution is not portable/JSON-compatible")
        if not is_portable([dict(item) for item in self.basis]):
            raise ValueError(f"{self.id} basis is not portable/JSON-compatible")
        if not is_portable(dict(self.data)):
            raise ValueError(f"{self.id} data is not portable/JSON-compatible")
        if not is_portable(dict(self.extensions)):
            raise ValueError(f"{self.id} extensions is not portable/JSON-compatible")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "delivery_run_id": self.delivery_run_id,
            "work_id": self.work_id,
            "attribution": to_portable(dict(self.attribution)),
            "basis": [to_portable(dict(item)) for item in self.basis],
            "data": to_portable(dict(self.data)),
            "extensions": to_portable(dict(self.extensions)),
        }


def make_decision(
    decision_id: str,
    *,
    delivery_run_id: str,
    work_id: str,
    basis: Sequence[Mapping[str, Any]],
    attribution: Mapping[str, Any] | None = None,
    data: Mapping[str, Any] | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> Decision:
    return Decision(
        id=decision_id,
        delivery_run_id=delivery_run_id,
        work_id=work_id,
        attribution=dict(attribution or V0_POLICY_ATTRIBUTION),
        basis=tuple(dict(item) for item in basis),
        data=dict(data or {}),
        extensions=dict(extensions or {}),
    )
