"""ScriptedCandidate (`TASK-M0-003`): deterministic `CandidatePort` test
double.

Fingerprints are a pure function of scripted subject *content* (never of
execution/work ids) -- `CONF-CAND-001` (same content -> same fingerprint)
and `CONF-CAND-002` (changed content -> different fingerprint) fall out
directly of a canonical-JSON sha256 digest with no adapter-side state.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional

from orc_werk.core.models import Candidate
from orc_werk.core.portable import is_portable, to_portable
from orc_werk.ports.candidate import (
    CANDIDATE_COMPARISON_DIFFERENT,
    CANDIDATE_COMPARISON_SAME,
    CandidatePort,
)


def fingerprint_of(subject_identity: Any) -> str:
    """Deterministic canonical fingerprint: sha256 over sorted-key JSON of
    the portable subject content. A pure function of content only
    (`INV-006`) -- never of execution/work identity."""
    canonical = json.dumps(to_portable(subject_identity), sort_keys=True, separators=(",", ":"))
    return "fp-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


class ScriptedCandidate(CandidatePort):
    """Script format (portable data):

    ```python
    subjects = {
      "<execution_id>": {"work_id": "w1", "subject_identity": {...}},
      # execution_id absent from `subjects`, or "subject_identity": None,
      # -> identify() returns None (execution produced no assurable subject).
    }
    current_by_work = {
      "<work_id>": "<execution_id>",  # must key into `subjects`
      # work_id absent, or mapped to None, -> current() declines (returns
      # None) rather than guessing at a possibly-stale candidate
      # (CONF-CAND-003). None is the decline shape: PORT-CAND-002 already
      # types `current()` as Optional[Candidate], and PORT-CAND-001 uses the
      # same None-for-"nothing safely identifiable" shape for identify() --
      # reusing it here avoids inventing a second sentinel/error shape for
      # the same "nothing to safely report" meaning (see PR body).
    }
    ```
    """

    def __init__(
        self,
        *,
        subjects: Optional[Mapping[str, Mapping[str, Any]]] = None,
        current_by_work: Optional[Mapping[str, Optional[str]]] = None,
    ) -> None:
        subjects = subjects or {}
        current_by_work = current_by_work or {}
        if not is_portable({key: dict(val) for key, val in subjects.items()}):
            raise ValueError("ScriptedCandidate subjects must be portable/JSON-compatible")
        if not is_portable(dict(current_by_work)):
            raise ValueError("ScriptedCandidate current_by_work must be portable/JSON-compatible")
        self._subjects: dict[str, dict[str, Any]] = {key: dict(val) for key, val in subjects.items()}
        self._current_by_work: dict[str, Optional[str]] = dict(current_by_work)

    def capabilities(self) -> frozenset[str]:
        # CONTRACT-CAPABILITIES defines no CandidatePort capability ids as
        # of this writing (ports/base.py, CANDIDATE_CAPABILITIES == frozenset()).
        return frozenset()

    def identify(
        self, *, execution_id: str, artifact_refs: Optional[Mapping[str, Any]] = None
    ) -> Optional[Candidate]:
        entry = self._subjects.get(execution_id)
        if entry is None or entry.get("subject_identity") is None:
            return None
        subject_identity = entry["subject_identity"]
        work_id = entry["work_id"]
        fingerprint = fingerprint_of(subject_identity)
        candidate_id = f"cand-{execution_id}-{fingerprint[3:15]}"
        return Candidate(
            id=candidate_id,
            work_id=work_id,
            execution_id=execution_id,
            subject_identity=subject_identity,
            fingerprint=fingerprint,
        )

    def current(self, *, work_id: str) -> Optional[Candidate]:
        execution_id = self._current_by_work.get(work_id)
        if execution_id is None:
            # CONF-CAND-003: decline explicitly rather than return a
            # possibly-stale guess.
            return None
        return self.identify(execution_id=execution_id)

    def compare(self, *, candidate_a: Candidate, candidate_b: Candidate) -> str:
        if candidate_a.fingerprint == candidate_b.fingerprint:
            return CANDIDATE_COMPARISON_SAME
        return CANDIDATE_COMPARISON_DIFFERENT


__all__ = ["ScriptedCandidate", "fingerprint_of"]
