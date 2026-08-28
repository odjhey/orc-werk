"""AssurancePort (`PORT-ASSURANCE`): request and observe independent
evaluation of one exact Candidate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from abc import abstractmethod
from typing import Any, Mapping, Optional

from orc_werk.core.facts import ASSURANCE_VERDICTS
from orc_werk.core.models import AssuranceRun, Candidate
from orc_werk.core.portable import is_portable, to_portable
from orc_werk.ports.base import LIFECYCLE_STATE_SETTLED, LIFECYCLE_STATES, Port


@dataclass(frozen=True)
class AssuranceObservation:
    """`PORT-ASSURE-002` canonical `inspect` result:

    ```text
    state: requested | running | settled
    verdict?: accepted | rejected | inconclusive
    candidate_fingerprint: required when settled
    evidence_refs: zero or more
    final_candidate?: Candidate when provider may mutate the subject
    extensions?: map<versioned_extension_id, json_payload>
    ```

    `final_candidate`, when present, is the portable dict shape produced by
    `orc_werk.core.models.Candidate.to_dict()` -- only providers advertising
    `CAP-ASSURE-MAY-MUTATE-CANDIDATE` populate it. `extensions` is opaque,
    portable baggage (`CONTRACT-EXTENSIONS`); this shape's `to_dict`/
    `from_dict` round-trip preserves unknown extension keys losslessly
    (`EXT-005`).
    """

    state: str
    verdict: Optional[str] = None
    candidate_fingerprint: Optional[str] = None
    evidence_refs: tuple[Any, ...] = field(default_factory=tuple)
    final_candidate: Optional[Mapping[str, Any]] = None
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in LIFECYCLE_STATES:
            raise ValueError(f"unknown assurance observation state: {self.state!r}")
        if self.verdict is not None and self.verdict not in ASSURANCE_VERDICTS:
            raise ValueError(f"unknown assurance verdict: {self.verdict!r}")
        if self.state == LIFECYCLE_STATE_SETTLED and not self.candidate_fingerprint:
            # PORT-ASSURE-002: "candidate_fingerprint: required when settled".
            raise ValueError(
                "assurance observation missing candidate_fingerprint (required when settled)"
            )
        if not is_portable(list(self.evidence_refs)):
            raise ValueError("evidence_refs is not portable/JSON-compatible")
        if self.final_candidate is not None and not is_portable(dict(self.final_candidate)):
            raise ValueError("final_candidate is not portable/JSON-compatible")
        if not is_portable(dict(self.extensions)):
            raise ValueError("extensions is not portable/JSON-compatible")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"state": self.state}
        if self.verdict is not None:
            data["verdict"] = self.verdict
        if self.candidate_fingerprint is not None:
            data["candidate_fingerprint"] = self.candidate_fingerprint
        data["evidence_refs"] = to_portable(list(self.evidence_refs))
        if self.final_candidate is not None:
            data["final_candidate"] = to_portable(dict(self.final_candidate))
        data["extensions"] = to_portable(dict(self.extensions))
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AssuranceObservation":
        final_candidate = data.get("final_candidate")
        return cls(
            state=data["state"],
            verdict=data.get("verdict"),
            candidate_fingerprint=data.get("candidate_fingerprint"),
            evidence_refs=tuple(data.get("evidence_refs", [])),
            final_candidate=dict(final_candidate) if final_candidate is not None else None,
            extensions=dict(data.get("extensions", {})),
        )


class AssurancePort(Port):
    """`PORT-ASSURANCE`: request / inspect."""

    @abstractmethod
    def request(
        self,
        *,
        candidate: Candidate,
        requirements: Mapping[str, Any],
        idempotency_key: str,
    ) -> AssuranceRun:
        """`PORT-ASSURE-001`. `requirements` is an opaque portable mapping
        -- the port does not structure provider-specific assurance
        requirements. Returns an AssuranceRun reference."""
        raise NotImplementedError

    @abstractmethod
    def inspect(self, *, assurance_id: str) -> AssuranceObservation:
        """`PORT-ASSURE-002`. A provider that may mutate the candidate MUST
        advertise `CAP-ASSURE-MAY-MUTATE-CANDIDATE`
        (`orc_werk.ports.capabilities.CAP_ASSURE_MAY_MUTATE_CANDIDATE`) and
        populate `AssuranceObservation.final_candidate` when changed. The
        generic core records/transports `extensions` but MUST NOT inspect
        their internals to derive the canonical verdict or candidate
        identity (`EXT-002`, `EXT-007`)."""
        raise NotImplementedError


__all__ = ["AssuranceObservation", "AssurancePort"]
