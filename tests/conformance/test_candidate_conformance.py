"""`CONF-CAND-*` conformance suite (`PORT-CANDIDATE`).

`CandidatePortConformance` is a reusable mixin (not itself a `TestCase`):
any current or future `CandidatePort` implementation runs the same suite
by subclassing it alongside `unittest.TestCase` and implementing
`make_candidate()`.
"""

from __future__ import annotations

import unittest
from typing import Any, Mapping, Optional

from orc_werk.adapters.scripted import ScriptedCandidate
from orc_werk.ports.candidate import (
    CANDIDATE_COMPARISON_DIFFERENT,
    CANDIDATE_COMPARISON_SAME,
    CandidatePort,
)


class CandidatePortConformance:
    def make_candidate(
        self,
        *,
        subjects: Mapping[str, Mapping[str, Any]],
        current_by_work: Optional[Mapping[str, Optional[str]]] = None,
    ) -> CandidatePort:
        raise NotImplementedError

    # -- CONF-CAND-001: same exact subject yields the same fingerprint. --

    def test_conf_cand_001_same_subject_same_fingerprint(self) -> None:
        subjects = {
            "e1": {"work_id": "w1", "subject_identity": {"files": {"a.py": "x"}}},
            "e2": {"work_id": "w1", "subject_identity": {"files": {"a.py": "x"}}},
        }
        adapter = self.make_candidate(subjects=subjects)
        c1 = adapter.identify(execution_id="e1")
        c2 = adapter.identify(execution_id="e2")
        self.assertIsNotNone(c1)
        self.assertIsNotNone(c2)
        self.assertEqual(c1.fingerprint, c2.fingerprint)
        self.assertEqual(
            adapter.compare(candidate_a=c1, candidate_b=c2), CANDIDATE_COMPARISON_SAME
        )

    # -- CONF-CAND-002: changed subject yields a different fingerprint. --

    def test_conf_cand_002_changed_subject_different_fingerprint(self) -> None:
        subjects = {
            "e1": {"work_id": "w1", "subject_identity": {"files": {"a.py": "x"}}},
            "e2": {"work_id": "w1", "subject_identity": {"files": {"a.py": "y"}}},
        }
        adapter = self.make_candidate(subjects=subjects)
        c1 = adapter.identify(execution_id="e1")
        c2 = adapter.identify(execution_id="e2")
        self.assertNotEqual(c1.fingerprint, c2.fingerprint)
        self.assertEqual(
            adapter.compare(candidate_a=c1, candidate_b=c2), CANDIDATE_COMPARISON_DIFFERENT
        )

    # -- CONF-CAND-003: current() must not silently return a known-stale candidate. --

    def test_conf_cand_003_current_declines_when_not_safely_determinable(self) -> None:
        subjects = {"e1": {"work_id": "w1", "subject_identity": {"a": 1}}}
        adapter = self.make_candidate(subjects=subjects, current_by_work={})
        self.assertIsNone(adapter.current(work_id="w1"))

    def test_conf_cand_003_current_returns_candidate_when_safely_determinable(self) -> None:
        subjects = {"e1": {"work_id": "w1", "subject_identity": {"a": 1}}}
        adapter = self.make_candidate(subjects=subjects, current_by_work={"w1": "e1"})
        current = adapter.current(work_id="w1")
        self.assertIsNotNone(current)
        self.assertEqual(current.execution_id, "e1")
        self.assertEqual(current.work_id, "w1")

    # -- identify(): MAY return none when the execution produced no assurable subject. --

    def test_identify_returns_none_when_execution_produced_no_subject(self) -> None:
        adapter = self.make_candidate(
            subjects={"e1": {"work_id": "w1", "subject_identity": None}}
        )
        self.assertIsNone(adapter.identify(execution_id="e1"))

    def test_identify_returns_none_for_unscripted_execution(self) -> None:
        adapter = self.make_candidate(subjects={})
        self.assertIsNone(adapter.identify(execution_id="ghost"))


class ScriptedCandidateConformanceTest(CandidatePortConformance, unittest.TestCase):
    def make_candidate(
        self,
        *,
        subjects: Mapping[str, Mapping[str, Any]],
        current_by_work: Optional[Mapping[str, Optional[str]]] = None,
    ) -> CandidatePort:
        return ScriptedCandidate(subjects=subjects, current_by_work=current_by_work)


if __name__ == "__main__":
    unittest.main()
