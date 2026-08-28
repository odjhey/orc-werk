"""Canonical Effects (PROTOCOL-EFFECTS).

An Effect is a requested mutation delegated to a port/adapter. IDs and
target ports mirror `docs/protocol/effects.md` verbatim. `FX-NOTIFY-OPERATOR`
is declared (optional attention/notification adapter, out of M0) but MUST
NOT be produced by v0/M0 reducer/policy code.

Every state-changing Effect carries a stable `idempotency_key` (INV-020).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from orc_werk.core.portable import is_portable, to_portable

FX_CREATE_WORK = "FX-CREATE-WORK"
FX_CLAIM_WORK = "FX-CLAIM-WORK"
FX_START_EXECUTION = "FX-START-EXECUTION"
FX_SEND_EXECUTION = "FX-SEND-EXECUTION"
FX_CANCEL_EXECUTION = "FX-CANCEL-EXECUTION"
FX_IDENTIFY_CANDIDATE = "FX-IDENTIFY-CANDIDATE"
FX_START_ASSURANCE = "FX-START-ASSURANCE"
FX_COMPLETE_WORK = "FX-COMPLETE-WORK"
FX_BLOCK_WORK = "FX-BLOCK-WORK"

# Reserved: declared per PROTOCOL-EFFECTS (optional attention adapter, out of M0).
FX_NOTIFY_OPERATOR = "FX-NOTIFY-OPERATOR"

TARGET_PORT: dict[str, str] = {
    FX_CREATE_WORK: "WorkGraphPort",
    FX_CLAIM_WORK: "WorkGraphPort",
    FX_START_EXECUTION: "ExecutionPort",
    FX_SEND_EXECUTION: "ExecutionPort",
    FX_CANCEL_EXECUTION: "ExecutionPort",
    FX_IDENTIFY_CANDIDATE: "CandidatePort",
    FX_START_ASSURANCE: "AssurancePort",
    FX_COMPLETE_WORK: "WorkGraphPort",
    FX_BLOCK_WORK: "WorkGraphPort",
    FX_NOTIFY_OPERATOR: "attention/notification adapter (optional)",
}

ALL_EFFECT_IDS = frozenset(TARGET_PORT)

# Producible by v0/M0 reducer/policy; excludes FX-NOTIFY-OPERATOR.
PRODUCIBLE_EFFECT_IDS = ALL_EFFECT_IDS - {FX_NOTIFY_OPERATOR}


@dataclass(frozen=True)
class Effect:
    id: str
    delivery_run_id: str
    work_id: str
    idempotency_key: str
    data: Mapping[str, Any] = field(default_factory=dict)
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.id not in ALL_EFFECT_IDS:
            raise ValueError(f"unknown effect id: {self.id!r}")
        if not self.idempotency_key:
            raise ValueError(f"{self.id} missing idempotency_key (INV-020)")
        if not is_portable(dict(self.data)):
            raise ValueError(f"{self.id} data is not portable/JSON-compatible")
        if not is_portable(dict(self.extensions)):
            raise ValueError(f"{self.id} extensions is not portable/JSON-compatible")

    @property
    def target_port(self) -> str:
        return TARGET_PORT[self.id]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "delivery_run_id": self.delivery_run_id,
            "work_id": self.work_id,
            "idempotency_key": self.idempotency_key,
            "data": to_portable(dict(self.data)),
            "extensions": to_portable(dict(self.extensions)),
        }


def make_effect(
    effect_id: str,
    *,
    delivery_run_id: str,
    work_id: str,
    idempotency_key: str,
    data: Mapping[str, Any] | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> Effect:
    return Effect(
        id=effect_id,
        delivery_run_id=delivery_run_id,
        work_id=work_id,
        idempotency_key=idempotency_key,
        data=dict(data or {}),
        extensions=dict(extensions or {}),
    )
