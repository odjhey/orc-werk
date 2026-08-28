"""Candidate-binding invariant tests: INV-005 through INV-010 structural
enforcement in the reducer (item 7 of TASK-M0-001's scope)."""

from __future__ import annotations

import unittest

from orc_werk.core.errors import CoreError
from orc_werk.core.facts import FACT_ASSURE_STARTED, make_fact
from orc_werk.core.reducer import reduce

from tests.core import fixtures

DRID = "dr-candidate"


class Inv005AssuranceRequiresCandidateTest(unittest.TestCase):
    """INV-005: Work MUST NOT enter assurance without an identifiable Candidate."""

    def test_assure_started_without_candidate_observed_rejected(self) -> None:
        facts = fixtures.dispatched(delivery_run_id=DRID, work_id="w1", execution_id="e1")
        facts.append(
            make_fact(
                FACT_ASSURE_STARTED, delivery_run_id=DRID, work_id="w1", assurance_id="a1", candidate_id="c1"
            )
        )
        with self.assertRaises(CoreError):
            reduce(facts, delivery_run_id=DRID)


class Inv007Inv008EvidenceCandidateBindingTest(unittest.TestCase):
    """INV-007: evidence MUST identify the exact Candidate fingerprint it evaluates.
    INV-008: evidence for Candidate A MUST NOT satisfy assurance for Candidate B
    unless they share a fingerprint (foreign-fingerprint evidence rejected)."""

    def test_settled_with_foreign_fingerprint_rejected(self) -> None:
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id="w1",
            execution_id="e1",
            candidate_id="c1",
            fingerprint="fp-c1",
            assurance_id="a1",
        )
        foreign = fixtures.assure_settled(
            delivery_run_id=DRID,
            work_id="w1",
            assurance_id="a1",
            fingerprint="fp-DIFFERENT-CANDIDATE",
            verdict="accepted",
        )
        with self.assertRaises(CoreError) as ctx:
            reduce(facts + [foreign], delivery_run_id=DRID)
        self.assertEqual(ctx.exception.error["error"], "ERR-CONFLICT")

    def test_matching_fingerprint_accepted(self) -> None:
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id="w1",
            execution_id="e1",
            candidate_id="c1",
            fingerprint="fp-c1",
            assurance_id="a1",
        )
        matching = fixtures.assure_settled(
            delivery_run_id=DRID, work_id="w1", assurance_id="a1", fingerprint="fp-c1", verdict="accepted"
        )
        # no exception: fingerprint matches the current candidate.
        reduce(facts + [matching], delivery_run_id=DRID)


class Inv010CandidateChangeInvalidatesStaleAssuranceTest(unittest.TestCase):
    """INV-010: assurance targeting a candidate that is no longer current is rejected."""

    def test_assure_started_targeting_stale_candidate_rejected(self) -> None:
        # Two full retry cycles: candidate c1 (rejected) -> candidate c2 current.
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id="w1",
            execution_id="e1",
            candidate_id="c1",
            fingerprint="fp-c1",
            assurance_id="a1",
        )
        facts.append(
            fixtures.assure_settled(
                delivery_run_id=DRID, work_id="w1", assurance_id="a1", fingerprint="fp-c1", verdict="rejected"
            )
        )
        facts += fixtures.settled_completed_with_candidate(
            delivery_run_id=DRID, work_id="w1", execution_id="e2", candidate_id="c2", fingerprint="fp-c2"
        )[2:]  # only the retry's exec-start/settle/candidate-observed tail
        # attempt to start assurance against the now-stale c1.
        stale = make_fact(
            FACT_ASSURE_STARTED, delivery_run_id=DRID, work_id="w1", assurance_id="a2", candidate_id="c1"
        )
        with self.assertRaises(CoreError):
            reduce(facts + [stale], delivery_run_id=DRID)


if __name__ == "__main__":
    unittest.main()
