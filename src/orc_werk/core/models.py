"""Canonical identity/reference value types.

`DOMAIN-LANGUAGE` and the port docs define these as plain identity records.
They are implemented as frozen dataclasses purely as a Python convenience
(ADR-0003); the canonical shape is the portable dict returned by `to_dict`,
never the Python class (AGENTS.md #9).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orc_werk.core.portable import to_portable


@dataclass(frozen=True)
class DeliveryRun:
    """One orchestration attempt to drive an intent to a verified terminal outcome."""

    id: str
    intent_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "intent_id": self.intent_id}


@dataclass(frozen=True)
class Work:
    """One logical deliverable unit in the authoritative work topology."""

    id: str
    delivery_run_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "delivery_run_id": self.delivery_run_id}


@dataclass(frozen=True)
class Execution:
    """One delegated work-producing run for one Work item (INV-001, INV-004)."""

    id: str
    work_id: str
    attempt_number: int

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "work_id": self.work_id, "attempt_number": self.attempt_number}


@dataclass(frozen=True)
class Candidate:
    """The exact result subject eligible for assurance (PORT-CANDIDATE shape)."""

    id: str
    work_id: str
    execution_id: str
    subject_identity: Any
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "work_id": self.work_id,
            "execution_id": self.execution_id,
            # subject_identity must be portable when serialized (ARCH-REPOSITORY-STRUCTURE
            # portability rules); to_portable raises for non-JSON-compatible values,
            # matching the guard every other canonical to_dict() already applies.
            "subject_identity": to_portable(self.subject_identity),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class AssuranceRun:
    """One evaluation of one exact Candidate."""

    id: str
    candidate_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "candidate_id": self.candidate_id}
