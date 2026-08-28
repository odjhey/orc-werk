"""CandidatePort (`PORT-CANDIDATE`): translate provider artifacts/results
into an exact canonical Candidate suitable for assurance freshness checks.

Provider-native subject fields are opaque to the core (`orc_werk.core.models.
Candidate.subject_identity`); the adapter must produce a deterministic
canonical fingerprint.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Mapping, Optional

from orc_werk.core.models import Candidate
from orc_werk.ports.base import Port

CANDIDATE_COMPARISON_SAME = "same"
CANDIDATE_COMPARISON_DIFFERENT = "different"
CANDIDATE_COMPARISONS = frozenset({CANDIDATE_COMPARISON_SAME, CANDIDATE_COMPARISON_DIFFERENT})


class CandidatePort(Port):
    """`PORT-CANDIDATE`: identify / current / compare."""

    @abstractmethod
    def identify(
        self, *, execution_id: str, artifact_refs: Optional[Mapping[str, Any]] = None
    ) -> Optional[Candidate]:
        """`PORT-CAND-001`. Identify the candidate produced by one
        execution/artifact set. May return `None` when the execution
        produced no assurable subject. `artifact_refs` is an opaque
        portable mapping (or `None`) naming the artifact set to identify."""
        raise NotImplementedError

    @abstractmethod
    def current(self, *, work_id: str) -> Optional[Candidate]:
        """`PORT-CAND-002`. Return the current candidate for Work when the
        provider can determine one safely; otherwise `None` rather than a
        possibly-stale guess (`INV-006`)."""
        raise NotImplementedError

    @abstractmethod
    def compare(self, *, candidate_a: Candidate, candidate_b: Candidate) -> str:
        """`PORT-CAND-003`. Return `CANDIDATE_COMPARISON_SAME` or
        `CANDIDATE_COMPARISON_DIFFERENT` according to canonical fingerprint
        equality."""
        raise NotImplementedError


__all__ = [
    "CANDIDATE_COMPARISON_DIFFERENT",
    "CANDIDATE_COMPARISON_SAME",
    "CANDIDATE_COMPARISONS",
    "CandidatePort",
]
